import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    """Fully isolate the test run from the developer's machine.

    Both credential sources are redirected into tmp_path: PA_HOME for our own
    store, and LEGACY_MCP_DIRS for the MCP fallback. Without the second, these
    tests would pass or fail depending on whether the person running them
    happens to have the MCP servers installed.
    """
    from pa import config

    monkeypatch.setenv("PA_HOME", str(tmp_path / "pa"))
    monkeypatch.delenv("PA_ACCOUNT", raising=False)
    monkeypatch.setenv("TZ", "Australia/Melbourne")
    monkeypatch.setattr(config, "LEGACY_MCP_DIRS",
                        {name: tmp_path / f"absent-{name}-mcp"
                         for name in ("gmail", "calendar")})
    yield


@pytest.fixture
def fixed_tz(monkeypatch):
    from pa import config

    monkeypatch.setattr(config, "default_timezone", lambda: "Australia/Melbourne")
