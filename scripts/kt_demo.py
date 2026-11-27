"""Run the torque-constant test on the simulated BotWheel and plot it.

Usage: uv run python scripts/kt_demo.py

AI usage: drafted with Claude; reviewed and edited by me.
"""

from pathlib import Path

from motorbench.procedure import Rig
from motorbench.sim import BOTWHEEL, SimBench
from motorbench.torque_constant import TorqueConstantTest, plot_torque_constant


def main() -> None:
    """Run the test, print the result and save the plot."""
    bench = SimBench(seed=1)
    rig = Rig(drive=bench.drive, torque=bench.torque_sensor, clock=bench.clock)
    result = TorqueConstantTest().run(rig)
    error_pct = 100 * (result.kt_nm_a / BOTWHEEL.kt_nm_a - 1)
    print(
        f"Kt = {result.kt_nm_a:.4f} ± {result.kt_ci95_nm_a:.4f} N·m/A (95%),"
        f" R² = {result.r_squared:.5f}"
    )
    print(f"True Kt = {BOTWHEEL.kt_nm_a} N·m/A, error {error_pct:+.2f}%")
    out = Path("results")
    out.mkdir(exist_ok=True)
    plot_torque_constant(result, out / "torque_constant_sim.png")
    print(f"Plot saved to {out / 'torque_constant_sim.png'}")


if __name__ == "__main__":
    main()
