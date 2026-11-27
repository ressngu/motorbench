"""Unit tests for the hardware interfaces.

AI usage: drafted with Claude; reviewed and edited by me.
"""

import dataclasses

import numpy as np
import pytest

from motorbench.interfaces import (
    Clock,
    DriveState,
    MotorDrive,
    RunStoppedError,
    TorqueSeries,
)


class StepClock(Clock):
    """Minimal clock for tests: time only moves when waited on."""

    def __init__(self) -> None:
        super().__init__()
        self._t_s = 0.0

    def now_s(self) -> float:
        return self._t_s

    def wait(self, duration_s: float) -> None:
        if self.stop_requested:
            raise RunStoppedError
        self._t_s += duration_s


def test_incomplete_drive_cannot_be_created() -> None:
    class HalfDrive(MotorDrive):
        def enable(self) -> None:
            pass

    with pytest.raises(TypeError, match="abstract"):
        HalfDrive()  # type: ignore[abstract]


def test_drive_state_is_read_only() -> None:
    state = DriveState(0.0, 1.0, 0.0, 0.0, 36.0, 25.0)
    with pytest.raises(dataclasses.FrozenInstanceError):
        state.iq_a = 2.0  # type: ignore[misc]


def test_torque_series_keeps_matching_arrays() -> None:
    series = TorqueSeries(t_s=np.arange(3.0), torque_nm=np.ones(3))
    assert series.torque_nm.mean() == pytest.approx(1.0)


def test_torque_series_rejects_mismatched_arrays() -> None:
    with pytest.raises(ValueError, match="same shape"):
        TorqueSeries(t_s=np.zeros(3), torque_nm=np.zeros(4))


def test_wait_moves_time_until_stop_requested() -> None:
    clock = StepClock()
    clock.wait(1.5)
    assert clock.now_s() == pytest.approx(1.5)

    clock.request_stop()
    assert clock.stop_requested
    with pytest.raises(RunStoppedError):
        clock.wait(1.0)
