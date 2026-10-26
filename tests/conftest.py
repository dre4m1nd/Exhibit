# -*- coding: utf-8 -*-
"""Shared test fixtures kept inside the workspace."""

from __future__ import annotations

import shutil
import uuid
from pathlib import Path

import pytest


@pytest.fixture()
def tmp_path() -> Path:
    """Provide a scratch directory inside the repository."""
    target = Path(__file__).parent / ".tmp" / uuid.uuid4().hex
    target.mkdir(parents=True)
    try:
        yield target
    finally:
        shutil.rmtree(target, ignore_errors=True)
