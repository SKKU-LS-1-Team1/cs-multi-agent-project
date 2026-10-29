"""이관 후 조사: 회신 근거와 담당자 확인을 체크포인트에 보존한다."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1200)]
Stage = Literal["triage", "serial_trace", "impact_assessment", "reproduction_test"]


class ReplyReference(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reply_id: str
    evidence: Text


class InvestigationStep(ReplyReference):
    stage: Stage
    status: Literal["in_progress", "completed"]


class RequestedField(ReplyReference):
    field: str


class FollowupReading(BaseModel):
    model_config = ConfigDict(extra="forbid")
    steps: list[InvestigationStep] = Field(default_factory=list, max_length=12)
    requested_fields: list[RequestedField] = Field(default_factory=list, max_length=20)
    conclusion: ReplyReference | None = None
    needs_review: bool = True


class FollowupConfirmation(BaseModel):
    source_version: str
    reviewer: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
    finding: ReplyReference
