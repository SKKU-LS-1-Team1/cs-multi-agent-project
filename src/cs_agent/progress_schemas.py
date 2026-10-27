"""Staff-reviewed customer progress notices, separate from ticket replies and dispatch."""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, Field, StringConstraints, field_validator

TicketID = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
NoticeText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=8000)]


class ProgressNoticeIn(BaseModel):
    notice_id: UUID
    ticket_ids: list[TicketID] = Field(min_length=1, max_length=10)

    @field_validator("ticket_ids")
    @classmethod
    def unique_tickets(cls, values: list[str]) -> list[str]:
        if len(values) != len(set(values)):
            raise ValueError("Duplicate ticket IDs are not allowed")
        return sorted(values)


class ProgressApprovalIn(BaseModel):
    reviewer: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
    edited_text: NoticeText


class ProgressNotice(BaseModel):
    notice_id: UUID
    anchor_ticket_id: str
    ticket_ids: list[str]
    customer_id: str
    target_language: str
    source_version: str
    source_facts: list[dict]
    status: Literal["draft", "prepared"] = "draft"
    draft_text: str | None = None
    approved_text: str | None = None
    final_text: str | None = None
    reviewer: str | None = None
    created_at: datetime
    approved_at: datetime | None = None
    error: str | None = None
    customer_qc: dict | None = None
