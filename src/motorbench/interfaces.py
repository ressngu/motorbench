"""Hardware interfaces that every test procedure talks to.

Decision record 001 explains the choices. Each device (the simulator,
an ODrive, the sensor hub) implements one of these abstract base
classes, so a procedure runs unchanged on any of them.

AI usage: drafted with Claude; reviewed and edited by me.
"""

import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray


class RunStoppedError(Exception):
    """Raised inside a procedure when someone asks the run to stop."""


@dataclass(frozen=True)
class DriveState:
    """Snapshot of a motor drive's measurements at one instant.

    Attributes:
        t_s: Time of the snapshot, from the run's clock.
        iq_a: Measured q-axis current. ODrive convention: equal to
            the peak phase current.
        speed_rad_s: Shaft speed.
        angle_rad: Shaft angle.
        vbus_v: DC bus voltage.
        temp_c: Motor temperature.
    """

    t_s: float
    iq_a: float
    speed_rad_s: float
    angle_rad: float
    vbus_v: float
    temp_c: float


@dataclass(frozen=True, eq=False)
class TorqueSeries:
    """Raw torque samples from the torque sensor.

    Attributes:
        t_s: Sample times, from the run's clock.
        torque_nm: Torque at each sample time.
    """

    t_s: NDArray[np.float64]
    torque_nm: NDArray[np.float64]

    def __post_init__(self) -> None:
        """Check that every sample has a time.

        Raises:
            ValueError: If the two arrays have different shapes.
        """
        if self.t_s.shape != self.torque_nm.shape:
            raise ValueError("t_s and torque_nm must have the same shape")


class MotorDrive(ABC):
    """A motor drive: the motor under test's, or the absorber's."""

    @abstractmethod
    def enable(self) -> None:
        """Energize the motor so it follows commands."""

    @abstractmethod
    def disable(self) -> None:
        """De-energize the motor and leave its phases floating.

        Must be safe to call more than once.
        """

    @abstractmethod
    def set_current(self, iq_a: float) -> None:
        """Command a q-axis current (torque control)."""

    @abstractmethod
    def set_velocity(self, speed_rad_s: float) -> None:
        """Command a shaft speed (velocity control)."""

    @abstractmethod
    def read_state(self) -> DriveState:
        """Return a snapshot of the drive's measurements."""


class TorqueSensor(ABC):
    """A torque sensor that buffers timestamped samples."""

    @abstractmethod
    def tare(self) -> None:
        """Zero the sensor. Call with no load on the shaft."""

    @abstractmethod
    def read_block(self, duration_s: float) -> TorqueSeries:
        """Return the samples from the last ``duration_s`` seconds.

        Doesn't wait: only ``Clock.wait()`` lets time pass.
        """


class Clock(ABC):
    """The run's sense of time, real or simulated."""

    def __init__(self) -> None:
        """Start with no stop requested."""
        self._stop = threading.Event()

    def request_stop(self) -> None:
        """Ask the running procedure to stop at its next wait.

        Safe to call from another thread, such as the GUI's.
        """
        self._stop.set()

    @property
    def stop_requested(self) -> bool:
        """Whether a stop has been requested."""
        return self._stop.is_set()

    @abstractmethod
    def now_s(self) -> float:
        """Return seconds since the run started."""

    @abstractmethod
    def wait(self, duration_s: float) -> None:
        """Let ``duration_s`` seconds pass.

        Raises:
            RunStoppedError: If a stop was requested before or while
                waiting.
        """
