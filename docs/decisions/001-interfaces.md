# 001. Hardware interfaces for test procedures

- Status: Accepted
- Date: 2026-11-26

## Context

The test procedures (torque constant first, then back-EMF) must run against a simulated motor now, and against the real rig (ODrive S1 drives and an STM32 sensor hub) after the course. I want to write each procedure once and run it on either without changes.

To work out what the software must be able to ask the hardware to do, I walked through the torque-constant and back-EMF tests in Lee et al. (2019), §II-B-1 "Torque / Back-EMF constant". The torque-constant walk-through is at the end of this record.

## Options

### How procedures reach the hardware

1. **Scripts that call the ODrive library directly.** Fastest to start, but nothing runs without hardware attached, and every script repeats the setup code.
2. **One big `Rig` class with every method.** One place to look, but a simulator would have to copy the whole class, and every procedure depends on every device.
3. **A small interface per device (drive, torque sensor, clock).** Procedures only use the interfaces, so a simulated class and a hardware class can be swapped in. Costs more classes and files.

### How the interfaces are defined in Python

1. **Abstract base class (`abc.ABC` with `@abstractmethod`).** Each device class inherits from its interface. Python refuses to create an object that is missing a method, as soon as the code runs. Shows up as inheritance in a class diagram.
2. **`typing.Protocol`.** No inheritance: any class with matching methods fits. A missing method is only caught by a type checker (mypy), not when the code runs. Useful for fitting classes I can't edit, such as a library's.
3. **Duck typing (no interface).** Least code, but nothing documents or checks what a device must provide.

### Smaller choices within the interfaces

| Question | Options considered | Chosen | Why |
| --- | --- | --- | --- |
| How a procedure lets time pass | Read the time and loop until enough has passed; or a `Clock` with `wait()` | `Clock.wait(duration_s)` | A loop on simulated time never ends, because nothing moves simulated time forward. `wait()` sleeps on hardware and steps the physics in simulation. |
| How torque is read | One sample per call; a block that waits and collects the next N seconds; or a block of the last N seconds from a buffer | `read_block(duration_s)` returns the last `duration_s` of raw samples | Python on Windows can't request samples at an even 1 kHz, so the STM32 hub buffers them with its own timestamps. Returning the last N seconds means only `Clock.wait()` lets time pass. Averaging happens in the analysis, so later tests (cogging FFT) can reuse the raw samples. |
| How drive values are read | Separate getters (`get_current`, `get_speed`, ...); or one snapshot | `read_state() -> DriveState` | All values come from the same instant, it's one CAN round trip instead of several, and adding a field later doesn't change the interface. |
| Which current Kt is fitted against | Commanded; or measured | Log both, fit against measured | Kt is a property of the motor. Measured current differs from the command through the drive's offsets and tracking error, so the gap is a check on the drive, not part of Kt. |
| How back-EMF is measured | Spin freely at a fixed voltage and compute V − i·R (Lee et al., 2019); or spin the motor with the absorber while its phases are open and measure the voltage directly (no-load test, Bojoi & Armando) | Absorber with phases open | With no current in the windings there's no i·R drop, so no separate resistance test is needed first and the drive doesn't need an open-loop voltage mode. |

## Decision

Each device gets its own interface (option 3), defined as an abstract base class. I chose ABCs over Protocols because a missing method fails as soon as the code runs without needing mypy, the inheritance shows in the class diagram, and I write every device class myself, so Protocol's main advantage doesn't apply. If I wrap a library later, I'll write a small adapter class for it.

| Object | Methods |
| --- | --- |
| `MotorDrive` | `enable()`, `disable()`, `set_current(iq_a)`, `set_velocity(speed_rad_s)`, `read_state() -> DriveState` |
| `TorqueSensor` | `tare()`, `read_block(duration_s) -> TorqueSeries` |
| `Clock` | `now_s() -> float`, `wait(duration_s)` |

- The same `MotorDrive` interface is used for the motor under test and for the absorber. The absorber uses `set_velocity` in the back-EMF test.
- `iq_a` is the torque-producing (q-axis) current. In ODrive's convention it equals the peak phase current (conventions explained in Lee et al., 2023).
- `DriveState` is a frozen dataclass (a read-only record) with `t_s`, `iq_a`, `speed_rad_s`, `angle_rad`, `vbus_v` and `temp_c`.
- `tare()` zeros the torque sensor with no load on it.
- `read_block(duration_s)` returns the samples from the last `duration_s` seconds. It doesn't wait itself.
- `now_s()` returns seconds since the run started. On hardware it uses a monotonic clock (Python's `time.monotonic()`), so it can't jump when the PC syncs its clock.

### Naming

Functions use type hints, and variable names end in their unit: `_a` amps, `_v` volts, `_nm` newton-meters, `_s` seconds, `_rad_s` rad/s, `_c` degrees Celsius. For example:

```python
def set_current(self, iq_a: float) -> None: ...  # takes amps, returns nothing
def read_state(self) -> DriveState: ...  # takes nothing, returns a snapshot
```

## Consequences

- Every new device (the simulator, an ODrive S1, the STM32 hub) needs its own class that implements every method of its interface.
- Procedures only let time pass through `Clock.wait()`, never `time.sleep()`, or they will hang in simulation.
- `disable()` must be safe to call twice, because a safety check may call it after a fault has already stopped the motor.
- For the back-EMF test, `disable()` must leave the phases floating, not shorted. They only stay truly open below roughly Kv × Vbus (about 310 rpm at 36 V, 210 rpm at 24 V for the BotWheel). Above that, the drive's diodes conduct and brake the motor.
- Still open:
  - the fields of `TorqueSeries`;
  - what measures the voltage in the back-EMF test (not the motor's own drive; a divider into the STM32 hub's ADC is one option), and its interface. A later record will cover it.

## Worked example: torque-constant procedure

From Lee et al. (2019), §II-B-1:

1. **Before starting:** confirm the shaft is locked and every planned current is within the motor's limits, then `wait(1.0)`, `tare()`, `enable()`.
2. **Plan:** currents from −5 A to +5 A in 1 A steps, five trials each (Lee et al.), in a random order (my addition: random order stops slow drift, like heating, from looking like a trend). ±5 A is within the BotWheel's 5 A continuous rating, so no cool-down rest is needed between trials.
3. **Each trial:**
   1. `set_current(i)`
   2. `wait(1.0)` to let it settle
   3. for 7 s: `wait(0.1)`, then `read_state()` (70 snapshots of measured current)
   4. `read_block(7.0)` to get the torque samples from those same 7 s
   5. `wait(1.0)`, the final second, which the paper also discards
4. **After the last trial**, or on any error: `disable()`.
5. **Analysis:** average torque and measured current within each trial, then across the five trials at each level. Fit a straight line. The slope is Kt, reported with R² (Lee et al.) and a 95% confidence interval (my addition).

_Corrected 2026-11-27: the first version said −10 A to +10 A in 2 A steps, which isn't what Lee et al. used._

## References

- Lee, U. H., Pan, C.-W., & Rouse, E. J. (2019). Empirical characterization of a high-performance exterior-rotor type brushless DC motor and drive. *IEEE/RSJ IROS*, 8018–8025. §II-B-1 "Torque / Back-EMF constant", p. 20 of the combined PDF.
- Lee, U. H., et al. (2023). How to model brushless electric motors for the design of lightweight robotic systems. arXiv:2310.00080. https://arxiv.org/abs/2310.00080
- Bojoi, R., & Armando, E. (n.d.). *Getting the back-EMF voltage constant of permanent magnet motors with just one lap wrist using GEN3i data recorder* [Technical article]. HBM. https://www.Hbm.com/fileadmin/mediapool/files/technical-articles-technotes-white-papers/Power_Analyzer_and_Electric_Power_Testing/Getting_the_Back_Emf_Voltage_Constant_of_Permanent_Magnet_Motors_with_Just_One_Lap_Wrist_using.pdf

---

AI usage: options and wording drafted with Claude from my notes and our discussion; I chose the decisions and reviewed the text.
