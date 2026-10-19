-- 상담원 작업 목록 (CSA-20 · CSA-40): SLA 남은 비율 순, 75% 이상 경고
-- 고객 회신 대기 시간은 경과에서 뺀다.
SELECT
    t.ticket_id,
    t.category,
    t.priority,
    t.assigned_dept,
    t.status,
    t.sla_resolution_target_h,
    (EXTRACT(EPOCH FROM (now() - t.received_at)) / 3600 - t.customer_wait_hours)
        / NULLIF(t.sla_resolution_target_h, 0) AS sla_ratio
FROM tickets t
WHERE t.status NOT IN ('RESOLVED', 'REJECTED')
  AND (:dept IS NULL OR t.assigned_dept = :dept)
ORDER BY sla_ratio DESC NULLS LAST;
