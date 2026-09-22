"""The last gate before a document is written to a file.

Every figure in the finished document must be one the user confirmed, or one
the template itself contains. If a figure appears that is neither, the export
fails rather than handing someone a letter with an invented number in it.
"""

from dataclasses import dataclass
from decimal import Decimal

from app.domain.amounts import digit_values
from app.domain.document_model import DocumentModel


@dataclass(frozen=True, slots=True)
class AuditResult:
    """What the audit found.

    Attributes:
        ok: True when every figure in the document is accounted for.
        unexplained: Figures that are in the document but in neither source.
    """

    ok: bool
    unexplained: tuple[Decimal, ...] = ()

    def describe(self) -> str:
        """Return a user-safe explanation of a failure."""
        if self.ok:
            return ""
        figures = ", ".join(str(value) for value in self.unexplained)
        return (
            f"This draft contains figures that are not among the facts you confirmed: {figures}. "
            "It was not created."
        )


def audit(
    document: DocumentModel, *, confirmed: dict[str, str], template_constants: str = ""
) -> AuditResult:
    """Check every figure in a rendered document.

    Args:
        document: The document about to be written to a file.
        confirmed: The facts the user confirmed.
        template_constants: The template's own text, whose figures are part of
            the template rather than something a model or a user supplied.

    Returns:
        The audit result.
    """
    allowed: set[Decimal] = set(digit_values(template_constants))
    for value in confirmed.values():
        allowed |= digit_values(value)

    unexplained = sorted(digit_values(document.text) - allowed)
    return AuditResult(ok=not unexplained, unexplained=tuple(unexplained))
