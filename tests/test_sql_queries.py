"""db/sql/*.sql (CSA-20). 실제 DB 테스트는 test_db.py 와 같이 TEST_DATABASE_URL 이 있을 때만.

  docker run -d --rm -p 55432:5432 -e POSTGRES_USER=cs -e POSTGRES_PASSWORD=cs \\
      -e POSTGRES_DB=cs pgvector/pgvector:0.8.0-pg16
  TEST_DATABASE_URL=postgresql+psycopg://cs:cs@localhost:55432/cs \\
      uv run pytest tests/test_sql_queries.py
"""

import json
import os
import re
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa

from cs_agent.db.queries import gold_rows, load_queries, params_of, query, run
from cs_agent.domain import FeedbackReason

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")
needs_db = pytest.mark.skipif(not TEST_DATABASE_URL, reason="TEST_DATABASE_URL 없음")
NOW = datetime(2026, 10, 21, 12, 0, tzinfo=UTC)


# --- DB 없이 ---------------------------------------------------------------------------------


def test_sql_files_split_into_named_queries() -> None:
    assert set(load_queries("dept_dashboard")) == {
        "dept_status",
        "review_outcomes_weekly",
        "feedback_reasons",
    }
    assert set(load_queries("work_list")) == {"work_list"}
    assert {"create_tickets_gold", "upsert_tickets_gold", "eval_summary"} <= set(
        load_queries("eval_join")
    )
    assert params_of("work_list", "work_list") == {"dept", "assignee", "now", "at_risk_ratio"}
    assert params_of("dept_dashboard", "review_outcomes_weekly") == {"dept", "since", "tz"}
    assert "-- name" not in load_queries("work_list")["work_list"]
    with pytest.raises(KeyError):
        query("work_list", "nope")


def test_feedback_reasons_match_domain() -> None:
    sql = load_queries("dept_dashboard")["feedback_reasons"]
    assert set(re.findall(r"\('(\w+)', \d\)", sql)) == {r.value for r in FeedbackReason}


def test_gold_rows_keep_valid_test_and_parse_lists() -> None:
    base = {
        "language": "en",
        "body_language": "en",
        "customer_tier": "GOLD",
        "product_code": "ACB-AS-2000",
        "category_code": "DEFECT",
        "urgency_flag": "NONE",
        "priority": "P3",
        "priority_rule_id": "PR-05",
        "priority_adjusted_by_agent": "Y",
        "assigned_dept": "TS_LV",
        "routing_rule_id": "RT-LV_BREAKER-DEFECT",
        "required_info": "serial_no;photos",
        "missing_info": "photos",
        "missing_blocking_info": "",
        "info_request_sent": "N",
        "reference_doc_id": "TG-ACB-AS-2000",
        "reference_section": "",
    }
    tickets = [
        {**base, "ticket_id": "A", "data_split": "train"},
        {**base, "ticket_id": "B", "data_split": "valid"},
    ]

    [row] = gold_rows(tickets)

    assert row["ticket_id"] == "B"
    assert json.loads(row["required_info"]) == ["serial_no", "photos"]
    assert json.loads(row["missing_blocking_info"]) == []
    assert row["priority_adjusted_by_agent"] is True
    assert row["reference_section"] is None


# --- 실제 DB ---------------------------------------------------------------------------------


@pytest.fixture
def conn():
    from alembic import command

    from cs_agent.db.session import alembic_config, get_engine

    config = alembic_config(TEST_DATABASE_URL)
    command.downgrade(config, "base")
    command.upgrade(config, "head")
    engine = get_engine(TEST_DATABASE_URL)
    with engine.connect() as connection:
        connection.execute(sa.text("DROP SCHEMA IF EXISTS eval CASCADE"))
        connection.commit()
        yield connection
        connection.rollback()
        connection.execute(sa.text("DROP SCHEMA IF EXISTS eval CASCADE"))
        connection.commit()
    command.downgrade(config, "base")


def _ticket(conn, ticket_id: str, hours_ago: float, **values) -> None:
    row = {
        "ticket_id": ticket_id,
        "channel": "email",
        "customer_tier": "STANDARD",  # ORM 기본값이라 DB 기본값이 없는 NOT NULL 열
        "subject": "",
        "followups": 0,
        "body": "b",
        "received_at": NOW - timedelta(hours=hours_ago),
        "status": "READY_FOR_REVIEW",
        "category": "TECH_SPEC",
        "assigned_dept": "TS_LV",
        "priority": "P3",
        "sla_resolution_target_h": 100.0,
        "customer_wait_hours": 0.0,
    } | values
    for key in ("provided_info", "missing_info", "missing_blocking", "provided_fields"):
        row[key] = json.dumps(row.get(key, [] if key != "provided_fields" else {}))
    columns = ", ".join(row)
    binds = ", ".join(
        f"CAST(:{k} AS jsonb)"
        if k in ("provided_info", "missing_info", "missing_blocking", "provided_fields")
        else f":{k}"
        for k in row
    )
    conn.execute(sa.text(f"INSERT INTO tickets ({columns}) VALUES ({binds})"), row)


def _review(conn, ticket_id: str, action: str, reason: str | None = None, days_ago: int = 0):
    conn.execute(
        sa.text(
            "INSERT INTO reviews (ticket_id, action, reviewer, feedback_reason, info_items, "
            "created_at) VALUES (:t, :a, 'r', :f, '[]', :c)"
        ),
        {"t": ticket_id, "a": action, "f": reason, "c": NOW - timedelta(days=days_ago)},
    )


@needs_db
def test_work_list_orders_by_sla_ratio_and_pauses_while_waiting(conn) -> None:
    _ticket(conn, "T-LOW", 10)  # 0.10
    _ticket(conn, "T-RISK", 80)  # 0.80
    _ticket(conn, "T-OTHER", 90, assigned_dept="TS_MV")  # 0.90
    # 50시간 전 접수, 지난 대기 10시간 + 지금 20시간째 대기 → 경과 20시간 = 0.20
    _ticket(
        conn,
        "T-WAIT",
        50,
        status="WAITING_CUSTOMER",
        customer_wait_hours=10.0,
        waiting_since=NOW - timedelta(hours=20),
    )
    _ticket(
        conn,
        "T-SAFETY",
        1,
        status="HUMAN_QUEUE",
        category=None,
        assigned_dept=None,
        priority=None,
        sla_resolution_target_h=None,
    )
    _ticket(conn, "T-DONE", 500, status="RESOLVED")
    _ticket(conn, "T-NEW", 1, status="NEW", sla_resolution_target_h=None)  # 규칙 전
    # TS_LV 에서 현장서비스로 이관 → 받은 부서 목록에 보인다 (0.30)
    _ticket(conn, "T-ESC", 30, status="ESCALATED", escalated_to="FIELD_SVC")

    rows = run(conn, "work_list", "work_list", now=NOW)

    assert [r["ticket_id"] for r in rows] == [
        "T-SAFETY",
        "T-OTHER",
        "T-RISK",
        "T-ESC",
        "T-WAIT",
        "T-LOW",
    ]
    by_id = {r["ticket_id"]: r for r in rows}
    assert by_id["T-RISK"]["sla_ratio"] == 0.8 and by_id["T-RISK"]["at_risk"] is True
    assert by_id["T-WAIT"]["sla_ratio"] == 0.2 and by_id["T-WAIT"]["at_risk"] is False
    # 마감 = 접수 + 목표 100시간 + 대기 30시간
    assert by_id["T-WAIT"]["sla_due_at"] == NOW - timedelta(hours=50) + timedelta(hours=130)
    assert by_id["T-SAFETY"]["sla_ratio"] is None and by_id["T-SAFETY"]["at_risk"] is True

    only_lv = run(conn, "work_list", "work_list", now=NOW, dept="TS_LV")
    assert [r["ticket_id"] for r in only_lv] == ["T-RISK", "T-WAIT", "T-LOW"]
    conn.execute(sa.text("UPDATE tickets SET assignee = 'AG-TS_LV-01' WHERE ticket_id = 'T-RISK'"))
    mine = run(conn, "work_list", "work_list", now=NOW, assignee="AG-TS_LV-01")
    assert [(r["ticket_id"], r["assignee"]) for r in mine] == [("T-RISK", "AG-TS_LV-01")]
    only_field = run(conn, "work_list", "work_list", now=NOW, dept="FIELD_SVC")
    assert [(r["ticket_id"], r["assigned_dept"]) for r in only_field] == [("T-ESC", "FIELD_SVC")]


@needs_db
def test_dept_dashboard(conn) -> None:
    _ticket(conn, "T-1", 10)  # 진행 중
    _ticket(conn, "T-2", 80)  # 경고
    _ticket(conn, "T-3", 120)  # 위반
    _ticket(conn, "T-4", 10, assigned_dept="TS_MV", category="DEFECT")
    # TS_LV 에서 TS_MV 로 이관 → TS_MV 몫
    _ticket(conn, "T-5", 10, category="DEFECT", status="ESCALATED", escalated_to="TS_MV")
    _ticket(  # 분류 없이 사람 큐로 간 안전 건 → 미배정 행, 경고
        conn,
        "T-SAFE",
        1,
        status="HUMAN_QUEUE",
        category=None,
        assigned_dept=None,
        priority=None,
        sla_resolution_target_h=None,
    )
    for ticket_id, action, reason in [
        ("T-1", "approve", None),
        ("T-2", "rewrite", "TONE"),  # 결정 아님
        ("T-2", "edit_approve", "FACT_ERROR"),
        ("T-3", "reject", "FACT_ERROR"),
        ("T-4", "edit_approve", "ROUTING_ERROR"),
    ]:
        _review(conn, ticket_id, action, reason)
    _review(conn, "T-1", "approve", days_ago=30)  # 지난달 (since 로 거른다)
    # 한국 시간 월요일(10/19) 0시 30분 = UTC 일요일 15시 30분 → 한국 기준 주(10/19)에 든다
    monday_kst = datetime(2026, 10, 18, 15, 30, tzinfo=UTC)
    conn.execute(
        sa.text(
            "INSERT INTO reviews (ticket_id, action, reviewer, info_items, created_at) "
            "VALUES ('T-5', 'approve', 'r', '[]', :c)"
        ),
        {"c": monday_kst},
    )

    status = run(conn, "dept_dashboard", "dept_status", now=NOW)
    assert status == [
        {"assigned_dept": None, "open_count": 1, "at_risk_count": 1, "breached_count": 0},
        {"assigned_dept": "TS_LV", "open_count": 3, "at_risk_count": 1, "breached_count": 1},
        {"assigned_dept": "TS_MV", "open_count": 2, "at_risk_count": 0, "breached_count": 0},
    ]
    only_mv = run(conn, "dept_dashboard", "dept_status", now=NOW, dept="TS_MV")
    assert [r["assigned_dept"] for r in only_mv] == ["TS_MV"]  # 미배정 행은 전체 볼 때만

    weekly = run(conn, "dept_dashboard", "review_outcomes_weekly", since=NOW - timedelta(days=7))
    lv = next(r for r in weekly if r["assigned_dept"] == "TS_LV")
    assert (lv["decided"], lv["approved"], lv["edit_approved"], lv["rejected"]) == (3, 1, 1, 1)
    assert lv["approve_rate"] == 0.333 and lv["category"] == "TECH_SPEC"
    week = datetime(2026, 10, 19).date()
    assert [(r["week"], r["decided"]) for r in weekly if r["assigned_dept"] == "TS_MV"] == [
        (week, 2)  # T-4 수정 후 승인 + 이관된 T-5 승인(월요일 새벽)
    ]
    utc_weeks = run(
        conn,
        "dept_dashboard",
        "review_outcomes_weekly",
        dept="TS_MV",
        tz="UTC",
        since=NOW - timedelta(days=7),
    )
    assert [r["week"] for r in utc_weeks] == [week, datetime(2026, 10, 12).date()]

    reasons = run(conn, "dept_dashboard", "feedback_reasons", since=NOW - timedelta(days=7))
    # 재작성(rewrite)에 붙은 TONE 은 결정이 아니라 빠진다
    assert [(r["feedback_reason"], r["count"]) for r in reasons] == [
        ("FACT_ERROR", 2),
        ("ROUTING_ERROR", 1),
        ("WEAK_EVIDENCE", 0),
        ("TONE", 0),
    ]
    assert reasons[0]["share"] == 0.667
    only_mv = run(conn, "dept_dashboard", "feedback_reasons", dept="TS_MV")
    assert [r["count"] for r in only_mv if r["feedback_reason"] == "ROUTING_ERROR"] == [1]


@needs_db
def test_eval_join(conn, tmp_path) -> None:
    from cs_agent.db.queries import load_tickets_gold, ticket_results_view

    header = (
        "ticket_id,data_split,language,body_language,customer_tier,product_code,category_code,"
        "urgency_flag,priority,priority_rule_id,priority_adjusted_by_agent,assigned_dept,"
        "routing_rule_id,required_info,missing_info,missing_blocking_info,info_request_sent,"
        "reference_doc_id,reference_section"
    )
    lines = [
        "G-1,valid,en,en,GOLD,ACB-AS-2000,DEFECT,NONE,P3,PR-05,N,TS_LV,RT-X,"
        "serial_no;photos,serial_no;photos,serial_no,Y,TG-ACB-AS-2000,3.1",
        "G-2,valid,en,en,GOLD,,QUOTE,NONE,P4,PR-07,Y,SALES,RT-Y,,,,N,POL-ORDER,",
        "G-3,test,en,en,GOLD,,QUOTE,NONE,P4,PR-07,N,SALES,RT-Y,,,,N,,",
        "G-5,valid,en,en,GOLD,ACB-AS-2000,DEFECT,NONE,P3,PR-05,N,TS_LV,RT-X,,,,N,,",
        "G-4,train,en,en,GOLD,,QUOTE,NONE,P4,PR-07,N,SALES,RT-Y,,,,N,,",
    ]
    csv_path = tmp_path / "tickets.csv"
    csv_path.write_text("\n".join([header, *lines]) + "\n", encoding="utf-8")

    assert load_tickets_gold(conn, csv_path) == 4  # train 은 넣지 않는다
    assert load_tickets_gold(conn, csv_path) == 4  # 다시 돌려도 됨

    # G-1: 같은 원본으로 두 번 실행 → 늦은 것(run2)을 쓴다
    _ticket(conn, "T-OLD", 5, thread_ref="run1:G-1", category="TECH_SPEC")
    _ticket(
        conn,
        "T-1",
        1,
        thread_ref="run2:G-1",
        category="DEFECT",
        priority="P3",
        missing_info=["serial_no"],
        route="info_request",
    )
    evidence = [
        {"source": "cases", "doc_id": "RC-1", "text": "c"},
        {"source": "docs", "doc_id": "DS-ACB-AS-2000", "section": "2.1", "text": "d"},
        {"source": "docs", "doc_id": "TG-ACB-AS-2000", "section": "3.1", "text": "d"},
    ]
    conn.execute(
        sa.text(
            "INSERT INTO drafts (ticket_id, version, kind, text, template, slots, cited, "
            "evidence, checks, fix_notes, model) VALUES ('T-1', 1, 'draft', 't', '', '{}', "
            "'[]', CAST(:e AS jsonb), '[]', '[]', '')"
        ),
        {"e": json.dumps(evidence)},
    )
    # G-2: 우선순위가 상담원 조정이라 규칙 값(P3)과 다르다, 근거는 문서만 맞으면 된다
    _ticket(
        conn, "T-2", 1, thread_ref="G-2", category="QUOTE", assigned_dept="SALES", priority="P3"
    )
    conn.execute(
        sa.text(
            "INSERT INTO drafts (ticket_id, version, kind, text, template, slots, cited, "
            "evidence, checks, fix_notes, model) VALUES ('T-2', 1, 'draft', 't', '', '{}', "
            "'[]', CAST(:e AS jsonb), '[]', '[]', '')"
        ),
        {"e": json.dumps([{"source": "docs", "doc_id": "POL-ORDER", "section": "2"}])},
    )

    # G-5: 처리는 됐지만 분석 실패로 유형·부서·우선순위가 비었다 (route 도 없음)
    _ticket(
        conn,
        "T-5",
        1,
        thread_ref="G-5",
        status="ANALYSIS_PENDING",
        category=None,
        assigned_dept=None,
        priority=None,
        sla_resolution_target_h=None,
    )

    with ticket_results_view(conn):
        rows = {r["gold_ticket_id"]: r for r in run(conn, "eval_join", "ticket_results")}
        summary = run(conn, "eval_join", "eval_summary", split="valid")
    g1, g2, g3 = rows["G-1"], rows["G-2"], rows["G-3"]
    assert g1["ticket_id"] == "T-1" and g1["category_match"] and g1["dept_match"]
    assert (g1["missing_found_count"], g1["gold_missing_count"]) == (1, 2)
    assert g1["missing_info_match"] is False
    assert g1["evidence_match"] is True and g1["evidence_top3"] == [
        "DS-ACB-AS-2000#2.1",
        "TG-ACB-AS-2000#3.1",
    ]
    assert g1["info_request_sent"] is True and g1["gold_info_request_sent"] is True
    assert g2["evidence_match"] is True and g2["priority_match"] is False
    assert g3["ticket_id"] is None and g3["evidence_match"] is None
    g5 = rows["G-5"]
    assert g5["category_match"] is None and g5["info_request_sent"] is False

    total = next(r for r in summary if r["gold_category"] is None)
    assert (total["gold_count"], total["processed"]) == (3, 3)
    # 분석 실패(G-5)는 빈 비교라도 분모에 남아 틀린 것으로 센다
    assert total["category_accuracy"] == pytest.approx(2 / 3)
    assert total["dept_accuracy"] == pytest.approx(2 / 3)
    assert total["priority_rule_accuracy"] == 0.5  # 상담원 조정 건(G-2)은 빼고 G-1·G-5
    assert total["missing_info_exact"] == pytest.approx(2 / 3)
    assert total["missing_info_recall"] == 0.5
    assert total["evidence_top3"] == 1.0  # 정답 근거 없는 G-5 는 분모에서 뺀다
    assert total["info_request_accuracy"] == 1.0
    defect = next(r for r in summary if r["gold_category"] == "DEFECT")
    assert (defect["processed"], defect["category_accuracy"]) == (2, 0.5)  # 1.0 이 아니다


@needs_db
def test_live_case_usage(conn) -> None:
    _ticket(conn, "T-1", 1)
    _ticket(conn, "T-2", 1)
    for case_id, split in (("CASE-LIVE", "live"), ("RC-0001", "train")):
        conn.execute(
            sa.text(
                "INSERT INTO resolution_cases (case_id, text, summary, cause, action, final_reply,"
                " cited, edited, source_fix_needed, active, data_split) VALUES (:c, 't', '', '',"
                " '', '', '[]', false, false, true, :s)"
            ),
            {"c": case_id, "s": split},
        )
    evidence = {
        "T-1": [
            {"source": "cases", "doc_id": "CASE-LIVE"},
            {"source": "cases", "doc_id": "RC-0001"},
        ],
        "T-2": [{"source": "docs", "doc_id": "CASE-LIVE"}],  # 문서 근거는 세지 않는다
    }
    for ticket_id, items in evidence.items():
        conn.execute(
            sa.text(
                "INSERT INTO drafts (ticket_id, version, kind, text, template, slots, cited, "
                "evidence, checks, fix_notes, model) VALUES (:t, 1, 'draft', 't', '', '{}', "
                "'[]', CAST(:e AS jsonb), '[]', '[]', '')"
            ),
            {"t": ticket_id, "e": json.dumps(items)},
        )

    rows = run(conn, "eval_join", "live_case_usage", ticket_ids=["T-1", "T-2", "T-NONE"])

    assert rows == [{"ticket_id": "T-1", "live_cases": 1}, {"ticket_id": "T-2", "live_cases": 0}]


@needs_db
def test_eval_leaves_no_view_that_blocks_migrations(conn, tmp_path) -> None:
    from cs_agent.db.queries import load_tickets_gold, ticket_results_view
    from cs_agent.db.session import get_engine

    conn.execute(sa.text("CREATE SCHEMA eval"))
    conn.execute(sa.text("CREATE VIEW eval.ticket_results AS SELECT * FROM tickets"))  # 예전 버전
    conn.commit()
    csv_path = tmp_path / "tickets.csv"
    csv_path.write_text("ticket_id,data_split\n", encoding="utf-8")

    with get_engine(TEST_DATABASE_URL).connect() as evaluation:  # 평가 실행 연결
        load_tickets_gold(evaluation, csv_path)
        evaluation.commit()
        with ticket_results_view(evaluation):
            evaluation.commit()
            # 평가 중에도 뷰가 안 쓰는 열은 바꿀 수 있다
            conn.execute(sa.text("ALTER TABLE tickets DROP COLUMN assignee"))
            conn.rollback()  # 막히지 않는지만 본다 (마이그레이션 되돌리기를 위해 원상복구)
        evaluation.commit()

    # 영구 뷰(예전 버전)는 지워졌고, 풀에 돌아간 연결에도 임시 뷰가 남지 않는다
    views = conn.execute(sa.text("SELECT 1 FROM pg_views WHERE viewname = 'ticket_results'"))
    assert views.all() == []
    conn.execute(sa.text("ALTER TABLE tickets DROP COLUMN category"))  # 뷰가 쓰던 열
    conn.rollback()
