"""⑦ 추가정보 요청 에이전트 (CSA-27 · 담당 김동규).

빠진 필수정보만, 한 번에, 고객 언어로 요청문 초안을 쓴다. 고객에게 직접 보내지 않고
상담원 화면에 초안으로 올린다 (P-01). 상담원 버튼으로 직접 부를 수도 있다.
"""

from cs_agent.llm.router import LLMRouter

FIELD_LABELS = {
    "product_model": "product model / ordering code",
    "serial_no": "serial number (nameplate photo)",
    "error_code": "error code shown on the display",
    "operating_condition": "operating condition when the problem occurred",
    "photos": "photos of the product and installation",
    "current_fw": "current firmware version",
    "tool_version": "engineering tool version",
    "quantity": "quantity",
    "incoterms": "Incoterms",
    "required_date": "required delivery date",
    "po_number": "PO number",
    "purchase_doc": "purchase document (invoice)",
    "return_reason": "reason for return",
    "target_standard": "target standard (IEC/UL/KC...)",
    "target_country": "destination country",
    "application": "application / use case",
    "document_type": "document type needed",
    "site_condition": "site condition",
    "wiring_diagram": "wiring diagram",
}


def write_info_request(missing: list[str], language: str, summary: str, llm: LLMRouter) -> str:
    items = [FIELD_LABELS.get(m, m) for m in missing]
    if llm.enabled:
        prompt = (
            f"고객 언어({language})로 정중한 추가정보 요청문을 써라. 아래 항목만, 한 번에 묻는다.\n"
            f"문의 요약: {summary}\n항목: {', '.join(items)}"
        )
        return llm.write("info_request", prompt)
    # TODO(CSA-27): 언어별 고정 문장 틀 (15개 언어) 또는 Gemini 번역
    lines = "\n".join(f"- {i}" for i in items)
    return (
        "Thank you for contacting us. To proceed with your inquiry, "
        f"please provide the following information:\n{lines}"
    )
