"""Smoke test: the package installs and its version is consistent.

AI usage: drafted with Claude; reviewed and edited by me.
"""

from importlib.metadata import version

import motorbench


def test_version_matches_installed_metadata() -> None:
    assert motorbench.__version__ == version("motorbench")
