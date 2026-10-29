from __future__ import annotations

from pathlib import Path

import pytest

from content_agent.executor import ToolExecutor
from content_agent.tools import ToolRuntime


@pytest.fixture
def data_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "data"


@pytest.fixture
def runtime(data_dir: Path, tmp_path: Path) -> ToolRuntime:
    return ToolRuntime(data_dir=data_dir, plans_dir=tmp_path / "saved_plans")


@pytest.fixture
def executor(runtime: ToolRuntime, tmp_path: Path) -> ToolExecutor:
    return ToolExecutor(runtime=runtime, runs_dir=tmp_path / "runs")
