"""Guard: nothing in the test suite may place a real phone call.

Repository rule, and a practical one — the account has a hard call budget and a
live call reaches a real person. A test that dials would burn both silently.

Refs #19.
"""

from __future__ import annotations

import re
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[1]
TESTS = APP_ROOT / "tests"

# Anything that would reach CALL-E for real.
DIALS = re.compile(
    r"\bCalleClient\b|\bcreate_and_wait\b|\brun_call\b"
    r"|calle\s+call\s+(start|run)|--execute\b|api\.heycall-e\.com",
)


def test_no_test_file_can_place_a_call():
    offenders = []
    for path in sorted(TESTS.glob("*.py")):
        if path.name == Path(__file__).name:
            continue  # this file defines the pattern, so it always contains it
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if line.lstrip().startswith("#"):
                continue
            if DIALS.search(line):
                offenders.append(f"{path.name}:{n}: {line.strip()}")
    assert not offenders, "tests must never place a call:\n" + "\n".join(offenders)


def test_suite_declares_no_network_dependency():
    """The app itself must stay installable and runnable with nothing extra."""
    pyproject = (APP_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert "dependencies = []" in pyproject
