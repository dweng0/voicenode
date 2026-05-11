"""Tests for interactive device menu CLI."""
import tempfile
from pathlib import Path
import pytest


def test_cli_parse_choose_input_flag():
    """Test that CLI can parse --choose-input flag."""
    import sys
    from voicenode.cli import parse_args

    # Mock argv with --choose-input
    test_args = ["voicenode", "--choose-input"]
    args = parse_args(test_args[1:])

    assert hasattr(args, "choose_input")
    assert args.choose_input is True


def test_cli_parse_choose_output_flag():
    """Test that CLI can parse --choose-output flag."""
    from voicenode.cli import parse_args

    test_args = ["voicenode", "--choose-output"]
    args = parse_args(test_args[1:])

    assert hasattr(args, "choose_output")
    assert args.choose_output is True
