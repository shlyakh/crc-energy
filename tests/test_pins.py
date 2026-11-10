"""Fail loudly if the installed CRC packages drift from the pinned versions (requirement N1)."""

from importlib.metadata import version

from crc_lab import PINNED


def test_crc_versions_are_pinned() -> None:
    for name, expected in PINNED.items():
        assert version(name) == expected, f"{name} is {version(name)}, expected {expected}"
