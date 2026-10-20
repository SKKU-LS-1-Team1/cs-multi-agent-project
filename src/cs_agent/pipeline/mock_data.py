# mock 데이터 (CSA-23 · 담당 김동규 · Sprint 1)
#
# 화면·API 개발과 시연에 쓰는 샘플 문의. 두 종류를 만든다.
# 1. 시연 시나리오 4개 (고정 문장, 결과가 정해져 있음 — expect 에 적어 둠)
#    | id | 내용 | 기대 결과 |
#    |---|---|---|
#    | DEMO-SPEC | 문의서로 TRF-OIL-1000 Vector group 문의 | 추천 답변 → 상담원 검토 |
#    | DEMO-SAFETY | S100 에서 연기 발생 | 사람 큐 (초안 없음) |
#    | DEMO-MISSING | S100 E.OC 트립, 시리얼 없음 | 추가정보 요청 (시리얼) |
#    | DEMO-CHAT | 챗봇 경유: S100 E.OC 조치 후 재발, 문의하기 자동 채움 | 추천 답변 → 상담원 검토 |
# 2. 학습 분할(train) 문의를 유형별로 몇 건씩 뽑은 것 (실제 문장, 15개 언어·5개 채널이 섞임)
#    - valid·test 분할은 쓰지 않는다 (평가 데이터 오염 방지).
#    - 입력에는 고객이 실제로 보낸 것만 넣는다. 유형·제품 코드 같은 정답은 expect 에만 둔다.
#    - 접수 시각은 지금부터 0~72시간 전으로 흩어 놓는다 (작업 목록 SLA 정렬·경고 확인용).
#
# 실행 (저장소 루트)
#   mkdir -p data/mock && uv run python -m cs_agent.pipeline.mock_data > data/mock/inquiries.json
#   uv run python -m cs_agent.pipeline.mock_data --post http://localhost:8000         # API 에 넣기
#   uv run python -m cs_agent.pipeline.mock_data --post http://localhost:8000 --demo-only
# --post 는 POST /api/tickets 로 한 건씩 넣고, 결과 상태를 expect 와 나란히 보여 준다.
# 실제 분석이 돌므로 서버가 LLM_PROVIDER=live 여야 한다 (fake 면 모두 분석 대기).
import argparse
import csv
import json
import random
import sys
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from cs_agent.config import get_settings
from cs_agent.domain import Category, Route, TicketStatus
from cs_agent.schemas import InquiryIn

MockItem = dict[str, Any]  # {"id", "source", "expect", "inquiry": InquiryIn}


def demo_scenarios(now: datetime | None = None) -> list[MockItem]:
    now = now or datetime.now(UTC)
    return [
        {
            "id": "DEMO-SPEC",
            "source": "demo",
            "expect": {
                "category": Category.TECH_SPEC,
                "route": Route.DRAFT,
                "status": TicketStatus.READY_FOR_REVIEW,
            },
            "inquiry": InquiryIn(
                channel="WEB_FORM",
                customer_id="CUST-DEMO-01",
                customer_tier="GOLD",
                country="KR",
                language="en",
                subject="Vector group of TRF-OIL-1000",
                body=(
                    "Hello, what is the vector group of the oil-immersed transformer "
                    "TRF-OIL-1000? We need it for our substation single-line diagram.\n\n"
                    "Details:\n"
                    "- Product model / ordering code: TRF-OIL-1000\n"
                    "- Application (voltage, load, duty): 11 kV / 0.433 kV substation, "
                    "continuous duty"
                ),
                category=Category.TECH_SPEC,  # 문의서에서 고객이 고른 유형
                product_code="TRF-OIL-1000",
                provided_fields={
                    "product_model": "TRF-OIL-1000",
                    "application": "11 kV / 0.433 kV substation, continuous duty",
                },
                received_at=now - timedelta(hours=2),
            ),
        },
        {
            "id": "DEMO-SAFETY",
            "source": "demo",
            "expect": {
                "category": Category.DEFECT,
                "route": Route.HUMAN,
                "status": TicketStatus.HUMAN_QUEUE,
            },
            "inquiry": InquiryIn(
                channel="PHONE",
                customer_id="CUST-DEMO-02",
                customer_tier="PLATINUM",
                country="KR",
                language="ko",
                subject="S100 인버터에서 연기 발생",
                body=(
                    "LSLV S100 7.5kW 인버터(INV-LSLV0075-S100) 운전 중에 본체에서 연기가 나고 "
                    "타는 냄새가 납니다. 일단 차단기를 내렸습니다. 어떻게 해야 하나요?"
                ),
                received_at=now - timedelta(minutes=20),
            ),
        },
        {
            "id": "DEMO-MISSING",
            "source": "demo",
            "expect": {
                "category": Category.DEFECT,
                "route": Route.INFO_REQUEST,
                "status": TicketStatus.READY_FOR_REVIEW,
                "missing_blocking": ["serial_no"],
            },
            "inquiry": InquiryIn(
                channel="EMAIL",
                customer_id="CUST-DEMO-03",
                customer_tier="STANDARD",
                country="VN",
                language="en",
                subject="S100 drive keeps tripping",
                body=(
                    "Our LSLV S100 7.5kW drive (INV-LSLV0075-S100) trips with E.OC every time "
                    "the conveyor starts. It happens during acceleration, about 3 seconds after "
                    "the run command. Please help."
                ),
                received_at=now - timedelta(hours=30),
            ),
        },
        {
            "id": "DEMO-CHAT",
            "source": "demo",
            "expect": {
                "category": Category.DEFECT,
                "route": Route.DRAFT,
                "status": TicketStatus.READY_FOR_REVIEW,
            },
            # 챗봇(CSA-32)이 대화에서 모은 값으로 문의하기를 자동으로 채운 모양
            "inquiry": InquiryIn(
                channel="CHAT",
                customer_id="CUST-DEMO-04",
                customer_tier="GOLD",
                country="KR",
                language="ko",
                subject="S100 E.OC 트립 재발",
                body=(
                    "챗봇 안내대로 가속 시간을 10초로 늘렸는데 이틀 뒤 E.OC 트립이 "
                    "다시 발생했습니다. 가속 중에 발생하고, 부하는 컨베이어입니다. "
                    "트립 로그를 첨부합니다."
                ),
                product_code="INV-LSLV0075-S100",
                provided_fields={
                    "product_model": "INV-LSLV0075-S100",
                    "serial_no": "S100K24A01234",
                    "error_code": "E.OC",
                    "operating_condition": "가속 중, 컨베이어 부하",
                    "logs": "[attachment: trip_log.csv]",
                },
                received_at=now - timedelta(hours=5),
            ),
        },
    ]


def sample_inquiries(
    per_category: int = 3,
    seed: int = 7,
    tickets_csv: Path | None = None,
    now: datetime | None = None,
) -> list[MockItem]:
    """train 분할에서 유형별 per_category 건. 같은 seed 면 같은 결과."""
    now = now or datetime.now(UTC)
    path = tickets_csv or get_settings().raw_data_dir / "tickets.csv"
    with path.open(encoding="utf-8-sig", newline="") as f:
        by_category: dict[str, list[dict]] = defaultdict(list)
        for row in csv.DictReader(f):
            if row["data_split"] == "train":
                by_category[row["category_code"]].append(row)

    rng = random.Random(seed)
    items = []
    for category in Category:
        for row in rng.sample(by_category[category], per_category):
            items.append(
                {
                    "id": f"MOCK-{row['ticket_id']}",
                    "source": row["ticket_id"],
                    "expect": {  # 원천 데이터의 정답 (비교용, 입력에는 넣지 않음)
                        "category": row["category_code"],
                        "product_code": row["product_code"] or None,
                        "urgency": row["urgency_flag"],
                        "priority": row["priority"],
                        "assigned_dept": row["assigned_dept"],
                    },
                    "inquiry": InquiryIn(
                        channel=row["channel"],
                        customer_id=row["customer_id"] or None,
                        customer_tier=row["customer_tier"] or "STANDARD",
                        country=row["country"] or None,
                        language=row["language"] or None,
                        subject=row["inquiry_subject"],
                        body=row["inquiry_body"],
                        received_at=now - timedelta(minutes=rng.randint(0, 72 * 60)),
                    ),
                }
            )
    return items


def build(per_category: int = 3, seed: int = 7, demo_only: bool = False) -> list[MockItem]:
    now = datetime.now(UTC)
    items = demo_scenarios(now)
    if not demo_only:
        items += sample_inquiries(per_category, seed, now=now)
    return items


def to_json(items: list[MockItem]) -> list[dict]:
    return [{**item, "inquiry": item["inquiry"].model_dump(mode="json")} for item in items]


def post_all(items: list[MockItem], base_url: str = "", client: Any = None) -> list[dict]:
    """POST /api/tickets 로 넣고 (id, ticket_id, 기대, 실제) 를 돌려준다.

    client 를 주면 그걸 쓴다 (테스트는 FastAPI TestClient).
    """
    import httpx

    results = []
    with client or httpx.Client(base_url=base_url, timeout=180) as client:
        for item in items:
            res = client.post("/api/tickets", json=item["inquiry"].model_dump(mode="json"))
            res.raise_for_status()
            ticket = res.json()
            results.append(
                {
                    "id": item["id"],
                    "ticket_id": ticket["ticket_id"],
                    "expect_status": item["expect"].get("status"),
                    "status": ticket["status"],
                    "expect_category": item["expect"].get("category"),
                    "category": ticket["category"],
                    "route": ticket["route"],
                }
            )
            row = results[-1]
            mark = "" if not row["expect_status"] else "✓" if _matches(row) else "✗"
            print(
                f"{mark:1} {row['id']:22} {row['ticket_id']:16} {row['status']:18} "
                f"{row['category'] or '-':11} (기대 {row['expect_status'] or '-'}, "
                f"{row['expect_category'] or '-'})",
                file=sys.stderr,
                flush=True,
            )
    return results


def _matches(row: dict) -> bool:
    return row["status"] == row["expect_status"] and row["category"] == row["expect_category"]


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="mock 문의 만들기 / API 에 넣기 (CSA-23)")
    parser.add_argument("--per-category", type=int, default=3, help="유형별 train 문의 수")
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--demo-only", action="store_true", help="시연 시나리오 4개만")
    parser.add_argument("--post", metavar="BASE_URL", help="예: http://localhost:8000")
    args = parser.parse_args(argv)

    items = build(args.per_category, args.seed, args.demo_only)
    if args.post:
        post_all(items, args.post)
    else:
        json.dump(to_json(items), sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")


if __name__ == "__main__":
    main()
