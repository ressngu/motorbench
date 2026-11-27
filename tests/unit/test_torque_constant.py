"""Unit tests for the torque-constant test's settings, plan and fit.

AI usage: drafted with Claude; reviewed and edited by me.
"""

from pathlib import Path

import pytest

from motorbench.torque_constant import (
    TorqueConstantSettings,
    TorqueConstantTest,
    Trial,
    fit_torque_constant,
    plot_torque_constant,
)


def line_trials(kt_nm_a: float, offset_nm: float) -> list[Trial]:
    """Two trials per current, scattered evenly about a known line."""
    trials = []
    for level_a in (-2.0, -1.0, 0.0, 1.0, 2.0):
        for scatter_nm in (-0.01, 0.01):
            torque_nm = kt_nm_a * level_a + offset_nm + scatter_nm
            trials.append(Trial(level_a, level_a, torque_nm))
    return trials


def test_settings_reject_currents_over_the_limit() -> None:
    with pytest.raises(ValueError, match="over current_limit_a"):
        TorqueConstantSettings(levels_a=(-6.0, 0.0, 6.0))


def test_settings_need_three_currents() -> None:
    with pytest.raises(ValueError, match="three"):
        TorqueConstantSettings(levels_a=(-1.0, 1.0, 1.0))


def test_settings_need_a_trial() -> None:
    with pytest.raises(ValueError, match="trials"):
        TorqueConstantSettings(trials=0)


def test_plan_runs_every_current_five_times_in_a_seeded_order() -> None:
    plan = TorqueConstantTest().plan()
    levels = [float(i) for i in range(-5, 6)]
    assert sorted(plan) == sorted(levels * 5)
    assert plan != sorted(plan)  # shuffled
    assert plan == TorqueConstantTest().plan()  # same seed, same order


def test_fit_recovers_a_known_line() -> None:
    result = fit_torque_constant(line_trials(0.9, 0.02))
    assert result.kt_nm_a == pytest.approx(0.9)
    assert result.intercept_nm == pytest.approx(0.02)
    # Exactly zero in theory; scipy computes it via sqrt(1 - R^2), which
    # turns ~1e-16 of rounding into ~1e-8, so allow a little.
    assert result.kt_ci95_nm_a == pytest.approx(0.0, abs=1e-6)
    assert result.r_squared == pytest.approx(1.0)
    assert result.current_a.tolist() == [-2.0, -1.0, 0.0, 1.0, 2.0]


def test_plot_saves_a_file(tmp_path: Path) -> None:
    path = tmp_path / "kt.png"
    plot_torque_constant(fit_torque_constant(line_trials(0.9, 0.0)), path)
    assert path.stat().st_size > 0


def test_interval_matches_a_hand_calculation() -> None:
    # Points (-1, -1), (0, 0.1), (1, 1): slope 1, residuals -1/30, 2/30,
    # -1/30, so stderr = sqrt((6/900) / 1 / 2) = 0.05774 and
    # t(0.975, 1 dof) = 12.706, giving 0.7336.
    result = fit_torque_constant(
        [Trial(-1.0, -1.0, -1.0), Trial(0.0, 0.0, 0.1), Trial(1.0, 1.0, 1.0)]
    )
    assert result.kt_nm_a == pytest.approx(1.0)
    assert result.kt_ci95_nm_a == pytest.approx(0.7336, abs=1e-4)
