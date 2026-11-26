# 001. Hardware interfaces for test procedures

Date: 2026-11-26

## Context

As a first step, I want to work out what the software must be able to ask the hardware to do, specifically for measuring the torque constand and back-EMF constant. These are referenced in section "1) Torque / Back-EMF constant" in (Lee et al., 2019).

## Decisions

For the torque-constant and back-EMF tests, I have written down the methods needed from the three objects: the drive, the torque sensor, and the clock. I 

| Object | Methods |
| --- | --- |
| `MotorDrive` | `enable()`, `disable()`, `set_current(iq_a)`, `set_velocity(speed_rad_s)`, `read_state() -> DriveState` |
| `TorqueSensor` | `tare()`, `read_block(duration_s) -> TorqueSeries` |
| `Clock` | `now_s() -> float`, `wait(duration_s)` |

### Syntax

For function definitions, I will use type-hinted formatting with variable names that include units. For example,

```python
def set_current(self, iq_a: float) -> None: # takes a current (in amps), returns nothing
def get_current(self) -> float: # takes nothing, returns a current
```

Units go at the end of the name: `_a` amps, `_v` volts, `_nm` newton-meters, `_s` seconds, `_rad_s` rad/s, `_c` degrees Celsius.

### Logging both commanded and measured current

Torque constant is a property of the motor, so measured torque is fitted against the measured current that flows through the windings. Measured current differs from the commanded current by small offsets due to the drive's current control, so the gap between commanded and measured current is a check on the drive.

### Dealing with time (clock)

At first, I suggested reading the current time and subtracting the global time at the start of the test. However, this only works when testing on hardware. In simulation, simulated time only moves forward when something steps the model forward. Thus, it is important to step the simulated time. The methods here are:

- `now_s() -> float:` time in seconds since the run started.
- `wait(duration_s: float) -> None`: on the real clock this sleeps, but on the simulated clock it steps time forward by that duration.

### Torque sensor: returning block vs raw individual samples

At first, I thought about the sensor taking one reading at a time, and a function can be used to block samples together to form averages (to follow the procedure of Lee et al., 2019). However, doing so create timing issues due to sampling rate of the microcontroller and communication with python scripts.

Instead, the microcontroller can block readings together and buffer the samples so that python fetches them in batches.

### One method for drive

Instead of separate `get_current`, `get_speed`, and `get_voltage` methods, I can use one method that returns everything at the same instant:

```python
def read_state(self) -> DriveState: ...
# DriveState: t_s, iq_a, speed_rad_s, angle_rad, vbus_v, temp_c
```

One methods instead of several leads to the following advantages:

- All the values come from the same moment.
- It's one CAN message round trip instead of several.
- Adding a field later doesn't change the interface.

`DriveState` would be a frozen dataclass (a read-only record).

### Back-EMF test

The back-EMF test I plan to go with is different from the one discussed in Lee et al., 2019. Lee at al. let's the motor spin freely with a fixed voltage and calculates the back-EMF using applied voltage - i*R. This has two costs: (1) It needs R from a separate test first, and (2) The drive must support a fixed open-loop voltage mode.

Instead, we can use an absorber motor to spin the motor under test. Then, no current flows to spin the motor and no i*R correction is needed, so the voltage can be measured directly. Some methods are needed:

- `set_velocity(speed_rad_s: float) -> None` on whichever drive is acting as the absorber.
- Speed from the motor's encoder (obtained in `read_state`).
- A voltage measurement from something other than the motor's drive.

## The torque-constant procedure

As described in Lee et al., 2019, the torque-constant procedure is:

1. **Before starting:** confirm the shaft is locked, check every planning current is within the motor's limits, `tare()`, `enable()`.
2. **Plan:** currents from -10 A to +10 A in 2 A steps, five trials each, in random order.(Random order stops slow drift, like heating, from looking like a trend.)
3. **Each trial:**
   1. `set_current(i)`
   2. `wait(1.0)` to let it settle
   3. read 7 s of torque and drive states
   4. `wait(1.0)`
   5. `set_current(0)`, then rest so the motor cools.
4. **After last trial**, or on any error: `disable()`.
5. **Analysis:** average torque and measured current within each trial, then across the five trials at each level. Fit a straight line. The slop is Kt, reported with its 95% interval and R^2.

## References

```text
Lee, U. H., Pan, C.-W., & Rouse, E. J. (2019). Empirical characterization of a high-performance exterior-rotor type brushless DC motor and drive. IEEE/RSJ IROS, 8018–8025.
```
