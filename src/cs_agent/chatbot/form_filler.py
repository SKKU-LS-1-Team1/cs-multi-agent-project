"""문의서 작성 에이전트 (CSA-34 · 담당 조수빈).

대화에서 문의서 칸을 미리 채우고, 비어 있는 필수 항목을 표시해 문의하기로 넘긴다.
제출은 고객이 확인한 뒤 직접 누른다. 고객이 고친 값이 우선한다.
"""

from pydantic import BaseModel, Field

from cs_agent.rules.engine import required_info
from cs_agent.schemas import Classification, Extraction


class InquiryDraftForm(BaseModel):
    category: str | None = None
    product_code: str | None = None
    fields: dict[str, str] = Field(default_factory=dict)
    missing_required: list[str] = Field(default_factory=list)
    subject: str = ""
    body: str = ""  # TODO(CSA-34): Gemini로 대화 요약 (안내받은 조치와 결과 포함)


def fill_form(
    classification: Classification, extraction: Extraction, transcript: list[str]
) -> InquiryDraftForm:
    required, _ = required_info(extraction.product_family, classification.category)
    values = {
        "product_model": extraction.product_code,
        "error_code": extraction.error_code,
        "serial_no": extraction.serial_no,
        "current_fw": extraction.fw_version,
    }
    fields = {k: v for k, v in values.items() if k in required and v}
    return InquiryDraftForm(
        category=classification.category.value,
        product_code=extraction.product_code,
        fields=fields,
        missing_required=[k for k in required if k not in fields],
        subject=transcript[0][:80] if transcript else "",
        body="\n".join(transcript[-6:]),
    )
