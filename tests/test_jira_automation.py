import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from jira_automation import (  # noqa: E402
    DONE,
    IN_PROGRESS,
    IN_REVIEW,
    TODO,
    closing_keys,
    keys_in,
    plan,
)


def branch_created(ref):
    return "create", {"ref_type": "branch", "ref": ref}


def pr(action, number, title, branch, body="", merged=False, draft=False):
    return "pull_request", {
        "action": action,
        "pull_request": {
            "number": number,
            "title": title,
            "body": body,
            "head": {"ref": branch},
            "merged": merged,
            "draft": draft,
            "html_url": f"https://github.com/x/y/pull/{number}",
        },
    }


def run(events, status_of, open_pr_keys=frozenset()):
    status_of = dict(status_of)
    for event, payload in events:
        for a in plan(event, payload, status_of, open_pr_keys):
            status_of[a.key] = a.to
    return status_of


def test_keys_from_title_and_branch_only():
    assert keys_in("CSA-21 CSA-22 제목", "feature/CSA-21-x") == ["CSA-21", "CSA-22"]
    assert closing_keys("참고 CSA-18\nCloses CSA-17, CSA-19") == {"CSA-17", "CSA-19"}
    assert closing_keys("fixes: CSA-3") == {"CSA-3"}
    assert closing_keys("CSA-18·24 이후") == set()


def test_branch_created_moves_todo_only():
    status = run([branch_created("feature/CSA-22-rules")], {"CSA-22": TODO})
    assert status["CSA-22"] == IN_PROGRESS
    assert run([branch_created("feature/CSA-22-rules")], {"CSA-22": DONE})["CSA-22"] == DONE


def test_draft_pr_is_not_review():
    status = run([pr("opened", 9, "CSA-22 x", "feature/CSA-22", draft=True)], {"CSA-22": TODO})
    assert status["CSA-22"] == TODO


def test_pr_body_reference_keys_are_ignored():
    body = "CSA-18·24 이후 저장. @박종석 님 CSA-19 로 남김"
    status = run(
        [pr("opened", 5, "CSA-22 규칙", "feature/CSA-22", body=body)],
        {"CSA-22": TODO, "CSA-18": TODO, "CSA-19": TODO},
    )
    assert status == {"CSA-22": IN_REVIEW, "CSA-18": TODO, "CSA-19": TODO}


def test_close_without_merge_returns_to_in_progress():
    status = run([pr("closed", 7, "CSA-30 x", "feature/CSA-30")], {"CSA-30": IN_REVIEW})
    assert status["CSA-30"] == IN_PROGRESS


def test_merge_keeps_review_while_another_pr_is_open():
    events = [pr("closed", 3, "CSA-21 a", "feature/CSA-21-a", merged=True)]
    assert run(events, {"CSA-21": IN_REVIEW}, open_pr_keys={"CSA-21"})["CSA-21"] == IN_REVIEW


def test_replay_today_2026_10_19():
    """오늘(10/19) 실제 브랜치·PR 순서대로 재생."""
    start = {k: TODO for k in ["CSA-15", "CSA-17", "CSA-19", "CSA-21", "CSA-22"]}
    pr4_title = "CSA-17 원천 데이터 추가, CSA-19 원본 기준표로 교체"
    pr3_title = "CSA-21 Jira 기준 전체 스켈레톤 코드"
    pr5_title = "CSA-21 CSA-22 CSA-15 공용 스키마·규칙 처리·SLA·사례 저장 기초"
    events = [
        branch_created("feature/CSA-21-skeleton"),
        pr("opened", 3, pr3_title, "feature/CSA-21-skeleton"),
        branch_created("feature/CSA-17-raw-data"),
        pr("opened", 4, pr4_title, "feature/CSA-17-raw-data"),
        pr("closed", 3, pr3_title, "feature/CSA-21-skeleton", merged=True),
        pr("closed", 4, pr4_title, "feature/CSA-17-raw-data", merged=True),
        branch_created("feature/CSA-21-core-rules-memory"),
        pr("opened", 5, pr5_title, "feature/CSA-21-core-rules-memory", body="CSA-18·24 이후"),
    ]
    assert run(events, start) == {
        "CSA-15": IN_REVIEW,  # PR #5 검토 중
        "CSA-17": IN_PROGRESS,  # 원천 데이터만 머지, 정제·분리는 남음
        "CSA-19": IN_PROGRESS,  # 검수·대분류 남음
        "CSA-21": IN_REVIEW,  # 스켈레톤 머지 후 PR #5 검토 중
        "CSA-22": IN_REVIEW,
    }
