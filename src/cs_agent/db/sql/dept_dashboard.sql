-- 부서별 대시보드 (CSA-20 · 담당 박종석) — 관리자 화면 CSA-43 이 쓴다
--
-- 할 일
-- 1. 부서별: 진행 중 건수, SLA 75% 경고 건수, SLA 위반 건수
-- 2. 부서 × 유형별: 그대로 승인 비율 / 수정 후 승인 비율 / 반려 비율 (reviews.action 기준, 주 단위)
-- 3. 수정 사유(feedback_reason) 4개 분포 — 피드백 루프 우선순위 판단용 (기획서 7장)
--
-- 부르는 법: db/queries.py  run(conn, "dept_dashboard", "dept_status", dept=None, now=None)
-- 파라미터 (모두 NULL 가능)
--   :dept           부서 코드. NULL 이면 전체
--   :now            기준 시각. NULL 이면 now() (테스트에서 고정할 때 넣는다)
--   :at_risk_ratio  경고 기준. NULL 이면 0.75 (settings.sla_at_risk_ratio)
--   :since          이 시각 이후 검토만 (review_outcomes_weekly, feedback_reasons). NULL 이면 전체
--
-- SLA 경과 비율은 work_list.sql 과 같은 계산이다:
--   (지금 − 접수 − 고객 대기) / 해결 목표 시간. 고객 대기 = customer_wait_hours(끝난 대기 누적)
--   + WAITING_CUSTOMER 인 동안의 지금 − waiting_since (SLA 정지, rules/sla.py).
-- 경고 = 0.75 ≤ 비율 < 1, 위반 = 비율 ≥ 1 (경고 건수에 위반 건은 넣지 않는다).


-- name: dept_status
-- 1. 부서별 지금 열려 있는 티켓 · SLA 75% 경고 · SLA 위반 건수
WITH params AS (
    SELECT
        COALESCE(CAST(:now AS timestamptz), now()) AS as_of,
        COALESCE(CAST(:at_risk_ratio AS double precision), 0.75) AS at_risk_ratio
),
open_tickets AS (
    SELECT
        t.assigned_dept,
        p.at_risk_ratio,
        GREATEST(
            EXTRACT(EPOCH FROM (p.as_of - t.received_at)) / 3600.0
            - t.customer_wait_hours
            - CASE
                WHEN t.status = 'WAITING_CUSTOMER' AND t.waiting_since IS NOT NULL
                    THEN EXTRACT(EPOCH FROM (p.as_of - t.waiting_since)) / 3600.0
                ELSE 0
            END,
            0
        ) / NULLIF(t.sla_resolution_target_h, 0) AS sla_ratio
    FROM tickets AS t
    CROSS JOIN params AS p
    WHERE t.status NOT IN ('APPROVED', 'REJECTED', 'RESOLVED')
        AND t.assigned_dept IS NOT NULL
        AND (CAST(:dept AS text) IS NULL OR t.assigned_dept = CAST(:dept AS text))
)
SELECT
    assigned_dept,
    count(*) AS open_count,
    count(*) FILTER (WHERE sla_ratio >= at_risk_ratio AND sla_ratio < 1) AS at_risk_count,
    count(*) FILTER (WHERE sla_ratio >= 1) AS breached_count
FROM open_tickets
GROUP BY assigned_dept
ORDER BY breached_count DESC, at_risk_count DESC, assigned_dept;


-- name: review_outcomes_weekly
-- 2. 부서 × 유형 × 주: 상담원 결정(그대로 승인·수정 후 승인·반려) 비율
--    재작성·추가정보 요청·이관은 결정이 아니라 다음 버튼을 기다리므로 분모에서 뺀다.
--    한 티켓이 다시 열려 두 번 결정되면 두 번 센다 (결정 이벤트 기준).
SELECT
    CAST(date_trunc('week', r.created_at AT TIME ZONE 'UTC') AS date) AS week,
    t.assigned_dept,
    t.category,
    count(*) AS decided,
    count(*) FILTER (WHERE r.action = 'approve') AS approved,
    count(*) FILTER (WHERE r.action = 'edit_approve') AS edit_approved,
    count(*) FILTER (WHERE r.action = 'reject') AS rejected,
    CAST(round(CAST(count(*) FILTER (WHERE r.action = 'approve') AS numeric) / count(*), 3)
        AS double precision) AS approve_rate,
    CAST(round(CAST(count(*) FILTER (WHERE r.action = 'edit_approve') AS numeric) / count(*), 3)
        AS double precision) AS edit_approve_rate,
    CAST(round(CAST(count(*) FILTER (WHERE r.action = 'reject') AS numeric) / count(*), 3)
        AS double precision) AS reject_rate
FROM reviews AS r
JOIN tickets AS t ON t.ticket_id = r.ticket_id
WHERE r.action IN ('approve', 'edit_approve', 'reject')
    AND (CAST(:dept AS text) IS NULL OR t.assigned_dept = CAST(:dept AS text))
    AND (CAST(:since AS timestamptz) IS NULL OR r.created_at >= CAST(:since AS timestamptz))
GROUP BY 1, t.assigned_dept, t.category
ORDER BY week DESC, t.assigned_dept, t.category;


-- name: feedback_reasons
-- 3. 수정 사유 4개(domain.FeedbackReason) 분포. 0건인 사유도 나온다.
WITH reasons (feedback_reason, ord) AS (
    VALUES ('FACT_ERROR', 1), ('WEAK_EVIDENCE', 2), ('TONE', 3), ('ROUTING_ERROR', 4)
),
counted AS (
    SELECT r.feedback_reason, count(*) AS n
    FROM reviews AS r
    JOIN tickets AS t ON t.ticket_id = r.ticket_id
    WHERE r.feedback_reason IS NOT NULL
        AND (CAST(:dept AS text) IS NULL OR t.assigned_dept = CAST(:dept AS text))
        AND (CAST(:since AS timestamptz) IS NULL OR r.created_at >= CAST(:since AS timestamptz))
    GROUP BY r.feedback_reason
)
SELECT
    reasons.feedback_reason,
    COALESCE(counted.n, 0) AS count,
    CAST(round(
        CAST(COALESCE(counted.n, 0) AS numeric)
        / NULLIF(sum(COALESCE(counted.n, 0)) OVER (), 0),
        3
    ) AS double precision) AS share
FROM reasons
LEFT JOIN counted ON counted.feedback_reason = reasons.feedback_reason
ORDER BY count DESC, reasons.ord;
