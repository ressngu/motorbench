"""Software-in-the-loop test: the full torque-constant procedure.

Runs Lee et al. (2019)'s protocol on the simulated BotWheel, with
sensor noise, and checks that the analysis recovers the true Kt.

AI usage: drafted with Claude; reviewed and edited by me.
"""

import pytest

from motorbench.procedure import Rig
from motorbench.sim import BOTWHEEL, SimBench
from motorbench.torque_constant import TorqueConstantTest


def test_recovers_the_botwheel_torque_constant() -> None:
    bench = SimBench(seed=1)
    rig = Rig(drive=bench.drive, torque=bench.torque_sensor, clock=bench.clock)
    result = TorqueConstantTest().run(rig)

    true_kt = BOTWHEEL.kt_nm_a
    assert result.kt_nm_a == pytest.approx(true_kt, rel=0.02)
    assert abs(result.kt_nm_a - true_kt) < result.kt_ci95_nm_a
    assert result.r_squared > 0.999
    # 1 s to tare, then 55 trials of 9 s, as in the paper
    assert bench.clock.now_s() == pytest.approx(1.0 + 55 * 9.0)
