"""Shared pytest fixtures for cv_pipeline tests."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# sys.path injection so test files can do `from cv_pipeline import ...`
# despite the hyphenated parent directory (tennis-match-video-editing)
sys.path.insert(0, str(Path(__file__).resolve().parents[1].parent))  # ...editing/
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))         # ...editing/cv_pipeline/

DATA_DIR = Path(__file__).parent / "data"


@pytest.fixture(scope="session")
def data_dir() -> Path:
    return DATA_DIR


@pytest.fixture
def tmp_job_dir(tmp_path: Path) -> Path:
    """A fresh empty job directory for one test."""
    job = tmp_path / "job"
    job.mkdir()
    return job
