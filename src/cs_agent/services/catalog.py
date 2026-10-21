# 제품 대시보드 데이터 (CSA-60 · 담당 김동규)
#
# 고객 화면 제품 대시보드(CSA-36 트리 · CSA-37 상세 탭)에 줄 내용을 기준표·기술문서에서 모은다.
# api/products.py 가 부른다. 파일만 읽으므로 DB·LLM 없이 동작하고, 한 번 만든 뒤 캐시한다.
#
# - tree(): 대분류(family_divisions.csv 순서) → 제품군 → 제품. 대 3 · 중 11 · 소 23
# - detail(code): 탭별 내용. 내용이 있는 탭만 tabs 에 넣는다 (펌웨어가 없는 제품은 firmware 탭 없음)
#   info      제품 설명 · 사양(product_spec_facts, 근거 문서·절) · 규격·인증 · 납기·MOQ·보증 · 외형
#   install   설치 가이드(IG) 절
#   faults    fault_catalog 에서 이 제품에 해당하는 고장 + 고장 가이드(TG) 절 번호
#   firmware  firmware_history (최신 먼저)
#   faq       제품군 FAQ + 정책(보증·반품·주문·서비스) 절
#   docs      문서 자료실: 제품 문서 + 제품군 FAQ + 정책
# - document(code, doc_id): 문서 하나의 절 목록. 그 제품이 볼 수 있는 문서(docs 탭)만
#
# 정해 둔 것
# - 챗봇 화면 이동 지시(chatbot/navigation.py, navigation_rules.csv)의 tab 값이 그대로 탭 이름이다.
#   anchor 로 강조할 수 있게 값을 담는다: faults[].error_code, info.specs[].attribute,
#   install.sections[].section, docs[].doc_id, firmware.latest. lead_time·policy 는 info.ordering ·
#   faq.policies 가 그 자리다.
# - 정가(list_price_usd)는 내보내지 않는다. 견적 금액은 영업팀이 정한다
#   (챗봇도 금액을 확정하지 않는다).
# - 절 나누기는 pipeline/chunking.py 와 같다 (RAG 근거의 doc_id·section 과 같은 번호). 긴 절이
#   여러 조각으로 나뉘었으면 다시 이어 붙인다.
import csv
from functools import lru_cache
from pathlib import Path
from typing import Any

from cs_agent.config import get_settings
from cs_agent.pipeline.chunking import chunk_markdown, parse_front_matter
from cs_agent.rules.tables import RefTables, load_tables

TAB_ORDER = ("info", "install", "faults", "firmware", "faq", "docs")
POLICY_DOC_TYPE = "POL"


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        return [{k: (v or "").strip() for k, v in row.items()} for row in csv.DictReader(f)]


def _split(value: str) -> list[str]:
    return [v.strip() for v in value.split(";") if v.strip()]


def _sections(raw: str) -> list[dict[str, str]]:
    """문서 → 절 목록 [{section, title, text}]. 나뉜 조각은 다시 잇는다."""
    merged: dict[str, dict[str, str]] = {}
    for chunk in chunk_markdown(raw):
        if chunk.section in merged:
            merged[chunk.section]["text"] += "\n\n" + chunk.text
        else:
            merged[chunk.section] = {
                "section": chunk.section,
                "title": chunk.title,
                "text": chunk.text,
            }
    return list(merged.values())


class Catalog:
    """기준표 + 기술문서로 만든 제품 대시보드 내용."""

    def __init__(self, tables: RefTables, ref_dir: Path, docs_dir: Path) -> None:
        self.tables = tables
        self.master = {r["product_code"]: r for r in _rows(ref_dir / "product_master.csv")}
        self.docs_dir = docs_dir
        self.doc_index = {r["doc_id"]: r for r in _rows(docs_dir / "doc_index.csv")}
        self._doc_cache: dict[str, list[dict[str, str]]] = {}

    # 트리 ------------------------------------------------------------------------------------

    def tree(self) -> list[dict[str, Any]]:
        families: dict[str, list[dict[str, str]]] = {}
        for code, product in self.tables.products.items():
            families.setdefault(product.family, []).append({"code": code, "name": product.name})
        tree = []
        for division, label in self.tables.divisions.items():
            members = [f for f, d in self.tables.family_divisions.items() if d == division]
            tree.append(
                {
                    "division": division,
                    "label": label,
                    "families": [
                        {
                            "family": family,
                            "label": self._family_label(family),
                            "products": families[family],
                        }
                        for family in members
                        if family in families
                    ],
                }
            )
        return tree

    def _family_label(self, family: str) -> str:
        return next(
            (r["family_name"] for r in self.master.values() if r["family"] == family), family
        )

    # 상세 ------------------------------------------------------------------------------------

    def detail(self, code: str) -> dict[str, Any] | None:
        product = self.tables.products.get(code)
        if product is None:
            return None
        row = self.master.get(code, {})
        content = {
            "info": self._info(code, row),
            "install": self._install(code),
            "faults": self._faults(code),
            "firmware": self._firmware(code),
            "faq": self._faq(product.family),
            "docs": self._docs(code),
        }
        return {
            "code": code,
            "name": product.name,
            "family": product.family,
            "family_label": self._family_label(product.family),
            "division": product.division,
            "division_label": self.tables.divisions.get(product.division, ""),
            "description": row.get("description", ""),
            "lifecycle_status": row.get("lifecycle_status", ""),
            "tabs": [tab for tab in TAB_ORDER if content[tab]],
            **content,
        }

    def _info(self, code: str, row: dict[str, str]) -> dict[str, Any]:
        product = self.tables.products[code]
        return {
            "specs": [
                {k: fact[k] for k in ("attribute", "value", "doc_id", "section")}
                for fact in self.tables.spec_facts.get(code, [])
            ],
            "standards": _split(product.standards),
            "certifications": _split(product.certifications),
            "ordering": {
                "std_lead_time_weeks": product.std_lead_time_weeks,
                "moq": product.moq,
                "warranty_months": product.warranty_months,
            },
            "physical": {
                key: row.get(key, "")
                for key in ("weight_kg", "dimensions_mm", "ip_rating", "operating_temp")
            },
        }

    def _install(self, code: str) -> dict[str, Any] | None:
        doc = self._product_doc(code, "IG")
        return self._document(doc) if doc else None

    def _faults(self, code: str) -> list[dict[str, Any]]:
        tg = self._product_doc(code, "TG")
        # 고장 가이드 절 제목은 "E.OC — Over-current trip during acceleration" (코드 — 증상),
        # 에러코드가 없는 고장은 증상만 ("Breaker trips at motor start")
        by_title = {s["title"]: s["section"] for s in self._sections(tg)} if tg else {}
        faults = []
        for fault in self.tables.faults:
            if code not in _split(fault["applies_to"]):
                continue
            error_code, symptom = fault["error_code"], fault["symptom"]
            title = f"{error_code} — {symptom}" if error_code else symptom
            faults.append(
                {
                    **{
                        k: fault[k]
                        for k in (
                            "fault_id",
                            "error_code",
                            "symptom",
                            "root_cause",
                            "diagnosis",
                            "action",
                        )
                    },
                    "needs_onsite": fault["needs_onsite"] == "Y",
                    "needs_rma": fault["needs_rma"] == "Y",
                    "fw_fix_version": fault.get("fw_fix_version", ""),
                    "doc_id": tg if title in by_title else None,
                    "section": by_title.get(title),
                }
            )
        return faults

    def _firmware(self, code: str) -> dict[str, Any] | None:
        rows = sorted(
            self.tables.firmware.get(code, []), key=lambda r: r["release_date"], reverse=True
        )
        if not rows:
            return None
        releases = [
            {
                "version": r["fw_version"],
                "release_date": r["release_date"],
                "latest": r["is_latest"] == "Y",
                "changes": [c.strip() for c in r["changes"].split("|") if c.strip()],
                "doc_id": r.get("doc_id", ""),
            }
            for r in rows
        ]
        latest = next((r["version"] for r in releases if r["latest"]), releases[0]["version"])
        return {"latest": latest, "releases": releases}

    def _faq(self, family: str) -> dict[str, Any] | None:
        faq = f"FAQ-{family}"
        items = [
            {"section": s["section"], "question": s["title"], "answer": s["text"]}
            for s in self._sections(faq)
        ]
        policies = [self._document(doc_id) for doc_id in self._policy_ids()]
        if not items and not policies:
            return None
        return {"doc_id": faq if items else None, "items": items, "policies": policies}

    def _docs(self, code: str) -> list[dict[str, str]]:
        return [self._doc_meta(doc_id) for doc_id in self._visible_docs(code)]

    # 문서 ------------------------------------------------------------------------------------

    def document(self, code: str, doc_id: str) -> dict[str, Any] | None:
        """그 제품의 문서 자료실(docs 탭)에 있는 문서만 연다."""
        if code not in self.tables.products or doc_id not in self._visible_docs(code):
            return None
        return self._document(doc_id)

    def _visible_docs(self, code: str) -> list[str]:
        product = self.tables.products[code]
        candidates = [*product.doc_ids, f"FAQ-{product.family}", *self._policy_ids()]
        return [doc_id for doc_id in dict.fromkeys(candidates) if doc_id in self.doc_index]

    def _policy_ids(self) -> list[str]:
        return [d for d, r in self.doc_index.items() if r["doc_type"] == POLICY_DOC_TYPE]

    def _product_doc(self, code: str, doc_type: str) -> str | None:
        return next(
            (
                doc_id
                for doc_id in self.tables.products[code].doc_ids
                if self.doc_index.get(doc_id, {}).get("doc_type") == doc_type
            ),
            None,
        )

    def _doc_meta(self, doc_id: str) -> dict[str, str]:
        row = self.doc_index[doc_id]
        return {k: row[k] for k in ("doc_id", "title", "doc_type", "revision")}

    def _document(self, doc_id: str) -> dict[str, Any]:
        return {**self._doc_meta(doc_id), "sections": self._sections(doc_id)}

    def _sections(self, doc_id: str) -> list[dict[str, str]]:
        if doc_id not in self._doc_cache:
            row = self.doc_index.get(doc_id)
            path = self.docs_dir.parent / row["path"] if row else None
            if path is None or not path.is_file():
                self._doc_cache[doc_id] = []
            else:
                raw = path.read_text(encoding="utf-8")
                meta, _ = parse_front_matter(raw)
                if meta.get("doc_id") not in (None, doc_id):
                    raise ValueError(f"{path}: front matter doc_id 가 {doc_id} 가 아니다")
                self._doc_cache[doc_id] = _sections(raw)
        return self._doc_cache[doc_id]


@lru_cache
def get_catalog() -> Catalog:
    settings = get_settings()
    return Catalog(load_tables(settings.ref_dir), settings.ref_dir, settings.raw_data_dir / "docs")
