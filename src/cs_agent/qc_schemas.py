"""Customer-facing QC results; stored as dictionaries in existing checkpoints."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class QcIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")
    paragraph_id: str = Field(pattern=r"^p[1-9]\d*$")
    category: Literal["ABUSE", "CREDENTIAL", "CONFIDENTIAL"]
    source_id: str | None = None


class QcDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: Literal["PASS", "BLOCK", "REVIEW"]
    issues: list[QcIssue] = Field(max_length=30)

    @model_validator(mode="after")
    def consistent(self):
        if (self.decision == "PASS") != (not self.issues):
            raise ValueError("PASS must have no issues; other decisions must have issues")
        return self


class QcResult(BaseModel):
    decision: Literal["PASS", "BLOCK", "REVIEW", "ERROR"]
    issues: list[dict] = Field(default_factory=list)
    message: str = ""
    text_hash: str = ""
