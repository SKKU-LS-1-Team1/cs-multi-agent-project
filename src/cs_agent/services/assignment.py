# 담당 부서·담당자 자동 배정 + 재배정 (CSA-53 · 담당 김동규 · Sprint 2) — 명세서 S-03
#
# 부서는 규칙 처리(⑤, rules/engine.py)가 routing_rules 로 이미 정한다 (RuleResult.assigned_dept,
# 이관되면 escalated_to). 여기서는 그 부서 안에서 담당 상담원을 고르고, SLA 75% 경고 시 다른
# 상담원에게 넘길 수 있게 한다. 관리자 화면 쪽은 CSA-54 (김도연).
#
# 정해 둔 것
# - 담당자 명단: data/ref/agents.csv (agent_id, name, dept_code, active, max_open). 시작할 때 읽고
#   (main.py), 표가 틀리면(없는 부서 코드·겹치는 agent_id·active 가 Y/N 아님) 시작을 멈춘다.
#   파일이 없으면 빈 명단 → 배정하지 않는다 (assignee NULL, 부서 큐에 남음).
# - 자동 배정 assign(): 부서 안 활성 담당자 중 지금 열린 건이 가장 적은 사람. 같으면 agent_id 순.
#   max_open(0 이면 제한 없음)에 이미 찬 사람은 뺀다. 다 찼으면 None (부서 큐).
#   services/tickets.py 가 그래프를 돌린 뒤마다 부른다: 아직 담당자가 없거나, 이관으로 부서가 바뀌어
#   지금 담당자가 그 부서 사람이 아닐 때. 사람 큐 안전 건(부서 없음)·닫힌 건은 배정하지 않는다.
# - 재배정 reassign(): 같은 부서 활성 담당자만 (다른 부서로 보내는 건 이관 ReviewAction.ESCALATE).
#   상담원·관리자가 직접 넘길 때는 max_open 을 넘어도 허용한다 (사람이 정한 것).
#   75% 경고 건은 화면에서 suggest() 후보를 보여 준다.
# - 저장: tickets.assignee + 배정 이력 assignments (from·to·사유·누가). services/records.py.
#   assignee 는 그래프 상태에 넣지 않는다 (save_state 가 덮어쓰지 않게, records 에서만 읽고 쓴다).
# - API: POST /api/tickets/{id}/assign, GET /api/tickets?assignee=, GET /api/agents?dept=
#
# 완료 기준
# - 부서가 정해진 문의는 접수 직후 담당자가 정해져 있음 (명단이 있을 때)
# - 75% 경고 건을 같은 부서 다른 담당자로 넘기면 작업 목록·이력에 반영
# - 다른 부서 담당자로 넘기려 하면 409
#
# 참고: 명세서 S-03, db/sql/work_list.sql (부서 = COALESCE(escalated_to, assigned_dept))
import csv
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

COLUMNS = ("agent_id", "name", "dept_code", "active", "max_open")


@dataclass(frozen=True)
class Agent:
    agent_id: str
    name: str
    dept: str
    active: bool = True
    max_open: int = 0  # 0 이면 제한 없음


def load_agents(path: Path | None = None, depts: set[str] | None = None) -> list[Agent]:
    """data/ref/agents.csv → 담당자 명단. 파일이 없으면 []. 표가 틀리면 ValueError."""
    from cs_agent.config import get_settings

    ref_dir = get_settings().ref_dir
    path = path or ref_dir / "agents.csv"
    if not path.exists():
        return []
    if depts is None:
        with (ref_dir / "departments.csv").open(encoding="utf-8-sig", newline="") as f:
            depts = {r["dept_code"] for r in csv.DictReader(f)}
    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if tuple(reader.fieldnames or ()) != COLUMNS:
            raise ValueError(f"{path.name}: 열은 {','.join(COLUMNS)} 이어야 한다")
        rows = list(reader)

    agents: list[Agent] = []
    seen: set[str] = set()
    for line, r in enumerate(rows, start=2):
        where = f"{path.name}:{line}"
        agent_id = r["agent_id"].strip()
        if not agent_id or agent_id in seen:
            raise ValueError(f"{where}: agent_id 가 비었거나 겹친다: {agent_id!r}")
        if r["dept_code"] not in depts:
            raise ValueError(f"{where}: departments.csv 에 없는 부서: {r['dept_code']!r}")
        if r["active"] not in ("Y", "N"):
            raise ValueError(f"{where}: active 는 Y 또는 N: {r['active']!r}")
        try:
            max_open = int(r["max_open"] or 0)
        except ValueError:
            raise ValueError(f"{where}: max_open 은 정수: {r['max_open']!r}") from None
        if max_open < 0:
            raise ValueError(f"{where}: max_open 은 0 이상: {max_open}")
        seen.add(agent_id)
        agents.append(
            Agent(agent_id, r["name"].strip(), r["dept_code"], r["active"] == "Y", max_open)
        )
    return agents


def _in_dept(dept: str, agents: Sequence[Agent]) -> list[Agent]:
    return [a for a in agents if a.dept == dept and a.active]


def assign(dept: str | None, open_counts: Mapping[str, int], agents: Sequence[Agent]) -> str | None:
    """부서 안에서 열린 건이 가장 적은 활성 담당자 agent_id. 없거나 모두 찼으면 None."""
    if not dept:
        return None
    candidates = [
        a
        for a in _in_dept(dept, agents)
        if a.max_open == 0 or open_counts.get(a.agent_id, 0) < a.max_open
    ]
    if not candidates:
        return None
    return min(candidates, key=lambda a: (open_counts.get(a.agent_id, 0), a.agent_id)).agent_id


def suggest(
    ticket_dept: str,
    current: str | None,
    open_counts: Mapping[str, int],
    agents: Sequence[Agent],
) -> list[Agent]:
    """재배정 후보 (같은 부서 활성, 지금 담당자 제외, 열린 건 적은 순)."""
    candidates = [a for a in _in_dept(ticket_dept, agents) if a.agent_id != current]
    return sorted(candidates, key=lambda a: (open_counts.get(a.agent_id, 0), a.agent_id))


def reassign(ticket_dept: str, to: str, agents: Sequence[Agent]) -> Agent:
    """넘길 담당자 확인. 없거나 다른 부서·비활성이면 ValueError (API 는 409)."""
    agent = next((a for a in agents if a.agent_id == to), None)
    if agent is None:
        raise ValueError(f"없는 담당자: {to}")
    if not agent.active:
        raise ValueError(f"비활성 담당자: {to}")
    if agent.dept != ticket_dept:
        raise ValueError(
            f"{to} 는 {agent.dept} 소속이라 {ticket_dept} 문의를 맡을 수 없다 (다른 부서는 이관)"
        )
    return agent
