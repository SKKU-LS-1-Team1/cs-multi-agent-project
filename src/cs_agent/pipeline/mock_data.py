"""mock 데이터 생성 (CSA-23 · 담당 김동규).

화면·API 개발용으로 유형별 샘플 문의를 만든다. 실제 시험 데이터(test 597건)는 쓰지 않는다.
실행: `uv run python -m cs_agent.pipeline.mock_data > data/mock/inquiries.json`
"""

import json
import random

from cs_agent.domain import Category
from cs_agent.rules.tables import load_tables

_BODIES = {
    Category.TECH_SPEC: "What is the rated breaking capacity of {name}?",
    Category.MANUAL: "Please send the installation manual for {name}.",
    Category.COMPLIANCE: "Does {name} have CE and UL certification?",
    Category.QUOTE: "Please quote 20 units of {name}, Incoterms FOB.",
    Category.ORDER_LEAD: "What is the lead time for {name}? PO number pending.",
    Category.DEFECT: "{name} shows error E.OC during acceleration.",
    Category.INSTALL: "How should I wire {name} in the panel?",
    Category.FW_UPDATE: "Is there a newer firmware for {name}? Current fw 1.2.",
    Category.WARRANTY: "{name} failed after 8 months. Is it under warranty?",
    Category.RETURN: "We want to return {name}, wrong model delivered.",
}


def generate(n: int = 50, seed: int = 7) -> list[dict]:
    rng = random.Random(seed)
    products = list(load_tables().products.values())
    rows = []
    for i in range(n):
        category = rng.choice(list(Category))
        p = rng.choice(products)
        rows.append(
            {
                "channel": rng.choice(["EMAIL", "WEB_FORM", "CHAT", "PHONE", "PARTNER_PORTAL"]),
                "customer_id": f"CUST-MOCK-{i:04d}",
                "customer_tier": rng.choice(["STANDARD", "GOLD", "PLATINUM"]),
                "language": "en",
                "subject": f"[{category.value}] {p.name}",
                "body": _BODIES[category].format(name=p.name),
            }
        )
    return rows


if __name__ == "__main__":
    print(json.dumps(generate(), ensure_ascii=False, indent=2))
