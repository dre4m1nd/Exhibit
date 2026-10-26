# -*- coding: utf-8 -*-
"""Tests for the agent CLI parser."""

from __future__ import annotations

from agent.app import _build_parser


def test_repo_path_defaults_to_current_directory() -> None:
    args = _build_parser().parse_args([])
    assert args.repo_path == "."


def test_repo_path_accepts_an_arbitrary_project() -> None:
    args = _build_parser().parse_args(
        ["--repo-path", "D:/work/another-project", "--task", "review_repo"]
    )
    assert args.repo_path == "D:/work/another-project"
    assert args.task == "review_repo"
