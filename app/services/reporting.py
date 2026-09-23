"""Logging shared by the analysis services."""

import logging

from app.domain.models import VerificationReport

logger = logging.getLogger(__name__)


def log_verification(operation: str, report: VerificationReport) -> None:
    """Record how much of a result survived verification. Metadata only.

    Args:
        operation: Which analysis produced the report.
        report: What verification made of it.
    """
    logger.info(
        "verification",
        extra={
            "operation": operation,
            "total": report.total,
            "verified": report.verified,
            "removed": report.removed_count,
        },
    )
