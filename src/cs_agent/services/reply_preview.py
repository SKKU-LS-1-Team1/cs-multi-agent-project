"""Bind a customer-language preview to its exact source and evidence context."""

import hashlib
import json
from typing import Any

from pydantic import BaseModel

from cs_agent.agents.drafting import _ref, customer_text
from cs_agent.schemas import ReviewIn


def _json(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    return str(value)


def target_language(state: dict) -> str:
    inquiry = state["inquiry"]
    extraction = state.get("extraction")
    return inquiry.language or (extraction.language if extraction else None) or "en"


def context_key(state: dict) -> str:
    fields = (
        "inquiry",
        "classification",
        "extraction",
        "evidence",
        "pending",
        "customer_revision",
        "specialist_revision",
        "specialist_followup",
        "specialist_requests",
        "information_review",
        "draft",
        "info_request",
    )
    payload = {key: state.get(key) for key in fields}
    return hashlib.sha256(
        json.dumps(payload, default=_json, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def valid_preview(state: dict, text: str, preview_id: str | None) -> bool:
    preview = state.get("reply_preview") or {}
    final_text = str(preview.get("final_text") or "")
    return bool(
        preview_id
        and preview.get("preview_id") == preview_id
        and preview.get("source_text") == text
        and preview.get("target_language") == target_language(state)
        and preview.get("context_key") == context_key(state)
        and final_text.strip()
        and customer_text(final_text, [_ref(e) for e in state.get("evidence", [])]) == final_text
    )


def review_text(state: dict, review: ReviewIn) -> str:
    if review.action == "edit_approve":
        text = review.edited_text or ""
    elif state.get("pending") == "info_request":
        text = (
            (
                state.get("approved_reply")
                if state.get("translation_error") or state.get("approval_error")
                else None
            )
            or state.get("info_request")
            or ""
        )
    else:
        draft = state.get("draft")
        text = (
            state.get("approval_text")
            or (state.get("approved_reply") if state.get("translation_error") else None)
            or (draft.text if draft else "")
        )
    return customer_text(text, [_ref(e) for e in state.get("evidence", [])])
