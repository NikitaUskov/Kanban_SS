"""Reusable input normalization without changing user-authored formatting."""

import re

_SPACE_RUN = re.compile(r"[ \t]+")


def clean_single_line(value: str) -> str:
    """Trim a title and collapse horizontal whitespace."""

    return _SPACE_RUN.sub(" ", value.strip())


def clean_optional_text(value: str | None) -> str | None:
    """Trim outer whitespace while preserving internal lines."""

    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None
