"""Simulated test bench: a BotWheel motor, its drive and torque sensor.

Lets every test procedure run without hardware (software-in-the-loop,
Lecture 17). The classes implement the interfaces from decision 001,
so a procedure can't tell the simulator from the real rig.

Model:
    - Drive: a first-order current loop, with a PI speed loop on top
      for velocity commands.
    - Shaft: either locked (torque-constant test) or free. When free,
      J * dw/dt = Kt * i + cogging - friction, as in Lee et al. (2019),
      eq. (1), with Coulomb and viscous friction (Armstrong-Helouvry
      et al., 1994) and sinusoidal cogging.
    - Sensors: the drive reports current with noise and an encoder
      angle in whole counts; the torque sensor samples once per step
      (1 kHz by default) into a fixed-length buffer, like the hub.

AI usage: drafted with Claude (Anthropic); reviewed and edited by me.
"""

import math
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

import numpy as np
from numpy.typing import NDArray

from motorbench.interfaces import (
    Clock,
    DriveState,
    MotorDrive,
    RunStoppedError,
    TorqueSensor,
    TorqueSeries,
)


@dataclass(frozen=True)
class MotorParams:
    """Physical parameters of a motor. Units are in the names.

    Currents use ODrive's convention: phase amplitude (peak).
    """

    kt_nm_a: float
    phase_resistance_ohm: float
    phase_inductance_h: float
    pole_pairs: int
    continuous_current_a: float
    peak_current_a: float
    encoder_cpr: int
    inertia_kg_m2: float
    coulomb_friction_nm: float
    viscous_friction_nm_s_rad: float
    cogging_amplitude_nm: float
    cogging_order: int
    current_bandwidth_rad_s: float


BOTWHEEL = MotorParams(
    # Published by ODrive Robotics ("ODrive Motors" specifications).
    kt_nm_a=0.951,
    phase_resistance_ohm=0.8,
    phase_inductance_h=1.7e-3,
    pole_pairs=15,
    continuous_current_a=5.0,
    peak_current_a=15.0,
    encoder_cpr=3200,
    # Assumed until measured on the rig.
    inertia_kg_m2=0.004,
    coulomb_friction_nm=0.060,
    viscous_friction_nm_s_rad=0.0025,
    cogging_amplitude_nm=0.025,
    cogging_order=270,
    current_bandwidth_rad_s=1000.0,
)
"""ODrive BotWheel: published values, plus labelled assumptions."""


@dataclass(frozen=True)
class MeasurementParams:
    """Noise, offset and buffer settings of the simulated sensors."""

    current_noise_a: float = 0.02
    torque_noise_nm: float = 0.005
    torque_offset_nm: float = 0.05
    buffer_s: float = 60.0
    tare_window_s: float = 0.5


DEFAULT_MEASUREMENT = MeasurementParams()
"""Sensor settings used unless a test passes its own."""


class SimClock(Clock):
    """Simulated time that moves only when a procedure waits.

    Time is kept as a whole number of steps, so it never drifts the
    way repeatedly adding 0.001 does.
    """

    def __init__(
        self, step: Callable[[float], None], dt_s: float = 1e-3
    ) -> None:
        """Create the clock.

        Args:
            step: Called once per step to advance the physics by
                ``dt_s`` seconds.
            dt_s: Length of one step.

        Raises:
            ValueError: If ``dt_s`` isn't positive.
        """
        super().__init__()
        if dt_s <= 0.0:
            raise ValueError("dt_s must be positive")
        self._step = step
        self._dt_s = dt_s
        self._steps = 0

    def now_s(self) -> float:
        """Return seconds since the run started."""
        return self._steps * self._dt_s

    def wait(self, duration_s: float) -> None:
        """Step the physics forward by ``duration_s``.

        The duration is rounded to the nearest whole step.

        Raises:
            ValueError: If ``duration_s`` is negative.
            RunStoppedError: If a stop is requested before or while
                waiting. Time stops at the step where it was seen.
        """
        if duration_s < 0.0:
            raise ValueError("duration_s can't be negative")
        if self.stop_requested:
            raise RunStoppedError
        for _ in range(round(duration_s / self._dt_s)):
            self._steps += 1
            self._step(self._dt_s)
            if self.stop_requested:
                raise RunStoppedError


class SimMotor:
    """The motor's shaft: locked in place, or free to turn."""

    def __init__(
        self, params: MotorParams, *, locked: bool, lock_angle_rad: float
    ) -> None:
        """Create the motor at rest.

        Args:
            params: Motor parameters.
            locked: Whether the shaft is held still by the torque
                sensor (as in the torque-constant test).
            lock_angle_rad: Shaft angle at the start, and where it is
                held if locked.
        """
        self.params = params
        self.locked = locked
        self.angle_rad = lock_angle_rad
        self.speed_rad_s = 0.0

    def cogging_nm(self) -> float:
        """Return the cogging torque at the current angle."""
        p = self.params
        return -p.cogging_amplitude_nm * math.sin(
            p.cogging_order * self.angle_rad
        )

    def shaft_torque_nm(self, iq_a: float) -> float:
        """Return the torque the shaft passes to the torque sensor.

        When locked, the sensor holds the rotor against the motor's
        torque and the cogging torque. When free, nothing is attached.
        """
        if not self.locked:
            return 0.0
        return self.params.kt_nm_a * iq_a + self.cogging_nm()

    def update(self, iq_a: float, dt_s: float) -> None:
        """Advance the shaft by one step, given the motor current.

        Uses semi-implicit Euler: the new speed is used to move the
        angle. Static friction holds the rotor until the driving
        torque exceeds it, and friction can stop the rotor but never
        reverse it.
        """
        if self.locked:
            return
        p = self.params
        driving_nm = p.kt_nm_a * iq_a + self.cogging_nm()
        speed = self.speed_rad_s
        if speed == 0.0 and abs(driving_nm) <= p.coulomb_friction_nm:
            return
        direction = math.copysign(1.0, speed if speed != 0.0 else driving_nm)
        friction_nm = (
            direction * p.coulomb_friction_nm
            + p.viscous_friction_nm_s_rad * speed
        )
        new_speed = speed + dt_s * (driving_nm - friction_nm) / (
            p.inertia_kg_m2
        )
        if speed != 0.0 and new_speed * speed < 0.0:
            new_speed = 0.0
        self.speed_rad_s = new_speed
        self.angle_rad += dt_s * new_speed


class SimMotorDrive(MotorDrive):
    """Simulated drive with a current loop and a PI speed loop."""

    VBUS_V = 36.0
    """Bus voltage reported in every state (no bus model yet)."""

    TEMP_C = 25.0
    """Motor temperature reported in every state (no thermal model)."""

    SPEED_BANDWIDTH_HZ = 10.0
    """Target bandwidth for tuning the speed loop."""

    def __init__(
        self,
        motor: SimMotor,
        now_s: Callable[[], float],
        rng: np.random.Generator,
        measurement: MeasurementParams,
        dt_s: float,
    ) -> None:
        """Create a disabled drive.

        Args:
            motor: The motor this drive powers.
            now_s: Returns the current time, for timestamps.
            rng: Random generator for measurement noise.
            measurement: Noise settings.
            dt_s: Simulation step, used to discretize the loops.
        """
        self._motor = motor
        self._now_s = now_s
        self._rng = rng
        self._measurement = measurement
        p = motor.params
        self._limit_a = p.peak_current_a
        # Exact discretization of a first-order lag: stable for any
        # step, unlike forward Euler.
        self._alpha = 1.0 - math.exp(-p.current_bandwidth_rad_s * dt_s)
        # Speed loop gains: with J * dw/dt = Kt * i, proportional
        # control gives bandwidth Kt * kp / J. The integral corner
        # sits a factor of 5 below, so it removes steady-state error
        # (from friction) without much overshoot.
        bandwidth_rad_s = 2.0 * math.pi * self.SPEED_BANDWIDTH_HZ
        self._kp = bandwidth_rad_s * p.inertia_kg_m2 / p.kt_nm_a
        self._ki = self._kp * bandwidth_rad_s / 5.0
        self._mode: Literal["off", "current", "velocity"] = "off"
        self._iq_cmd_a = 0.0
        self._speed_cmd_rad_s = 0.0
        self._integral_rad = 0.0
        self.iq_a = 0.0
        """Actual q-axis current flowing in the motor."""

    def enable(self) -> None:
        """Energize the motor, starting from zero current."""
        self._mode = "current"
        self._iq_cmd_a = 0.0

    def disable(self) -> None:
        """De-energize the motor. Safe to call more than once.

        The phases float, so the current decays to zero. (Above about
        Kv x Vbus a real drive's diodes would brake the motor; that
        isn't modelled.)
        """
        self._mode = "off"

    def set_current(self, iq_a: float) -> None:
        """Command a current, clamped to the motor's peak current.

        Raises:
            RuntimeError: If the drive isn't enabled.
        """
        self._require_enabled()
        self._mode = "current"
        self._iq_cmd_a = max(-self._limit_a, min(self._limit_a, iq_a))

    def set_velocity(self, speed_rad_s: float) -> None:
        """Command a shaft speed, held by the PI speed loop.

        Raises:
            RuntimeError: If the drive isn't enabled.
        """
        self._require_enabled()
        if self._mode != "velocity":
            self._integral_rad = 0.0  # start the loop fresh
        self._mode = "velocity"
        self._speed_cmd_rad_s = speed_rad_s

    def read_state(self) -> DriveState:
        """Return a snapshot, with current noise and encoder counts."""
        count_rad = 2.0 * math.pi / self._motor.params.encoder_cpr
        counts = round(self._motor.angle_rad / count_rad)
        noise_a = self._rng.normal(0.0, self._measurement.current_noise_a)
        return DriveState(
            t_s=self._now_s(),
            iq_a=self.iq_a + noise_a,
            speed_rad_s=self._motor.speed_rad_s,
            angle_rad=counts * count_rad,
            vbus_v=self.VBUS_V,
            temp_c=self.TEMP_C,
        )

    def update(self, dt_s: float) -> None:
        """Advance the current and speed loops by one step."""
        if self._mode == "off":
            target_a = 0.0
        elif self._mode == "current":
            target_a = self._iq_cmd_a
        else:
            target_a = self._speed_loop_a(dt_s)
        self.iq_a += self._alpha * (target_a - self.iq_a)

    def _speed_loop_a(self, dt_s: float) -> float:
        """Return the current command from the PI speed loop.

        The integral only grows while the output isn't at the current
        limit, so it can't wind up (Lecture 17's integrator windup).
        """
        error = self._speed_cmd_rad_s - self._motor.speed_rad_s
        integral = self._integral_rad + error * dt_s
        command_a = self._kp * error + self._ki * integral
        if abs(command_a) <= self._limit_a:
            self._integral_rad = integral
            return command_a
        held_a = self._kp * error + self._ki * self._integral_rad
        return max(-self._limit_a, min(self._limit_a, held_a))

    def _require_enabled(self) -> None:
        if self._mode == "off":
            raise RuntimeError("enable() the drive before commanding it")


class SimTorqueSensor(TorqueSensor):
    """Simulated torque sensor that buffers samples, like the hub."""

    def __init__(
        self,
        rng: np.random.Generator,
        measurement: MeasurementParams,
        dt_s: float,
    ) -> None:
        """Create an empty sensor.

        Args:
            rng: Random generator for measurement noise.
            measurement: Noise, offset and buffer settings.
            dt_s: Time between samples.
        """
        self._rng = rng
        self._measurement = measurement
        self._dt_s = dt_s
        size = round(measurement.buffer_s / dt_s)
        self._t_s = np.zeros(size)
        self._raw_nm = np.zeros(size)
        self._next = 0
        self._count = 0
        self._zero_nm = 0.0

    def record(self, t_s: float, torque_nm: float) -> None:
        """Take one sample of the true shaft torque.

        Adds the sensor's offset and noise, then stores the reading,
        overwriting the oldest one once the buffer is full.
        """
        m = self._measurement
        noise_nm = self._rng.normal(0.0, m.torque_noise_nm)
        self._t_s[self._next] = t_s
        self._raw_nm[self._next] = torque_nm + m.torque_offset_nm + noise_nm
        self._next = (self._next + 1) % self._t_s.size
        self._count = min(self._count + 1, self._t_s.size)

    def tare(self) -> None:
        """Zero the sensor using the last ``tare_window_s`` of samples.

        Raises:
            RuntimeError: If less than ``tare_window_s`` is buffered.
        """
        n = self._samples_in(self._measurement.tare_window_s)
        if n > self._count:
            raise RuntimeError("not enough samples to tare: wait first")
        self._zero_nm = float(np.mean(self._raw_nm[self._latest(n)]))

    def read_block(self, duration_s: float) -> TorqueSeries:
        """Return the samples from the last ``duration_s`` seconds.

        Raises:
            ValueError: If the duration is under one sample, or longer
                than what has been buffered.
        """
        n = self._samples_in(duration_s)
        if n < 1:
            raise ValueError("duration_s is shorter than one sample")
        if n > self._count:
            buffered_s = self._count * self._dt_s
            raise ValueError(f"only {buffered_s:.3f} s is buffered")
        index = self._latest(n)
        return TorqueSeries(
            t_s=self._t_s[index],
            torque_nm=self._raw_nm[index] - self._zero_nm,
        )

    def _samples_in(self, duration_s: float) -> int:
        return round(duration_s / self._dt_s)

    def _latest(self, n: int) -> NDArray[np.intp]:
        """Return where the newest ``n`` samples are, oldest first."""
        return (self._next - n + np.arange(n)) % self._t_s.size


class SimBench:
    """A simulated test bench: motor, drive, torque sensor and clock.

    Built by composition (Lecture 18): the bench has a motor, a drive,
    a sensor and a clock, and each step advances them in order.
    """

    def __init__(
        self,
        params: MotorParams = BOTWHEEL,
        measurement: MeasurementParams = DEFAULT_MEASUREMENT,
        *,
        locked: bool = True,
        lock_angle_rad: float = 0.0,
        seed: int = 0,
        dt_s: float = 1e-3,
    ) -> None:
        """Create the bench at rest, with the drive disabled.

        Args:
            params: Motor parameters.
            measurement: Sensor settings.
            locked: Whether the shaft is locked to the torque sensor.
            lock_angle_rad: Starting (or locked) shaft angle.
            seed: Seed for all measurement noise, so a run can be
                repeated exactly.
            dt_s: Simulation step, which is also the sample period.
        """
        drive_rng, sensor_rng = np.random.default_rng(seed).spawn(2)
        self.motor = SimMotor(
            params, locked=locked, lock_angle_rad=lock_angle_rad
        )
        self.clock = SimClock(self._step, dt_s)
        self.drive = SimMotorDrive(
            self.motor, self.clock.now_s, drive_rng, measurement, dt_s
        )
        self.torque_sensor = SimTorqueSensor(sensor_rng, measurement, dt_s)

    def _step(self, dt_s: float) -> None:
        """Advance everything by one step, then take a sample."""
        self.drive.update(dt_s)
        self.motor.update(self.drive.iq_a, dt_s)
        self.torque_sensor.record(
            self.clock.now_s(), self.motor.shaft_torque_nm(self.drive.iq_a)
        )
