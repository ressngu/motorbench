"""Unit tests for the simulated test bench.

Most tests turn the noise off, so the expected values are exact.

AI usage: drafted with Claude; reviewed and edited by me.
"""

import math

import numpy as np
import pytest
from numpy.typing import NDArray

from motorbench.interfaces import RunStoppedError
from motorbench.sim import BOTWHEEL, MeasurementParams, SimBench, SimClock

NO_NOISE = MeasurementParams(current_noise_a=0.0, torque_noise_nm=0.0)
KT = BOTWHEEL.kt_nm_a


def make_bench(
    *, locked: bool = True, lock_angle_rad: float = 0.0
) -> SimBench:
    return SimBench(
        measurement=NO_NOISE, locked=locked, lock_angle_rad=lock_angle_rad
    )


# Clock


def test_clock_counts_whole_steps() -> None:
    steps: list[float] = []
    clock = SimClock(steps.append, dt_s=0.001)
    clock.wait(0.25)
    assert len(steps) == 250
    assert clock.now_s() == pytest.approx(0.25)


def test_clock_time_does_not_drift() -> None:
    clock = SimClock(lambda dt_s: None, dt_s=0.001)
    for _ in range(10_000):
        clock.wait(0.001)
    assert clock.now_s() == 10.0  # adding 0.001 10,000 times gives 9.9999...


def test_clock_rejects_bad_durations() -> None:
    with pytest.raises(ValueError, match="positive"):
        SimClock(lambda dt_s: None, dt_s=0.0)
    with pytest.raises(ValueError, match="negative"):
        SimClock(lambda dt_s: None).wait(-1.0)


def test_clock_stops_at_the_step_where_stop_was_requested() -> None:
    def step(dt_s: float) -> None:
        if clock.now_s() >= 0.005:
            clock.request_stop()

    clock = SimClock(step, dt_s=0.001)
    with pytest.raises(RunStoppedError):
        clock.wait(1.0)
    assert clock.now_s() == pytest.approx(0.005)
    with pytest.raises(RunStoppedError):
        clock.wait(0.0)


# Drive


def test_drive_refuses_commands_until_enabled() -> None:
    drive = make_bench().drive
    with pytest.raises(RuntimeError, match="enable"):
        drive.set_current(1.0)
    with pytest.raises(RuntimeError, match="enable"):
        drive.set_velocity(1.0)


def test_current_settles_to_command() -> None:
    bench = make_bench()
    bench.drive.enable()
    bench.drive.set_current(3.0)
    bench.clock.wait(0.02)  # 20 current-loop time constants
    assert bench.drive.read_state().iq_a == pytest.approx(3.0)


def test_current_is_clamped_to_peak() -> None:
    bench = make_bench()
    bench.drive.enable()
    bench.drive.set_current(-50.0)
    bench.clock.wait(0.02)
    assert bench.drive.read_state().iq_a == pytest.approx(-15.0)


def test_disable_is_safe_twice_and_current_decays() -> None:
    bench = make_bench()
    bench.drive.enable()
    bench.drive.set_current(2.0)
    bench.clock.wait(0.02)
    bench.drive.disable()
    bench.drive.disable()
    bench.clock.wait(0.02)
    assert bench.drive.read_state().iq_a == pytest.approx(0.0, abs=1e-6)


def test_state_has_time_and_encoder_counts() -> None:
    bench = make_bench(lock_angle_rad=0.1)
    bench.clock.wait(0.5)
    state = bench.drive.read_state()
    count_rad = 2 * math.pi / BOTWHEEL.encoder_cpr
    assert state.t_s == pytest.approx(0.5)
    assert state.angle_rad / count_rad == pytest.approx(51.0)  # 50.93
    assert state.vbus_v > 0.0


# Locked shaft and torque sensor


def test_locked_torque_is_kt_times_current_plus_cogging() -> None:
    angle = math.pi / (2 * BOTWHEEL.cogging_order)  # where sin(N*angle) = 1
    bench = make_bench(lock_angle_rad=angle)
    bench.drive.enable()
    bench.drive.set_current(2.0)
    bench.clock.wait(1.0)
    torque = bench.torque_sensor.read_block(0.5).torque_nm
    expected = KT * 2.0 - BOTWHEEL.cogging_amplitude_nm
    # No tare yet, so the sensor's offset is still in the reading.
    assert torque.mean() == pytest.approx(expected + NO_NOISE.torque_offset_nm)


def test_tare_removes_offset_and_holding_torque() -> None:
    angle = math.pi / (2 * BOTWHEEL.cogging_order)
    bench = make_bench(lock_angle_rad=angle)
    bench.clock.wait(1.0)
    bench.torque_sensor.tare()
    bench.drive.enable()
    bench.drive.set_current(2.0)
    bench.clock.wait(1.0)
    assert bench.torque_sensor.read_block(0.5).torque_nm.mean() == (
        pytest.approx(KT * 2.0)
    )


def test_tare_needs_enough_samples() -> None:
    bench = make_bench()
    bench.clock.wait(0.1)
    with pytest.raises(RuntimeError, match="tare"):
        bench.torque_sensor.tare()


def test_read_block_returns_the_newest_samples_in_order() -> None:
    bench = make_bench()
    bench.clock.wait(2.5)
    t_s = bench.torque_sensor.read_block(1.0).t_s
    assert t_s.size == 1000
    assert t_s[-1] == pytest.approx(2.5)
    assert np.all(np.diff(t_s) > 0.0)


def test_read_block_wraps_around_the_buffer() -> None:
    small = MeasurementParams(current_noise_a=0.0, buffer_s=0.5)
    bench = SimBench(measurement=small)
    bench.clock.wait(1.2)
    t_s = bench.torque_sensor.read_block(0.5).t_s
    assert t_s[0] == pytest.approx(0.701)
    assert t_s[-1] == pytest.approx(1.2)
    assert np.all(np.diff(t_s) > 0.0)


def test_read_block_rejects_bad_durations() -> None:
    bench = make_bench()
    bench.clock.wait(1.0)
    with pytest.raises(ValueError, match="one sample"):
        bench.torque_sensor.read_block(0.0)
    with pytest.raises(ValueError, match="buffered"):
        bench.torque_sensor.read_block(2.0)


# Free shaft


def test_static_friction_holds_a_small_current() -> None:
    bench = make_bench(locked=False)
    bench.drive.enable()
    bench.drive.set_current(0.03)  # 0.029 N*m, under 0.06 N*m friction
    bench.clock.wait(1.0)
    assert bench.drive.read_state().speed_rad_s == 0.0


def test_free_shaft_reads_no_torque() -> None:
    bench = make_bench(locked=False)
    bench.drive.enable()
    bench.drive.set_current(1.0)
    bench.clock.wait(0.5)
    assert bench.drive.read_state().speed_rad_s > 0.0
    torque = bench.torque_sensor.read_block(0.5).torque_nm
    assert torque.mean() == pytest.approx(NO_NOISE.torque_offset_nm)


@pytest.mark.parametrize("speed_rad_s", [10.0, -10.0])
def test_speed_loop_holds_the_set_speed(speed_rad_s: float) -> None:
    bench = make_bench(locked=False)
    bench.drive.enable()
    bench.drive.set_velocity(speed_rad_s)
    bench.clock.wait(2.0)
    speed = bench.drive.read_state().speed_rad_s
    assert speed == pytest.approx(speed_rad_s, rel=0.01)


def test_speed_loop_follows_a_new_set_speed() -> None:
    bench = make_bench(locked=False)
    bench.drive.enable()
    bench.drive.set_velocity(5.0)
    bench.clock.wait(1.0)
    bench.drive.set_velocity(10.0)
    bench.clock.wait(2.0)
    assert bench.drive.read_state().speed_rad_s == pytest.approx(
        10.0, rel=0.01
    )


def test_speed_loop_output_is_limited() -> None:
    bench = make_bench(locked=False)
    bench.drive.enable()
    bench.drive.set_velocity(1000.0)
    bench.clock.wait(0.1)
    assert bench.drive.read_state().iq_a == pytest.approx(15.0)


def test_friction_stops_the_shaft_after_disable() -> None:
    bench = make_bench(locked=False)
    bench.drive.enable()
    bench.drive.set_velocity(10.0)
    bench.clock.wait(2.0)
    bench.drive.disable()
    bench.clock.wait(3.0)
    assert bench.drive.read_state().speed_rad_s == 0.0


# Noise


def test_same_seed_gives_the_same_run() -> None:
    def run(seed: int) -> NDArray[np.float64]:
        bench = SimBench(seed=seed)
        bench.clock.wait(1.0)
        return bench.torque_sensor.read_block(1.0).torque_nm

    assert np.array_equal(run(1), run(1))
    assert not np.array_equal(run(1), run(2))
