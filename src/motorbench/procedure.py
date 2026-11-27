"""Base class for every test procedure, and the rig it runs on.

Each test subclasses ``TestProcedure`` and fills in two steps:
``execute()`` drives the rig and collects data, and ``analyze()``
turns that data into a result. ``run()`` calls them in order and
always disables the drive afterwards, even if something goes wrong.
That's the template method pattern from Lecture 18.

AI usage: drafted with Claude; reviewed and edited by me.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass

from motorbench.interfaces import Clock, MotorDrive, TorqueSensor


@dataclass(frozen=True)
class Rig:
    """The devices a procedure uses."""

    drive: MotorDrive
    torque: TorqueSensor
    clock: Clock


class TestProcedure[DataT, ResultT](ABC):
    """A test: collect data on a rig, then analyze it.

    ``DataT`` is what ``execute()`` collects and ``ResultT`` is what
    ``analyze()`` returns, so each test keeps its own precise types.
    """

    __test__ = False  # tells pytest this isn't a test class

    def run(self, rig: Rig) -> ResultT:
        """Run the test and return its result.

        The drive is disabled afterwards, whether the test finished,
        failed or was stopped.
        """
        try:
            data = self.execute(rig)
        finally:
            rig.drive.disable()
        return self.analyze(data)

    @abstractmethod
    def execute(self, rig: Rig) -> DataT:
        """Drive the rig and collect raw data."""

    @abstractmethod
    def analyze(self, data: DataT) -> ResultT:
        """Turn raw data into a result, without touching the rig."""
