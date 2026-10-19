-- 평가용 (CSA-20 · CSA-50): 시스템 판단 vs 정답 비교용 조인 뼈대
-- TODO(CSA-20): 정답 테이블(tickets_gold) 적재 후 사용
SELECT
    t.ticket_id,
    t.category AS pred_category,
    g.category_code AS gold_category,
    t.assigned_dept AS pred_dept,
    g.assigned_dept AS gold_dept,
    t.priority AS pred_priority,
    g.priority AS gold_priority
FROM tickets t
JOIN tickets_gold g ON g.ticket_id = t.ticket_id;
