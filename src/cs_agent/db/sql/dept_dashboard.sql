-- 부서별 대시보드 (CSA-20 · CSA-43): 처리량, 무수정 승인율, SLA 위반
-- TODO(CSA-20): 유형별·주 단위 집계 추가
SELECT
    t.assigned_dept,
    COUNT(*) AS tickets,
    AVG(CASE WHEN r.action = 'approve' THEN 1.0 ELSE 0 END) AS approve_as_is_rate,
    AVG(CASE WHEN r.action = 'edit_approve' THEN 1.0 ELSE 0 END) AS edit_rate,
    AVG(CASE WHEN r.action = 'reject' THEN 1.0 ELSE 0 END) AS reject_rate
FROM tickets t
LEFT JOIN reviews r ON r.ticket_id = t.ticket_id
GROUP BY t.assigned_dept
ORDER BY tickets DESC;
