-- 평가용 조인 (CSA-20 · 담당 박종석) — 평가 스크립트 CSA-50 이 쓴다
--
-- 할 일
-- 1. 정답 테이블(tickets_gold: valid·test 분할의 원본 tickets)을 적재한다.
-- 2. 시스템 판단(tickets, drafts, reviews) vs 정답: 유형, 부서, 우선순위, 누락 항목, 근거 문서·절.
-- 3. KPI 정의는 analysis/kpi/KPI_설정안.md (K1~K5).
--
-- 정해 둔 것
-- - 평가용 테이블·뷰는 eval 스키마에 둔다. Alembic 은 기본 스키마만 비교하므로 마이그레이션
--   (db/models.py ↔ DB 비교, autogenerate)에 걸리지 않는다.
-- - 적재: db/queries.py load_tickets_gold(conn) 가 data/raw/tickets.csv 의 valid·test 를 넣는다
--   (create_eval_schema → create_tickets_gold → upsert_tickets_gold, 다시 돌려도 됨).
-- - 시스템 티켓 ↔ 정답 연결: 시스템 ticket_id 는 새로 매겨지므로(T-…), 평가 스크립트가 문의를
--   낼 때 InquiryIn.thread_ref 에 원본 ticket_id 를 넣는다. "실행ID:원본ID" 처럼 앞에 붙여도 된다
--   (마지막 ':' 뒤를 원본 ID 로 본다). 같은 원본이 여러 번 들어오면 가장 늦게 접수된 것을 쓴다.
-- - KPI (analysis/kpi/KPI_설정안.md 정의를 따른다. 여기서 낼 수 있는 것만):
--     K3 근거 일치: 마지막 답변 초안의 docs 근거 상위 3개에 정답 문서(절이 있으면 절까지)
--     K4 부서·우선순위 일치
--     K5 누락 항목 재현율: 정답 missing_info 중 시스템이 찾은 비율
--   K1(지연 p95)은 Langfuse, K2(무수정 승인)는 상담원 검토가 있어야 해서 여기서 내지 않는다
--   (ticket_results.review_action 으로 볼 수는 있다).


-- name: create_eval_schema
CREATE SCHEMA IF NOT EXISTS eval;


-- name: create_tickets_gold
-- 목록형 값(required_info 등)은 tickets 쪽과 같은 jsonb 배열로 둔다.
CREATE TABLE IF NOT EXISTS eval.tickets_gold (
    ticket_id text PRIMARY KEY,
    data_split text NOT NULL,
    language text,
    body_language text,
    customer_tier text,
    product_code text,
    category text NOT NULL,
    urgency_flag text,
    priority text,
    priority_rule_id text,
    priority_adjusted_by_agent boolean NOT NULL DEFAULT false,
    assigned_dept text,
    routing_rule_id text,
    required_info jsonb NOT NULL DEFAULT '[]',
    missing_info jsonb NOT NULL DEFAULT '[]',
    missing_blocking_info jsonb NOT NULL DEFAULT '[]',
    info_request_sent boolean NOT NULL DEFAULT false,
    reference_doc_id text,
    reference_section text,
    loaded_at timestamptz NOT NULL DEFAULT now()
);


-- name: upsert_tickets_gold
INSERT INTO eval.tickets_gold (
    ticket_id, data_split, language, body_language, customer_tier, product_code, category,
    urgency_flag, priority, priority_rule_id, priority_adjusted_by_agent, assigned_dept,
    routing_rule_id, required_info, missing_info, missing_blocking_info, info_request_sent,
    reference_doc_id, reference_section
) VALUES (
    :ticket_id, :data_split, :language, :body_language, :customer_tier, :product_code, :category,
    :urgency_flag, :priority, :priority_rule_id, :priority_adjusted_by_agent, :assigned_dept,
    :routing_rule_id, CAST(:required_info AS jsonb), CAST(:missing_info AS jsonb),
    CAST(:missing_blocking_info AS jsonb), :info_request_sent, :reference_doc_id,
    :reference_section
)
ON CONFLICT (ticket_id) DO UPDATE SET
    data_split = EXCLUDED.data_split,
    language = EXCLUDED.language,
    body_language = EXCLUDED.body_language,
    customer_tier = EXCLUDED.customer_tier,
    product_code = EXCLUDED.product_code,
    category = EXCLUDED.category,
    urgency_flag = EXCLUDED.urgency_flag,
    priority = EXCLUDED.priority,
    priority_rule_id = EXCLUDED.priority_rule_id,
    priority_adjusted_by_agent = EXCLUDED.priority_adjusted_by_agent,
    assigned_dept = EXCLUDED.assigned_dept,
    routing_rule_id = EXCLUDED.routing_rule_id,
    required_info = EXCLUDED.required_info,
    missing_info = EXCLUDED.missing_info,
    missing_blocking_info = EXCLUDED.missing_blocking_info,
    info_request_sent = EXCLUDED.info_request_sent,
    reference_doc_id = EXCLUDED.reference_doc_id,
    reference_section = EXCLUDED.reference_section,
    loaded_at = now();


-- name: create_ticket_results
-- 정답 1건마다 시스템 판단과 일치 여부. 시스템 티켓이 아직 없으면 시스템 열은 NULL.
CREATE OR REPLACE VIEW eval.ticket_results AS
SELECT
    g.ticket_id AS gold_ticket_id,
    g.data_split,
    g.language,
    t.ticket_id,
    t.status,
    -- 유형
    g.category AS gold_category,
    t.category,
    t.category = g.category AS category_match,
    -- 부서 (K4, 게이트)
    g.assigned_dept AS gold_dept,
    t.assigned_dept,
    t.assigned_dept = g.assigned_dept AS dept_match,
    g.routing_rule_id AS gold_routing_rule_id,
    t.routing_rule_id,
    -- 우선순위 (K4). 정답이 상담원 조정이면 규칙과 다른 게 정상이라 따로 표시한다
    g.priority AS gold_priority,
    t.priority,
    t.priority = g.priority AS priority_match,
    g.priority_rule_id AS gold_priority_rule_id,
    t.priority_rule_id,
    g.priority_adjusted_by_agent,
    -- 누락 항목 (K5)
    g.missing_info AS gold_missing_info,
    t.missing_info,
    t.missing_info @> g.missing_info AND g.missing_info @> t.missing_info AS missing_info_match,
    jsonb_array_length(g.missing_info) AS gold_missing_count,
    (
        SELECT count(*)
        FROM jsonb_array_elements_text(g.missing_info) AS gold_item (field)
        WHERE t.missing_info ? gold_item.field
    ) AS missing_found_count,
    g.missing_blocking_info AS gold_missing_blocking,
    t.missing_blocking,
    -- 추가정보 요청 여부
    g.info_request_sent AS gold_info_request_sent,
    CASE WHEN t.ticket_id IS NULL THEN NULL ELSE info.requested END AS info_request_sent,
    -- 근거 문서·절 (K3). 정답 근거가 없는 문의는 NULL
    g.reference_doc_id AS gold_reference_doc_id,
    g.reference_section AS gold_reference_section,
    top_docs.doc_ids AS evidence_top3,
    CASE
        WHEN t.ticket_id IS NULL OR COALESCE(g.reference_doc_id, '') = '' THEN NULL
        ELSE EXISTS (
            SELECT 1
            FROM jsonb_array_elements(COALESCE(draft.evidence, '[]')) WITH ORDINALITY
                AS ev (value, ord)
            WHERE ev.value ->> 'source' = 'docs'
                AND ev.value ->> 'doc_id' = g.reference_doc_id
                AND (
                    COALESCE(g.reference_section, '') = ''
                    OR ev.value ->> 'section' = g.reference_section
                )
                AND (
                    SELECT count(*)
                    FROM jsonb_array_elements(draft.evidence) WITH ORDINALITY AS prev (value, ord)
                    WHERE prev.value ->> 'source' = 'docs' AND prev.ord <= ev.ord
                ) <= 3
        )
    END AS evidence_match,
    -- 상담원 마지막 버튼 (K2 참고용)
    last_review.action AS review_action
FROM eval.tickets_gold AS g
LEFT JOIN LATERAL (
    SELECT tk.*
    FROM tickets AS tk
    WHERE regexp_replace(tk.thread_ref, '^.*:', '') = g.ticket_id
    ORDER BY tk.received_at DESC
    LIMIT 1
) AS t ON true
LEFT JOIN LATERAL (
    SELECT d.evidence
    FROM drafts AS d
    WHERE d.ticket_id = t.ticket_id AND d.kind = 'draft'
    ORDER BY d.version DESC
    LIMIT 1
) AS draft ON true
LEFT JOIN LATERAL (
    SELECT array_agg(
        (ev.value ->> 'doc_id') || COALESCE('#' || (ev.value ->> 'section'), '') ORDER BY ev.ord
    ) AS doc_ids
    FROM (
        SELECT e.value, e.ord
        FROM jsonb_array_elements(COALESCE(draft.evidence, '[]')) WITH ORDINALITY AS e (value, ord)
        WHERE e.value ->> 'source' = 'docs'
        ORDER BY e.ord
        LIMIT 3
    ) AS ev
) AS top_docs ON true
LEFT JOIN LATERAL (
    SELECT
        t.route = 'info_request'
        OR EXISTS (
            SELECT 1 FROM drafts AS d WHERE d.ticket_id = t.ticket_id AND d.kind = 'info_request'
        ) AS requested
) AS info ON true
LEFT JOIN LATERAL (
    SELECT r.action
    FROM reviews AS r
    WHERE r.ticket_id = t.ticket_id
    ORDER BY r.id DESC
    LIMIT 1
) AS last_review ON true;


-- name: ticket_results
-- 정답 1건씩 (틀린 건 목록·유형별/언어별 분석용). :split NULL 이면 전체
SELECT *
FROM eval.ticket_results
WHERE CAST(:split AS text) IS NULL OR data_split = CAST(:split AS text)
ORDER BY gold_ticket_id;


-- name: eval_summary
-- split 별, split × 정답 유형별 일치율. 시스템 티켓이 없는 정답은 processed 에서 빠진다.
SELECT
    data_split,
    gold_category,
    count(*) AS gold_count,
    count(ticket_id) AS processed,
    CAST(avg(CAST(category_match AS int)) AS double precision) AS category_accuracy,
    CAST(avg(CAST(dept_match AS int)) AS double precision) AS dept_accuracy,
    CAST(avg(CAST(priority_match AS int)) AS double precision) AS priority_accuracy,
    CAST(avg(CAST(priority_match AS int)) FILTER (WHERE NOT priority_adjusted_by_agent)
        AS double precision) AS priority_rule_accuracy,
    CAST(avg(CAST(missing_info_match AS int)) AS double precision) AS missing_info_exact,
    CAST(
        sum(missing_found_count) FILTER (WHERE ticket_id IS NOT NULL)
        / NULLIF(sum(gold_missing_count) FILTER (WHERE ticket_id IS NOT NULL), 0)
        AS double precision
    ) AS missing_info_recall,
    CAST(avg(CAST(evidence_match AS int)) AS double precision) AS evidence_top3,
    CAST(avg(CAST(info_request_sent = gold_info_request_sent AS int)) AS double precision)
        AS info_request_accuracy
FROM eval.ticket_results
WHERE CAST(:split AS text) IS NULL OR data_split = CAST(:split AS text)
GROUP BY GROUPING SETS ((data_split), (data_split, gold_category))
ORDER BY data_split, gold_category NULLS FIRST;
