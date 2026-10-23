"""Bind a customer-language preview to its exact source and evidence context."""

import hashlib
import json
from typing import Any

from pydantic import BaseModel

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
    return bool(
        preview_id
        and preview.get("preview_id") == preview_id
        and preview.get("source_text") == text
        and preview.get("target_language") == target_language(state)
        and preview.get("context_key") == context_key(state)
        and str(preview.get("final_text") or "").strip()
    )


def review_text(state: dict, review: ReviewIn) -> str:
    if review.action == "edit_approve":
        return review.edited_text or ""
    if state.get("pending") == "info_request":
        return (
            (state.get("approved_reply") if state.get("translation_error") else None)
            or state.get("info_request")
            or ""
        )
    draft = state.get("draft")
    return (
        state.get("approval_text")
        or (state.get("approved_reply") if state.get("translation_error") else None)
        or (draft.text if draft else "")
    )
