"""Turning key dates into a calendar file."""

from datetime import date
from typing import Annotated

from fastapi import APIRouter
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field

from app.domain.ics import build_calendar

router = APIRouter(tags=["analysis"])

MAX_EVENTS = 50
CALENDAR_MEDIA_TYPE = "text/calendar; charset=utf-8"


class CalendarEvent(BaseModel):
    """One dated obligation to put in a calendar."""

    model_config = ConfigDict(extra="forbid")

    title: Annotated[str, Field(min_length=1, max_length=300)]
    date: date
    description: Annotated[str, Field(max_length=1000)] = ""


class CalendarRequest(BaseModel):
    """The dates to export."""

    model_config = ConfigDict(extra="forbid")

    document_id: Annotated[str, Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")]
    events: Annotated[list[CalendarEvent], Field(min_length=1, max_length=MAX_EVENTS)]


@router.post(
    "/calendar",
    summary="Download key dates as a calendar file",
    description=(
        "Returns an RFC 5545 file of all-day events. Only dates the document states as "
        "calendar dates are included; a period such as 'within 30 days' is explained in "
        "words instead, because turning it into a date would be a guess."
    ),
    response_class=Response,
    responses={200: {"content": {"text/calendar": {}}, "description": "An iCalendar file."}},
)
async def calendar(body: CalendarRequest) -> Response:
    """Build the calendar file."""
    content = build_calendar(
        [(event.title, event.date, event.description) for event in body.events],
        uid_namespace=body.document_id,
    )
    return Response(
        content=content,
        media_type=CALENDAR_MEDIA_TYPE,
        headers={"Content-Disposition": 'attachment; filename="nyayalens-key-dates.ics"'},
    )
