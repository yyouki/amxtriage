import os
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
EXAMPLES = ROOT / "examples"
FIXTURES = Path(__file__).resolve().parent / "fixtures"

CliRunner = Callable[..., "subprocess.CompletedProcess[bytes]"]


@pytest.fixture
def sample_log() -> Path:
    return EXAMPLES / "sample_server_log.txt"


@pytest.fixture
def sample_sources() -> Path:
    return EXAMPLES / "gamemodes"


@pytest.fixture
def run_cli() -> CliRunner:
    def run(
        *args: str, input_bytes: bytes | None = None, cwd: Path | None = None
    ) -> "subprocess.CompletedProcess[bytes]":
        env = dict(os.environ)
        env["PYTHONPATH"] = str(SRC)
        env["PYTHONIOENCODING"] = "utf-8"
        return subprocess.run(
            [sys.executable, "-m", "amxtriage", *args],
            input=input_bytes,
            capture_output=True,
            env=env,
            cwd=cwd,
            timeout=120,
            check=False,
        )

    return run
