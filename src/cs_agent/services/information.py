"""Apply a staff review to existing extraction without another classification/extraction call."""

from cs_agent.rules.tables import RefTables
from cs_agent.schemas import Extraction, InformationFieldReview

_SCALARS = {"error_code": "error_code", "serial_no": "serial_no", "current_fw": "fw_version"}


def apply_information_review(
    extraction: Extraction,
    fields: dict[str, InformationFieldReview],
    tables: RefTables,
) -> tuple[Extraction, dict[str, InformationFieldReview]]:
    reviewed = extraction.model_copy(deep=True)
    normalized: dict[str, InformationFieldReview] = {}
    allowed = set(tables.field_labels) | set(tables.request_labels) | {"product_model", *_SCALARS}
    for key, item in sorted(fields.items(), key=lambda pair: pair[0] != "product_model"):
        if key not in allowed:
            raise ValueError(f"알 수 없는 자료 항목입니다: {key}")
        old = reviewed.field_values.get(key) or (
            reviewed.product_code
            if key == "product_model"
            else getattr(reviewed, _SCALARS.get(key, ""), None)
        )
        if item.status == "confirmed":
            value = item.value or old
            if not value or not item.evidence:
                raise ValueError(f"확인한 {key}의 실제 값과 확인 근거를 입력해 주세요")
            if key == "product_model":
                # Product catalog identity only. A generic family name must never choose an item.
                if value not in tables.products:
                    from cs_agent.agents.analysis import _product_matches

                    matches = _product_matches(value, tables.products)
                    if (
                        len(matches) != 1
                        or next(iter(matches.values())).casefold() != value.casefold()
                    ):
                        raise ValueError("제품을 하나의 제품 코드로 확인해 주세요")
                    value = next(iter(matches))
                if value != reviewed.product_code:
                    _invalidate_product_fields(reviewed, item.evidence)
                reviewed.product_code = value
                reviewed.product_family = tables.products[value].family
            if old and old != value:
                reviewed.field_candidates.setdefault(key, []).append(
                    {
                        "value": old,
                        "evidence": reviewed.field_evidence.get(key, ""),
                        "source": reviewed.field_sources.get(key, ""),
                        "reason": "staff_correction",
                    }
                )
            reviewed.field_values[key] = value
            reviewed.field_evidence[key] = item.evidence
            reviewed.field_sources[key] = "staff"
            reviewed.unconfirmed_fields.pop(key, None)
            reviewed.unconfirmed_evidence.pop(key, None)
            if key not in reviewed.provided_info:
                reviewed.provided_info.append(key)
            if key in _SCALARS:
                setattr(reviewed, _SCALARS[key], value)
            normalized[key] = item.model_copy(update={"value": value})
        else:
            if item.value:
                raise ValueError(f"미제공·사용 불가 항목 {key}에는 확정값을 넣을 수 없습니다")
            if old:
                reviewed.field_candidates.setdefault(key, []).append(
                    {
                        "value": old,
                        "evidence": reviewed.field_evidence.get(key, ""),
                        "source": reviewed.field_sources.get(key, ""),
                        "reason": f"staff_{item.status}",
                    }
                )
            reviewed.field_values.pop(key, None)
            reviewed.field_evidence.pop(key, None)
            reviewed.field_sources.pop(key, None)
            reviewed.provided_info = [name for name in reviewed.provided_info if name != key]
            reviewed.unconfirmed_fields[key] = f"staff_{item.status}"
            reviewed.unconfirmed_evidence[key] = item.evidence
            if key == "product_model":
                _invalidate_product_fields(reviewed, item.evidence)
                reviewed.product_code = reviewed.product_family = None
            if key in _SCALARS:
                setattr(reviewed, _SCALARS[key], None)
            normalized[key] = item.model_copy(update={"value": None})
    return reviewed, normalized


def _invalidate_product_fields(extraction: Extraction, evidence: str) -> None:
    """A new product cannot inherit the old unit's serial, error, firmware or operating facts."""
    values = dict(extraction.field_values)
    for key, attr in _SCALARS.items():
        if value := getattr(extraction, attr):
            values.setdefault(key, value)
        setattr(extraction, attr, None)
    keys = (set(values) | set(extraction.provided_info)) - {"product_model"}
    for key in keys:
        if value := values.get(key):
            extraction.field_candidates.setdefault(key, []).append(
                {
                    "value": value,
                    "evidence": extraction.field_evidence.get(key, ""),
                    "source": extraction.field_sources.get(key, ""),
                    "reason": "product_changed",
                }
            )
        extraction.field_values.pop(key, None)
        extraction.field_evidence.pop(key, None)
        extraction.field_sources.pop(key, None)
        extraction.unconfirmed_fields[key] = "product_changed"
        extraction.unconfirmed_evidence[key] = evidence
    extraction.provided_info = [key for key in extraction.provided_info if key == "product_model"]
    extraction.return_defect = None
