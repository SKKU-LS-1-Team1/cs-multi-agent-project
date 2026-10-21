-- 상담원 작업 목록 (CSA-20 · 담당 박종석) — 관리자 화면 CSA-40 이 쓴다
--
-- 할 일
-- 1. 해결·반려되지 않은 티켓을 SLA 경과 비율(경과 시간 − 고객 대기 시간) / 해결 목표 시간이 큰 순으로.
-- 2. 열: ticket_id, category, priority, assigned_dept, assignee, status, sla_due_at, sla_ratio,
--    at_risk(≥ 0.75)
-- 3. :dept 파라미터로 부서 필터, :assignee 로 담당자 필터 (NULL 이면 전체, CSA-53).
--    담당자 필터를 주면 부서 큐(담당자 없음)·사람 큐 안전 건은 빠진다.
-- 4. 테이블·열 이름은 db/models.py (CSA-24) 확정본을 따른다.
--
-- 부르는 법: db/queries.py  run(conn, "work_list", "work_list", dept=None, now=None)
-- 파라미터 (모두 NULL 가능): :dept, :assignee, :now(NULL 이면 now()), :at_risk_ratio(NULL 이면 0.75)
--
-- 정해 둔 것 (services/tickets.py work_list 를 CSA-40 에서 이 SQL 로 바꾼다. 그 전까지 Python 쪽은
-- 고객 대기 시간을 빼지 않아 대기했던 티켓의 sla_ratio·sla_due_at 이 여기와 다르다)
-- - 닫힌 상태 = APPROVED · REJECTED · RESOLVED (services/tickets.py CLOSED).
-- - 부서 = 이관됐으면 이관 부서(escalated_to), 아니면 assigned_dept. 부서 필터·assigned_dept 열 모두
--   이 값이다 (이관된 건은 받은 부서 목록에 보여야 한다).
-- - 고객 대기 = customer_wait_hours(끝난 대기 누적) + WAITING_CUSTOMER 인 동안 지금 − waiting_since.
--   대기 중에는 SLA 시계가 멈추므로 비율이 커지지 않고, 마감(sla_due_at)은 대기만큼 뒤로 간다
--   (rules/sla.py due_at·elapsed_hours 와 같은 식).
-- - 규칙이 아직 없는 티켓(해결 목표 시간 없음)은 빼되, 분류 없이 사람 큐로 간 안전 건
--   (HUMAN_QUEUE · 부서 없음)은 부서 필터가 없을 때 맨 위에 둔다 (sla_ratio NULL, at_risk true —
--   유형·부서·SLA 를 상담원이 정해야 해서 경고로 보인다).
-- - 같은 비율이면 먼저 접수된 순.


-- name: work_list
WITH params AS (
    SELECT
        COALESCE(CAST(:now AS timestamptz), now()) AS as_of,
        COALESCE(CAST(:at_risk_ratio AS double precision), 0.75) AS at_risk_ratio
),
open_tickets AS (
    SELECT
        t.*,
        COALESCE(t.escalated_to, t.assigned_dept) AS dept,
        p.as_of,
        p.at_risk_ratio,
        t.customer_wait_hours
        + CASE
            WHEN t.status = 'WAITING_CUSTOMER' AND t.waiting_since IS NOT NULL
                THEN EXTRACT(EPOCH FROM (p.as_of - t.waiting_since)) / 3600.0
            ELSE 0
        END AS wait_hours
    FROM tickets AS t
    CROSS JOIN params AS p
    WHERE t.status NOT IN ('APPROVED', 'REJECTED', 'RESOLVED')
        AND (
            (t.sla_resolution_target_h IS NOT NULL AND t.assigned_dept IS NOT NULL)
            OR (t.status = 'HUMAN_QUEUE' AND t.assigned_dept IS NULL)
        )
        AND (
            CAST(:dept AS text) IS NULL
            OR COALESCE(t.escalated_to, t.assigned_dept) = CAST(:dept AS text)
        )
        AND (CAST(:assignee AS text) IS NULL OR t.assignee = CAST(:assignee AS text))
),
measured AS (
    SELECT
        *,
        GREATEST(EXTRACT(EPOCH FROM (as_of - received_at)) / 3600.0 - wait_hours, 0)
        / NULLIF(sla_resolution_target_h, 0) AS ratio
    FROM open_tickets
)
SELECT
    ticket_id,
    category,
    priority,
    dept AS assigned_dept,
    assignee,
    status,
    received_at + make_interval(secs => (sla_resolution_target_h + wait_hours) * 3600)
        AS sla_due_at,
    CAST(round(CAST(ratio AS numeric), 3) AS double precision) AS sla_ratio,
    -- 사람 큐 안전 건은 비율이 없어도 경고로 보인다 (services/tickets.py _unruled_row)
    CASE WHEN ratio IS NULL THEN status = 'HUMAN_QUEUE' ELSE ratio >= at_risk_ratio END AS at_risk
FROM measured
ORDER BY ratio DESC NULLS FIRST, received_at, ticket_id;
