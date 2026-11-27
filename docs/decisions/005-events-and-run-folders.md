# 005. Progress events and run folders

- Status: Accepted
- Date: 2026-11-27

## Context

Until now a procedure's `run()` returned its data only at the end. Two things need data while a test is running:

- the GUI's live plot (decision 004), and
- a log on disk that keeps everything, including all raw samples, so a run can be re-analyzed later and a crash doesn't lose finished trials.

Each run also has to record its test conditions. Torres et al. (2026) argue that fair comparisons need "the test conditions, normalization criteria, and processing methods" to be "explicitly reported" (p. 2).

## Options

### How a running procedure reports data

| Option | For | Against |
| --- | --- | --- |
| Return everything at the end (current) | Simplest | No live plot; a crash loses the whole run |
| The GUI reads the devices itself | No change to procedures | Two readers of one drive; the GUI starts running the test |
| The procedure sends events to a sink it is given | Procedures stay unaware of files and windows; any number of listeners | One more small interface |

### File format

| Option | For | Against |
| --- | --- | --- |
| CSV for data, JSON for settings and results | Opens in Excel, MATLAB and a text editor; readable diffs; no new packages | Larger and slower than binary formats |
| Parquet | Compact, typed | Needs pyarrow, a large dependency; not human-readable |
| HDF5 | One file, compact | Needs h5py; not human-readable |
| NumPy `.npz` or pickle | Easy from Python | Python-only; pickle can run code when loaded |

### When to write

Options: at the end of the run, or as events arrive (streaming).

## Decision

- **Events and sinks (observer pattern).** A procedure's `run()` takes an `EventSink` and calls `emit(event)` as data arrives. Sinks:
  - `RunFolder` writes to disk;
  - `ListSink` collects events for tests;
  - `FanOut` passes each event to several sinks (the run folder and the GUI);
  - the GUI's queue sink (PR F).

  If no sink is given, a null sink that ignores events is used, so tests and scripts don't need one.
- **Event types**, as frozen dataclasses:
  - `TorqueSamples`: raw torque samples;
  - `DriveStates`: raw drive snapshots;
  - `TrialRow`: one row of per-trial results;
  - `Progress`: steps done and a message.
- **Every procedure also provides** `summary(result)` (the headline numbers) and `plot(result, path)`.
- **Run folder:** `runs/<date>_<time>_<test>/`, written as events arrive:

  | File | Contents |
  | --- | --- |
  | `run.json` | Test name and settings (including the seed), motorbench version, git commit, Python version, rig description (for the simulator, its motor parameters), current convention (ODrive: q-axis current equals peak phase current), start and end times |
  | `torque_samples.csv` | Every raw torque sample the procedure read: `t_s, torque_nm` |
  | `drive_states.csv` | Every drive snapshot: `t_s, iq_a, speed_rad_s, angle_rad, vbus_v, temp_c` |
  | `trials.csv` | One row per trial |
  | `summary.json` | Headline results, such as Kt, its 95% interval and R² |
  | `plot.png` | The result plot |

- **The torque-constant test reads each whole 9 s trial**, both torque and drive states, and averages only the samples whose timestamps fall in the middle 7 s, as Lee et al. (2019, §II-B-1) describe. All 9 s are saved.
- Numbers are written with Python's shortest exact form, so reading a CSV back gives exactly the same values.

## Consequences

- Procedures must emit everything they read, so the run folder holds all raw data.
- A crash keeps every trial finished before it, because files are written as events arrive.
- Disk use: about 9 MB per torque-constant run (495,000 torque samples); about 60–70 MB per hour of 1 kHz data. `runs/` is ignored by git.
- `run()`, `execute()` and every procedure gain an `events` argument, and every procedure must implement `summary()` and `plot()`.
- The GUI (PR F) adds a queue sink. The safety layer (decision 006) can report stops through the same events.
- Any run can be re-analyzed later from its CSV files, in Python, Excel or MATLAB.

## References

- Torres Rodríguez, I. J., et al. (2026). Toward reproducible actuator characterization: a comprehensive framework for robotics applications. *Actuators*, 15(6), 301. https://doi.org/10.3390/act15060301. p. 2.
- Lee, U. H., Pan, C.-W., & Rouse, E. J. (2019). Empirical characterization of a high-performance exterior-rotor type brushless DC motor and drive. *IEEE/RSJ IROS*, 8018–8025. §II-B-1, p. 20 of the combined PDF.
- Gao, J. (2026). *GUI Design: a Robot Arm Jog Panel* (MECH 410G Lecture 19): model separated from the view.

---

AI usage: options researched and text drafted with Claude; I made the decisions and reviewed the text.
