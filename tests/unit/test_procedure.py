"""Unit tests for the procedure base class.

The rig is made of mocks (Lecture 17's test doubles), so these tests
check what ``run()`` does without any physics.

AI usage: drafted with Claude; reviewed and edited by me.
"""

from unittest.mock import Mock

import pytest

from motorbench.interfaces import Clock, MotorDrive, TorqueSensor
from motorbench.procedure import Rig, TestProcedure


class Passing(TestProcedure[int, str]):
    def execute(self, rig: Rig) -> int:
        return 42

    def analyze(self, data: int) -> str:
        return f"answer {data}"


class Failing(TestProcedure[int, str]):
    def execute(self, rig: Rig) -> int:
        raise RuntimeError("sensor unplugged")

    def analyze(self, data: int) -> str:
        return "never reached"


def make_rig(drive: Mock) -> Rig:
    return Rig(
        drive=drive, torque=Mock(spec=TorqueSensor), clock=Mock(spec=Clock)
    )


def test_run_executes_then_analyzes_then_disables() -> None:
    drive = Mock(spec=MotorDrive)
    assert Passing().run(make_rig(drive)) == "answer 42"
    drive.disable.assert_called_once()


def test_run_disables_the_drive_when_the_test_fails() -> None:
    drive = Mock(spec=MotorDrive)
    with pytest.raises(RuntimeError, match="unplugged"):
        Failing().run(make_rig(drive))
    drive.disable.assert_called_once()
