
# MECH 410G Project: Motor Test Bench Software

**Goal:** Build a python application that runs characterization tests on brushless motors and analyzes the results.

**Approval status:** Proposal was approved by Jian and I am allowed to proceed independently. However, I am required to use feature branches and submit pull requests for all repository changes.

Tests should follow published brushless motor and actuator characterization methods, with:

- common interfaces for motor drives and torque sensors, with a simulated motor so everything runs without hardware;
- scripted tests for torque constant, back-EMF, cogging, and frequency response, each logged with its test conditions; and
- analysis with FFTs and frequency-response estimates (Bode and Nyquist plots), reporting each parameter with its uncertainty.

The testing protocol is especially motivated by the following papers:

1. Lee, U. H., Pan, C.-W., & Rouse, E. J. (2019). Empirical characterization of a high-performance exterior-rotor type brushless DC motor and drive. IEEE/RSJ IROS, 8018–8025.
2. Torres Rodríguez, I. J., et al. (2026). Toward reproducible actuator characterization: a comprehensive framework for robotics applications. Actuators 15(6), 301. doi.org/10.3390/act15060301.

## Development

Requires [uv](https://docs.astral.sh/uv/). From the repository folder:

```
uv sync               # create .venv and install everything from uv.lock
uv run ruff check     # lint
uv run ruff format    # format
uv run mypy           # type check
uv run pytest --cov   # tests with coverage (must stay at or above 85%)
```

Design decisions are recorded in [docs/decisions](docs/decisions).

## AI usage

I use Claude to research options, explain trade-offs and draft some files and decision records. I make the design decisions, review every change in a pull request, and note AI involvement at the top of each file.
