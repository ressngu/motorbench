# 002. Programming language for the test software

- Status: Accepted
- Date: 2026-11-26

## Context

Decision 001 keeps the time-critical work off the PC: the ODrive closes its own current loop, and the STM32 hub samples torque at 1 kHz and timestamps each sample. That leaves the PC software to:

- plan tests and check their limits;
- send commands at about 10 Hz over USB or CAN;
- collect, log and analyze the data (line fits with confidence intervals, FFTs, frequency responses with coherence, thermal model fits);
- make plots, and run automated tests on every pull request.

So the language doesn't need to be real-time. It needs a good link to the ODrive and strong analysis libraries, and it has to fit two constraints: every change goes through a pull request (MECH 410G), and the software must stay free to use and develop after I graduate.

The papers don't decide this. Lee et al. (2019) recorded torque with a Raspberry Pi that also talked to the drives over USB, then processed the data afterwards. Torres et al. (2026) logged with a Saleae acquisition unit. Neither names a language, but both split logging and analysis the same way.

## Options

| | Python | C# | MATLAB | LabVIEW | C++ |
| --- | --- | --- | --- | --- | --- |
| Talks to the ODrive | Official package, over USB and USB-CAN adapters | Write the CAN messages myself | Write it myself; CAN needs a paid toolbox | Write it myself | Write the CAN messages, or use ODrive's ROS 2 package |
| Analysis libraries | numpy, scipy, matplotlib (free) | MathNet.Numerics, ScottPlot (free, less common) | Built in; frequency response, coherence and fit intervals need paid toolboxes | Built-in blocks | Possible, slow to write |
| Cost to keep developing after graduation | Free | Free | About US$5,300 at list price (MATLAB + Signal Processing + Statistics toolboxes, perpetual) | Paid; the free Community Edition excludes commercial use | Free |
| Pull requests show changed lines | Yes | Yes | `.m` yes, `.mlx` no | No (`.vi` files are binary) | Yes |
| Approved in my project proposal | Yes | No | No | No | No |

I also considered a hybrid: Python runs the rig and writes CSV files, and MATLAB does the analysis. It works, but it means two languages to maintain and still needs MATLAB licences.

## Decision

Python 3.14, the version I use for the MECH 410G assignments.

- It's the only option with an official ODrive library, over both USB and CAN.
- Every analysis the tests need is in free, standard libraries (numpy, scipy, matplotlib).
- It stays free to use and develop after I graduate. MATLAB needs a paid licence once my student access ends, and LabVIEW's free edition excludes commercial use.
- It's slower than compiled languages, but that doesn't matter here: the fast, time-critical work runs on the ODrive and the microcontroller, and numpy does the heavy maths in compiled code.
- Its files are plain text, so every change can be reviewed in a pull request.
- C# matches the course, but Python is allowed and was approved in my proposal, and it's more widely used in robotics, so it's better practice for the work I want to do.

## Consequences

- Type errors only show up when the code runs. Type hints and a type checker (mypy) catch most of them earlier, and automated tests catch the rest. Decision 003 sets these up.
- Python can't keep precise timing on Windows. Decision 001 already handles this: the hub buffers and timestamps the samples, and the PC only sends commands at about 10 Hz.
- The `odrive` package must install on Python 3.14. Its wheels are tagged for any Python from 3.7 up; I'll confirm this when setting up the tooling and pin the version.
- This project won't give me practice in C# (the course language) or LabVIEW (common in actuator test jobs). LabVIEW is worth learning separately.
- The STM32 hub will still need firmware, likely C or C++, to sample the sensors, buffer the data, answer the PC's commands and run the E-stop watchdog. That's out of scope for MECH 410G: the simulator stands in for the hub, and the `TorqueSensor` interface from decision 001 is the contract the firmware will have to meet. Writing that firmware, or buying a data-acquisition board with a Python library instead, is a later decision.
- Report figures will come from matplotlib, not MATLAB.

## References

- Lee, U. H., Pan, C.-W., & Rouse, E. J. (2019). Empirical characterization of a high-performance exterior-rotor type brushless DC motor and drive. *IEEE/RSJ IROS*, 8018–8025. Data acquisition setup on p. 19 of the combined PDF.
- Torres Rodríguez, I. J., et al. (2026). Toward reproducible actuator characterization: a comprehensive framework for robotics applications. *Actuators*, 15(6), 301. https://doi.org/10.3390/act15060301. §3.2 "Hardware Setup".
- ODrive Robotics. Python Package guide. https://docs.odriverobotics.com/v/latest/guides/python-package.html
- ODrive Robotics. CAN Bus guide. https://docs.odriverobotics.com/v/latest/guides/can-guide.html
- MathWorks. Standard perpetual licence prices: MATLAB US$2,625, Signal Processing Toolbox US$1,315, Statistics and Machine Learning Toolbox US$1,375 (checked 2026-11-26). https://www.mathworks.com/store/products/standard/perpetual/
- NI. LabVIEW Community Edition usage details. https://www.ni.com/en/support/documentation/supplemental/20/labview-community-edition-usage-details.html

---

AI usage: options researched with Claude; I made the decision and reviewed the text.