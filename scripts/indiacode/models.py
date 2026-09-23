"""What both readers return."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ExtractedSection:
    """One section, exactly as the source published it.

    Attributes:
        section: The section number, for example ``420`` or ``65B``.
        title: The section's own heading, kept as printed.
        text: The section's text, with page furniture removed and nothing else.
        page: The page it starts on, or ``0`` when the source is not paginated.
        url: The public page a reader can check it against.
    """

    section: str
    title: str
    text: str
    page: int = 0
    url: str = ""
