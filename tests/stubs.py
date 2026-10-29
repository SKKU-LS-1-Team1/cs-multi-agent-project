# 테스트용 분석 에이전트 대역 (그래프·API 흐름 테스트에서 LLM 없이 ②③ 자리를 채운다)
#
# 실제 구현은 agents/analysis.py. 여기 함수는 tests/ 밖에서 쓰지 않는다.
import functools
import re

from cs_agent.domain import Urgency
from cs_agent.rules.engine import UNKNOWN_PRODUCT_FIELD
from cs_agent.schemas import Classification, Extraction, InquiryIn

_SAFETY = re.compile(r"(?i)\b(smoke|fire|spark(?:s|ing)?)\b|연기|화재|감전")


def classify(inquiry: InquiryIn, llm) -> Classification:
    assert inquiry.category, "테스트 문의는 category 를 채워 둔다"
    return Classification(category=inquiry.category, confidence=1.0, model="stub")


def extract(inquiry: InquiryIn, tables, *, llm=None, category=None) -> Extraction:
    text = f"{inquiry.subject}\n{inquiry.body}"
    code = inquiry.product_code or next(
        (c for c in tables.products if re.search(rf"\b{re.escape(c)}\b", text)), None
    )
    product = tables.products.get(code) if code else None
    provided = list(inquiry.provided_fields)
    if product:
        provided.append(UNKNOWN_PRODUCT_FIELD)
    return Extraction(
        product_code=product.code if product else None,
        product_family=product.family if product else None,
        urgency=Urgency.SAFETY if _SAFETY.search(text) else Urgency.NONE,
        language=inquiry.language,
        provided_info=provided,
    )


def pass_customer_qc(text, *args, **kwargs):
    import hashlib

    from cs_agent.qc_schemas import QcResult

    return QcResult(decision="PASS", text_hash=hashlib.sha256(text.encode()).hexdigest())


ANALYSIS = {"classify": classify, "extract": extract, "check_customer_qc": pass_customer_qc}


# 지식 그래프 fake (CSA-71) -----------------------------------------------------------------------
# agents/knowledge_graph.GraphStore 를 메모리로. Neo4j 와 같은 GraphData(pipeline/build_graph.py)로
# 만들어서 CI 가 Neo4j 없이 검색·학습 규칙을 돈다. 임베딩은 단어 해시 벡터(toy_embed)로 대신한다.


def toy_embed(text: str, dim: int = 256) -> list[float]:
    import hashlib
    import math

    vector = [0.0] * dim
    for word in re.findall(r"[a-z0-9.]+", text.lower()):
        vector[int(hashlib.md5(word.encode()).hexdigest(), 16) % dim] += 1.0
    norm = math.sqrt(sum(x * x for x in vector)) or 1.0
    return [x / norm for x in vector]


class MemoryGraph:
    def __init__(self, data) -> None:
        self.nodes = {label: {r["id"]: dict(r) for r in rows} for label, rows in data.nodes.items()}
        self.rels = {rel: set(pairs) for rel, pairs in data.rels.items()}

    def _into(self, rel: str, end: str) -> set[str]:
        return {a for a, b in self.rels[rel] if b == end}

    def _out(self, rel: str, start: str) -> set[str]:
        return {b for a, b in self.rels[rel] if a == start}

    def _active_cases(self, fault_id: str) -> list[dict]:
        cases = [self.nodes["Case"][c] for c in self._into("INSTANCE_OF", fault_id)]
        return [c for c in cases if c["active"]]

    def faults_on_product(self, product_code: str) -> set[str]:
        return self._into("APPLIES_TO", product_code)

    def faults_in_family(self, family: str) -> set[str]:
        products = self._into("IN_FAMILY", family)
        return {f for p in products for f in self._into("APPLIES_TO", p)}

    def faults_with_code(self, code: str) -> set[str]:
        return self._into("SHOWS_CODE", code)

    def rank(self, fault_ids, vector, k):
        pool = self.nodes["Fault"] if fault_ids is None else fault_ids
        scored = []
        for fid in pool:
            embedding = self.nodes["Fault"][fid].get("embedding")
            if embedding and self._active_cases(fid):
                scored.append((fid, sum(a * b for a, b in zip(embedding, vector, strict=True))))
        return sorted(scored, key=lambda pair: (-pair[1], pair[0]))[:k]

    def details(self, fault_ids):
        out = {}
        for fid in fault_ids:
            fault = self.nodes["Fault"][fid]
            cases = sorted(
                self._active_cases(fid),
                key=lambda c: (c["split"] == "live", c["resolved_at"], c["id"]),
                reverse=True,
            )
            active = {c["id"] for c in cases}
            cited = {c: self._out("CITED", c) for c in active}
            sections = sorted(
                self._out("EXPLAINED_IN", fid),
                key=lambda d: (-sum(d in s for s in cited.values()), d),
            )
            out[fid] = {
                "pattern": {
                    "pattern_id": fid,
                    **{k: fault.get(k) for k in ("family", "error_code", "applies_to", "text")},
                },
                "cases": [
                    {
                        "case_id": c["id"],
                        "final_reply": c["final_reply"],
                        "data_split": c["split"],
                        "product_code": c["product_code"],
                        "cited": sorted(cited[c["id"]]),
                    }
                    for c in cases
                ],
                "sections": sections,
            }
        return out

    def has_vector(self, fault_id: str) -> bool:
        return bool(self.nodes["Fault"].get(fault_id, {}).get("embedding"))

    def learn(self, case, fault) -> None:
        from cs_agent.pipeline.build_graph import case_node

        if fault is not None:
            node = self.nodes["Fault"].setdefault(fault["id"], dict(fault))
            node["embedding"] = node.get("embedding") or fault.get("embedding")
            for product in fault["applies_to"]:
                if product in self.nodes["Product"]:
                    self.rels["APPLIES_TO"].add((fault["id"], product))
            if fault.get("error_code"):
                self.nodes["ErrorCode"].setdefault(fault["error_code"], {"id": fault["error_code"]})
                self.rels["SHOWS_CODE"].add((fault["id"], fault["error_code"]))
        node = case_node(case)
        self.nodes["Case"][node["id"]] = node
        for rel in ("INSTANCE_OF", "ON_PRODUCT", "CITED"):
            self.rels[rel] = {(a, b) for a, b in self.rels[rel] if a != node["id"]}
        fault_id = case.get("pattern_id")
        if fault_id in self.nodes["Fault"]:
            self.rels["INSTANCE_OF"].add((node["id"], fault_id))
        if node["product_code"] in self.nodes["Product"]:
            self.rels["ON_PRODUCT"].add((node["id"], node["product_code"]))
        for section in case.get("cited") or []:
            if section in self.nodes["DocSection"]:
                self.rels["CITED"].add((node["id"], section))
                if fault_id in self.nodes["Fault"]:
                    self.rels["EXPLAINED_IN"].add((fault_id, section))

    def deactivate(self, ticket_id: str) -> None:
        for case in self.nodes["Case"].values():
            if case["ticket_id"] == ticket_id:
                case["active"] = False

    def case_count(self, fault_id: str) -> int:
        return len(self._active_cases(fault_id))


@functools.lru_cache(maxsize=1)
def graph_data():
    """기준표 + data/raw train 사례 568건 그래프 (고장 설명은 toy_embed)."""
    from cs_agent.agents.case_patterns import catalog_pattern
    from cs_agent.pipeline.build_graph import build, csv_cases
    from cs_agent.rules.tables import load_tables

    patterns = {
        r["fault_id"]: {"embedding": toy_embed(catalog_pattern(r)["text"])}
        for r in load_tables().faults
    }
    return build(csv_cases(), patterns)


def memory_graph() -> MemoryGraph:
    return MemoryGraph(graph_data())
