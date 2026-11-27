"""Torque-constant test, following Lee et al. (2019), section II-B-1.

With the rotor locked to the torque sensor, hold each current for 9 s
and average the middle 7 s of torque and measured current. Average
the five trials at each current, then fit a straight line through the
averages: the slope is the torque constant Kt.

Two additions to the paper: the trials run in a random order, so slow
drift can't look like a trend, and Kt comes with a 95% confidence
interval.

AI usage: drafted with Claude; reviewed and edited by me.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from matplotlib.figure import Figure
from numpy.typing import NDArray
from scipy import stats

from motorbench.procedure import Rig, TestProcedure

TARE_WAIT_S = 1.0
"""Time to collect torque samples before taring."""


@dataclass(frozen=True)
class TorqueConstantSettings:
    """Test settings. The defaults follow Lee et al. (2019).

    Attributes:
        levels_a: Currents to test: -5 A to +5 A in 1 A steps.
        trials: Trials at each current.
        settle_s: Time discarded at the start of each trial.
        record_s: Time averaged in each trial.
        drop_s: Time discarded at the end of each trial.
        state_period_s: Time between drive-state readings.
        current_limit_a: Largest current allowed. The default is the
            BotWheel's continuous rating.
        seed: Seed for the random trial order.
    """

    levels_a: tuple[float, ...] = tuple(float(i) for i in range(-5, 6))
    trials: int = 5
    settle_s: float = 1.0
    record_s: float = 7.0
    drop_s: float = 1.0
    state_period_s: float = 0.1
    current_limit_a: float = 5.0
    seed: int = 0

    def __post_init__(self) -> None:
        """Check the settings before anything runs.

        Raises:
            ValueError: If there are fewer than three currents, a
                current is over the limit, or ``trials`` is below 1.
        """
        if len(set(self.levels_a)) < 3:
            raise ValueError("need at least three different currents")
        if max(abs(i) for i in self.levels_a) > self.current_limit_a:
            raise ValueError("a current is over current_limit_a")
        if self.trials < 1:
            raise ValueError("trials must be at least 1")


DEFAULT_SETTINGS = TorqueConstantSettings()
"""Lee et al. (2019)'s protocol."""


@dataclass(frozen=True)
class Trial:
    """Averages from one trial."""

    commanded_a: float
    current_a: float
    torque_nm: float


@dataclass(frozen=True, eq=False)
class TorqueConstantResult:
    """The fitted torque constant, and the data behind it.

    Attributes:
        kt_nm_a: Torque constant: the slope of the fitted line.
        kt_ci95_nm_a: Half-width of its 95% confidence interval.
        intercept_nm: Torque at zero current: leftover sensor offset
            plus the cogging torque at the locked angle.
        r_squared: How well the line fits, from 0 to 1.
        current_a: Average measured current at each level.
        torque_nm: Average torque at each level.
        trials: Every trial, in the order they ran.
    """

    kt_nm_a: float
    kt_ci95_nm_a: float
    intercept_nm: float
    r_squared: float
    current_a: NDArray[np.float64]
    torque_nm: NDArray[np.float64]
    trials: tuple[Trial, ...]


class TorqueConstantTest(TestProcedure[list[Trial], TorqueConstantResult]):
    """Measure Kt with the rotor locked (Lee et al., 2019)."""

    def __init__(
        self, settings: TorqueConstantSettings = DEFAULT_SETTINGS
    ) -> None:
        """Create the test.

        Args:
            settings: Test settings; Lee et al.'s protocol by default.
        """
        self.settings = settings

    def plan(self) -> list[float]:
        """Return every trial's current, in a seeded random order."""
        s = self.settings
        rng = np.random.default_rng(s.seed)
        order = rng.permutation(np.repeat(s.levels_a, s.trials))
        return [float(i) for i in order]

    def execute(self, rig: Rig) -> list[Trial]:
        """Tare with no current, then run every trial.

        The shaft must already be locked to the torque sensor.
        """
        s = self.settings
        rig.clock.wait(TARE_WAIT_S)
        rig.torque.tare()
        rig.drive.enable()
        trials = []
        for level_a in self.plan():
            rig.drive.set_current(level_a)
            rig.clock.wait(s.settle_s)
            currents_a = []
            for _ in range(round(s.record_s / s.state_period_s)):
                rig.clock.wait(s.state_period_s)
                currents_a.append(rig.drive.read_state().iq_a)
            torque_nm = rig.torque.read_block(s.record_s).torque_nm
            rig.clock.wait(s.drop_s)
            trials.append(
                Trial(level_a, float(np.mean(currents_a)), torque_nm.mean())
            )
        return trials

    def analyze(self, data: list[Trial]) -> TorqueConstantResult:
        """Fit Kt to the trials."""
        return fit_torque_constant(data)


def fit_torque_constant(trials: Sequence[Trial]) -> TorqueConstantResult:
    """Average the trials at each current, then fit a straight line.

    The 95% interval uses Student's t with n - 2 degrees of freedom,
    where n is the number of current levels.
    """
    levels_a = sorted({t.commanded_a for t in trials})
    current_a = np.array(
        [
            np.mean([t.current_a for t in trials if t.commanded_a == level])
            for level in levels_a
        ]
    )
    torque_nm = np.array(
        [
            np.mean([t.torque_nm for t in trials if t.commanded_a == level])
            for level in levels_a
        ]
    )
    fit = stats.linregress(current_a, torque_nm)
    t_95 = float(stats.t.ppf(0.975, len(levels_a) - 2))
    return TorqueConstantResult(
        kt_nm_a=float(fit.slope),
        kt_ci95_nm_a=t_95 * float(fit.stderr),
        intercept_nm=float(fit.intercept),
        r_squared=float(fit.rvalue) ** 2,
        current_a=current_a,
        torque_nm=torque_nm,
        trials=tuple(trials),
    )


def plot_torque_constant(result: TorqueConstantResult, path: Path) -> None:
    """Save a plot of torque against current, with the fitted line."""
    fig = Figure(figsize=(6.4, 4.2), layout="constrained")
    ax = fig.subplots()
    ax.plot(
        [t.current_a for t in result.trials],
        [t.torque_nm for t in result.trials],
        "o",
        color="0.65",
        ms=3,
        label="Each trial",
    )
    ax.plot(
        result.current_a,
        result.torque_nm,
        "o",
        color="C0",
        label="Average at each current",
    )
    ends_a = np.array([result.current_a.min(), result.current_a.max()])
    ax.plot(
        ends_a,
        result.kt_nm_a * ends_a + result.intercept_nm,
        color="C1",
        label=(
            f"Kt = {result.kt_nm_a:.4f} ± {result.kt_ci95_nm_a:.4f} N·m/A"
            f" (95%), R² = {result.r_squared:.5f}"
        ),
    )
    ax.set_xlabel("Measured current [A]")
    ax.set_ylabel("Torque [N·m]")
    ax.set_title("Torque constant (Lee et al. 2019 method)")
    ax.grid(alpha=0.3)
    ax.legend()
    fig.savefig(path, dpi=150)
