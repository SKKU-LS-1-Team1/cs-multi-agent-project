"""고객 관리는 실제 문의 행을 집계한다. 고객 마스터나 시연 명단을 생성하지 않는다."""

from collections import Counter, defaultdict
from datetime import UTC, datetime

from cs_agent.services.records import current_wait


def summarize_customers(rows: list[dict], now: datetime | None = None) -> list[dict]:
    now = now or datetime.now(UTC)
    try:
        cutoff = now.replace(year=now.year - 1)
    except ValueError:
        cutoff = now.replace(year=now.year - 1, day=28)
    groups = defaultdict(list)
    for row in rows:
        if row.get("customer_id") and row.get("received_at"):
            groups[row["customer_id"]].append(row)
    result = []
    for customer_id, items in sorted(groups.items()):
        items.sort(key=lambda r: (r["received_at"], r["ticket_id"]), reverse=True)
        latest = items[0]
        recent = [r for r in items if cutoff <= r["received_at"] <= now]
        recent_ids = {r["ticket_id"] for r in recent}
        families = Counter(r["product_family"] for r in recent if r.get("product_family"))
        urgent, safety, history = [], [], []
        breaches = 0
        for r in items:
            closed = r["status"] in {"RESOLVED", "CLOSED", "REJECTED"}
            end = r.get("resolved_at") if closed else now
            target = r.get("sla_resolution_target_h")
            elapsed = None
            if end is not None and target is not None and target > 0:
                wait = current_wait(r.get("waiting_since"), r.get("customer_wait_hours") or 0, end)
                elapsed = max(0, (end - r["received_at"]).total_seconds() / 3600 - wait)
            late = elapsed is not None and elapsed >= target
            if r["ticket_id"] in recent_ids and late:
                breaches += 1
            info = [r["ticket_id"], r.get("subject") or r["ticket_id"], r.get("priority") or "—"]
            if not closed and elapsed is not None and elapsed >= target * 0.75:
                urgent.append([*info, target, elapsed, r["status"]])
            if not closed and r.get("urgency_flag") == "SAFETY":
                safety.append([r["ticket_id"], info[1]])
            history.append(
                [
                    r["ticket_id"],
                    r["received_at"].isoformat(),
                    info[1],
                    r.get("category") or "미분류",
                    r.get("product_family") or "제품군 미확인",
                    info[2],
                    r["status"],
                    "BREACHED"
                    if late
                    else "MET"
                    if closed and elapsed is not None
                    else "ON_TRACK"
                    if elapsed is not None
                    else "UNKNOWN",
                ]
            )
        urgent.sort(key=lambda u: u[4] - u[3], reverse=True)
        result.append(
            dict(
                id=customer_id,
                name=customer_id,
                c=latest.get("country") or "",
                cn=latest.get("country") or "국가 미등록",
                tier=latest["customer_tier"],
                seg="업종 미등록",
                since="",
                n=len(recent),
                breach=breaches,
                last=latest["received_at"].isoformat(),
                fam=families.most_common(),
                urgent=urgent,
                urgentN=len(urgent),
                safety=safety,
                t=history,
                notice_tickets=[
                    dict(
                        id=r["ticket_id"],
                        title=r.get("subject") or r["ticket_id"],
                        status=r["status"],
                        language=r.get("language"),
                    )
                    for r in items
                    if r["status"] not in {"RESOLVED", "CLOSED", "REJECTED"}
                ],
            )
        )
    return result
