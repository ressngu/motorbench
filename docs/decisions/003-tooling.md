# 003. Development tooling

- Status: Accepted
- Date: 2026-11-26

## Context

Decisions 001 and 002 settle the design and the language. Before writing code, the project needs:

- one command that sets up an identical environment on my desktop, my laptop, my instructor's machine and the CI servers;
- automatic checks (style, types, tests) on every pull request, since MECH 410G requires pull requests for all changes;
- tests organized the way Lecture 17 describes them: many fast unit tests, software-in-the-loop (SIL) tests against the simulator, and later a few hardware-in-the-loop (HIL) tests on the real rig.

## Options

| Question | Options considered | Chosen | Why |
| --- | --- | --- | --- |
| Folder layout | Flat (code imported from the repo folder, as in the Lecture 17 example `from src.pid import PID`); src layout with an installed package | src layout (`src/motorbench/`) | Python imports from the current folder first, so with a flat layout tests can pass against loose files even when the installed package is broken. With `src/`, tests use the installed copy (PyPA guide). |
| Environment and installs | pip + venv with `requirements.txt` (as in Lecture 17); uv; Poetry; conda | uv | One tool for Python versions, virtual environments and installs, 10–100× faster than pip. Its lockfile (`uv.lock`) records the exact version of every package, so all machines match. It makes a standard `.venv` and reads a standard `pyproject.toml`, so pip still works. |
| Build backend | setuptools; hatchling; uv_build | uv_build | Comes with uv and expects the src layout, so it needs no configuration. |
| Lint and format | ruff; black + flake8 + isort | ruff | One fast tool for both, with the same rules as my assignments repo plus three groups (below). |
| Type checker | mypy; pyright; ty | mypy, strict | The most established checker; ty is still in beta. Starting strict is easier than tightening later. |
| Tests | pytest; unittest | pytest | Used in Lecture 17: plain `assert`, `pytest.approx`, parametrized tests and markers. |
| Coverage | None; pytest-cov with a minimum | pytest-cov, lines and branches, at least 85% | See "Why 85% coverage" below. |
| CI service | Azure DevOps Pipelines (Lecture 17); GitHub Actions; none | GitHub Actions | The repository is on GitHub, and Actions is free for public repositories. It works the same way as the lecture's pipeline: it runs on every push and pull request, shows results on the pull request, and can block merging until the checks pass. |
| CI operating systems | Ubuntu only; Windows and Ubuntu | Both | I develop on Windows, and Ubuntu is the common default, so running both catches path and line-ending differences. |
| Editor settings | Set up on each machine; committed in `.vscode/` | Committed | Both my machines, and anyone who clones the repo, get format-on-save and the same tool versions. |
| Dev container | Yes; no | No | It needs Docker on both machines, and passing USB devices into a container on Windows needs extra tools (usbipd), which would get in the way once the rig is connected. uv and its lockfile already give identical environments. |

## Decision

### Files

- `pyproject.toml`: project details, dependencies and all tool settings.
- `uv.lock`: exact versions of every package (committed).
- `.python-version`: Python 3.14.
- `src/motorbench/`: the package, with `py.typed` to mark it as type-hinted.
- `tests/unit/`, `tests/sil/`, `tests/hil/`: the three test levels from Lecture 17, each created when its first test is written. HIL tests are also marked `@pytest.mark.hil`.
- `.github/workflows/ci.yml`: the CI pipeline.
- `.vscode/settings.json` and `.vscode/extensions.json`: editor settings and recommended extensions.

### Dependencies

- Runtime: numpy, scipy and matplotlib, with minimum versions.
- Development (`dev` group): ruff, mypy, pytest, pytest-cov and scipy-stubs. Their exact versions are fixed by `uv.lock`, so a new tool release can't make CI fail on a pull request that changed nothing.
- Optional (`hardware` extra): the `odrive` package, so CI and anyone using only the simulator don't need it.

### Ruff rules

| Group | What it checks | Status |
| --- | --- | --- |
| `E`, `W`, `F`, `I`, `N`, `D`, `UP`, `B`, `A`, and the comment-style preview rules `E261`, `E262`, `E265`, `E266` | Style, errors, import order, naming, Google docstrings, modern syntax, likely bugs, shadowed built-ins | Kept from my assignments repo |
| `NPY` | NumPy-specific rules | Added: flags old-style `np.random.seed()` in favour of `np.random.default_rng(seed)`, so the simulator's noise can be reproduced from the seed saved with each run |
| `PT` | pytest style | Added: I'm new to pytest, and it points me to the usual patterns |
| `RUF` | Ruff's own bug checks | Added: catches mutable defaults and look-alike characters (such as a Unicode minus "−" pasted from a paper) |
| `PL` | Pylint rules | Rejected: its magic-number rule flags every constant like 0.78 or 1.5, and physics code is full of them |
| `ANN` | Missing type hints | Rejected: mypy strict already requires them, so every warning would appear twice |

Line length is 79 and docstring line length is 72, as in my assignments repo.

### Why 85% coverage

Coverage is the share of lines (and, with branch coverage, both outcomes of each `if`) that run at least once during the tests. It shows which code has never been tested, but as Lecture 17 puts it, "Coverage shows which lines were never executed – it does not prove correctness": a test that runs a function without checking its result still counts.

- Not 100%: some code only runs with hardware attached (the ODrive and hub classes), and the last few percent mostly produce tests written to touch lines rather than to check behaviour. Google's testing team warns that chasing 100% "leads to a false sense of security", and treats 60% as acceptable, 75% as commendable and 90% as exemplary (Arguelles et al., 2020).
- Not lower: at 60%, whole test procedures could go untested.
- 85% sits between commendable and exemplary. It's a floor that CI enforces, not a target: if a pull request drops coverage below it, CI fails and I see the untested code before merging.

### Everyday commands

```
uv sync               # create .venv and install exactly what uv.lock says
uv run ruff check     # lint
uv run ruff format    # format
uv run mypy           # type check
uv run pytest --cov   # tests with coverage
```

## Consequences

- Every pull request must pass linting, formatting, type checking and the tests (with at least 85% coverage) on Windows and Ubuntu. Once CI has run once, these become required checks in the repository's ruleset.
- Libraries are added with `uv add`, never `pip install`, so `uv.lock` stays in step with `pyproject.toml`. CI installs with `uv sync --locked`, which fails if the two disagree.
- Every function needs type hints (mypy strict).
- HIL tests are skipped in CI (`-m "not hil"`). Running them automatically would need a self-hosted runner on the lab PC (Lecture 17's second stage), but GitHub advises against self-hosted runners on public repositories, because a pull request from anyone could run code on that machine. To be decided after the course.
- A nightly run, as in Lecture 17, will be added once there are slow SIL tests.
- If hardware-only code makes 85% unreachable, I'll exclude those modules from coverage explicitly rather than lower the floor.
- The GUI (decision 004) will follow Lecture 19's model–view split, so the model is tested normally and the view stays thin.

## References

- Gao, J. (2026). *Software Testing and Test Pipelines* (MECH 410G Lecture 17): test pyramid (slide 4), test levels (slide 5), pytest and coverage (slide 14), SIL and HIL (slide 16), test pipeline (slides 20–23).
- Python Packaging Authority. src layout vs flat layout. https://packaging.python.org/en/latest/discussions/src-layout-vs-flat-layout/
- Astral. uv documentation. https://docs.astral.sh/uv/
- Astral. ty announcement. https://astral.sh/blog/ty
- Arguelles, C., Ivanković, M., & Bender, A. (2020). Code coverage best practices. Google Testing Blog. https://testing.googleblog.com/2020/08/code-coverage-best-practices.html

---

AI usage: options researched and text drafted with Claude; I made the decisions and reviewed the text.
