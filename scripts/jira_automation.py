"""GitHub 이벤트로 Jira 이슈 상태를 옮기는 자동화 규칙 (CSA-14).

`.github/workflows/jira-automation.yml` 이 브랜치 생성·PR 이벤트마다 실행한다.

규칙 (이슈 키는 브랜치 이름과 PR 제목에서만 읽는다. 본문의 참고용 키는 무시)
  R1 브랜치 생성            해야 할 일 → 진행 중
  R2 PR 열림·다시 열림·리뷰 요청 가능  해야 할 일/진행 중 → 검토 중
  R3 PR 머지 + 본문 "Closes CSA-n"   → 완료 (그 키만)
  R4 PR 머지(닫는 키 아님) 또는 머지 없이 닫힘
                            검토 중 → 진행 중 (같은 키의 다른 열린 PR이 있으면 그대로)
상태를 뒤로 돌리는 것은 R4 하나뿐이고, 완료 이슈는 R3 말고는 건드리지 않는다.

환경변수 JIRA_BASE_URL · JIRA_USER_EMAIL · JIRA_API_TOKEN 이 없으면 계획만 출력한다(dry-run).
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass

KEY_RE = re.compile(r"\bCSA-\d+\b")
CLOSE_RE = re.compile(
    r"\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s*:?\s+((?:CSA-\d+[\s,]*)+)", re.I
)

TODO, IN_PROGRESS, IN_REVIEW, DONE = "해야 할 일", "진행 중", "검토 중", "완료"


@dataclass(frozen=True)
class Action:
    key: str
    to: str
    rule: str
    comment: str


def keys_in(*texts: str | None) -> list[str]:
    seen: dict[str, None] = {}
    for text in texts:
        for key in KEY_RE.findall(text or ""):
            seen[key] = None
    return list(seen)


def closing_keys(text: str | None) -> set[str]:
    return {k for group in CLOSE_RE.findall(text or "") for k in KEY_RE.findall(group)}


def plan(
    event: str,
    payload: dict,
    status_of: dict[str, str],
    open_pr_keys: set[str] = frozenset(),
) -> list[Action]:
    """이벤트 하나에 대해 할 일을 정한다. Jira·GitHub 호출 없음."""
    actions: list[Action] = []

    def move(key: str, allowed_from: set[str], to: str, rule: str, comment: str) -> None:
        if status_of.get(key) in allowed_from:
            actions.append(Action(key, to, rule, comment))

    if event == "create" and payload.get("ref_type") == "branch":
        branch = payload["ref"]
        for key in keys_in(branch):
            move(key, {TODO}, IN_PROGRESS, "R1", f"브랜치 생성: `{branch}`")
        return actions

    if event != "pull_request":
        return actions

    pr = payload["pull_request"]
    act = payload.get("action")
    keys = keys_in(pr.get("title"), pr["head"]["ref"])
    link = f"PR #{pr['number']} {pr.get('title', '')} ({pr.get('html_url', '')})"

    if act in {"opened", "reopened", "ready_for_review"} and not pr.get("draft"):
        for key in keys:
            move(key, {TODO, IN_PROGRESS}, IN_REVIEW, "R2", f"검토 요청: {link}")
    elif act == "closed":
        merged = bool(pr.get("merged"))
        closes = closing_keys(pr.get("body")) | closing_keys(pr.get("title")) if merged else set()
        for key in keys_in(*keys, *sorted(closes)):
            if key in closes:
                move(key, {TODO, IN_PROGRESS, IN_REVIEW}, DONE, "R3", f"머지로 완료: {link}")
            elif key not in open_pr_keys:
                why = "머지됨(닫는 키 아님)" if merged else "머지 없이 닫힘"
                move(key, {IN_REVIEW}, IN_PROGRESS, "R4", f"{why}: {link}")
    return actions


class Jira:
    def __init__(self, base_url: str, email: str, token: str) -> None:
        self.base = base_url.rstrip("/")
        cred = base64.b64encode(f"{email}:{token}".encode()).decode()
        self.headers = {
            "Authorization": f"Basic {cred}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def _call(self, method: str, path: str, body: dict | None = None) -> dict:
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base + path, data, self.headers, method=method)
        with urllib.request.urlopen(req, timeout=20) as res:
            raw = res.read()
        return json.loads(raw) if raw else {}

    def status(self, key: str) -> str | None:
        try:
            return self._call("GET", f"/rest/api/3/issue/{key}?fields=status")["fields"]["status"][
                "name"
            ]
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            raise

    def apply(self, action: Action) -> None:
        trans = self._call("GET", f"/rest/api/3/issue/{action.key}/transitions")["transitions"]
        tid = next(t["id"] for t in trans if t["to"]["name"] == action.to)
        path = f"/rest/api/3/issue/{action.key}"
        self._call("POST", f"{path}/transitions", {"transition": {"id": tid}})
        text = {"type": "text", "text": f"[자동화 {action.rule}] {action.comment}"}
        doc = {"type": "doc", "version": 1, "content": [{"type": "paragraph", "content": [text]}]}
        self._call("POST", f"/rest/api/3/issue/{action.key}/comment", {"body": doc})


def open_pr_keys_from_github(repo: str, token: str, exclude: int | None) -> set[str]:
    url = f"https://api.github.com/repos/{repo}/pulls?state=open&per_page=100"
    req = urllib.request.Request(
        url, headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}
    )
    with urllib.request.urlopen(req, timeout=20) as res:
        pulls = json.load(res)
    return {
        key
        for p in pulls
        if p["number"] != exclude
        for key in keys_in(p["title"], p["head"]["ref"])
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--event", default=os.environ.get("GITHUB_EVENT_NAME"))
    ap.add_argument("--payload", default=os.environ.get("GITHUB_EVENT_PATH"))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    with open(args.payload, encoding="utf-8") as f:
        payload = json.load(f)

    env = os.environ
    creds = [env.get("JIRA_BASE_URL"), env.get("JIRA_USER_EMAIL"), env.get("JIRA_API_TOKEN")]
    dry = args.dry_run or not all(creds)
    jira = None if dry else Jira(*creds)  # type: ignore[arg-type]

    pr = payload.get("pull_request") or {}
    candidates = keys_in(
        payload.get("ref") if args.event == "create" else None,
        pr.get("title"),
        (pr.get("head") or {}).get("ref"),
        " ".join(sorted(closing_keys(pr.get("body")))),
    )
    if jira:
        status_of = {k: s for k in candidates if (s := jira.status(k))}
    else:
        # dry-run: 실제 상태를 모르면 각 규칙이 적용될 수 있는 상태로 가정
        assumed = IN_REVIEW if payload.get("action") == "closed" else TODO
        status_of = {k: assumed for k in candidates}

    open_keys: set[str] = set()
    pr_closed = args.event == "pull_request" and payload.get("action") == "closed"
    if pr_closed and env.get("GITHUB_TOKEN"):
        open_keys = open_pr_keys_from_github(
            env["GITHUB_REPOSITORY"], env["GITHUB_TOKEN"], pr.get("number")
        )

    actions = plan(args.event, payload, status_of, open_keys)
    print(f"event={args.event} action={payload.get('action')} keys={candidates} dry_run={dry}")
    for a in actions:
        print(f"  {a.rule} {a.key}: {status_of.get(a.key)} → {a.to}  ({a.comment})")
        if jira:
            jira.apply(a)
    if not actions:
        print("  변경 없음")
    return 0


if __name__ == "__main__":
    sys.exit(main())
