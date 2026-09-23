"""Readers for the two forms in which India Code publishes statutory text.

The new codes (BNS, BNSS, BSA) are published as structured records, one per
section, and are read over India Code's own REST API. The codes they replaced
are no longer published that way: since their repeal on 1 July 2024 only the
consolidated act PDF remains, so those are read from the PDF.

Neither reader rewrites what it finds. Both drop page furniture -- the
watermark, running page numbers, the footnote apparatus -- and nothing else.
"""

from scripts.indiacode.models import ExtractedSection

__all__ = ["ExtractedSection"]
