# GitHub ↔ Jira 연동 가이드

Jira 사이트: https://skku-ls-team1.atlassian.net · 프로젝트 키: **CSA**

## 1. GitHub for Jira 앱 설치 (Jira 관리자, 1회)

1. Jira에서 **설정(⚙) → 앱 → Atlassian Marketplace 살펴보기** 로 이동해 **"GitHub for Atlassian"** 을 설치한다.
2. 앱 설정 화면에서 **Connect GitHub organization** → `SKKU-LS-1-Team1` 조직을 선택한다.
   (GitHub 조직 Owner 권한이 필요하다. 없으면 조직 Owner에게 설치 승인을 요청)
3. 저장소 접근 범위에 `cs-multi-agent-project` 가 포함되어 있는지 확인한다.
4. 연결 후 기존 이력은 백필(backfill)되고, 이후 활동은 실시간으로 동기화된다.

설치가 끝나면 Jira 이슈 오른쪽 **개발(Development)** 패널에 브랜치, 커밋, PR,
그리고 GitHub Actions 빌드 결과(CI 상태)가 자동으로 표시된다. 별도 토큰이나 시크릿은 필요 없다.

## 2. 이슈 키 규칙 (팀 전체)

Jira 연동은 **이슈 키(CSA-숫자)** 로 매칭된다. 아래 중 하나 이상에 키를 넣는다.

| 대상 | 예시 |
|------|------|
| 브랜치 | `feature/CSA-12-intent-classifier` |
| 커밋 | `CSA-12 의도 분류 에이전트 초안` |
| PR 제목 | `CSA-12 의도 분류 에이전트 추가` |

`Jira key check` 워크플로가 PR 제목/브랜치에 키가 없으면 실패 처리한다.

### 스마트 커밋 (선택)

커밋 메시지로 Jira 이슈를 조작할 수 있다. (GitHub 이메일이 Jira 계정 이메일과 같아야 함)

```
CSA-12 #comment 리뷰 반영 완료
CSA-12 #time 2h
CSA-12 #done
```

## 3. CI

`.github/workflows/ci.yml` 이 push(main)·PR마다 실행된다.

- `ruff check` / `ruff format --check` — 린트·포맷
- `pytest` — 테스트

로컬에서 동일하게 실행:

```bash
uv sync
uv run ruff check . && uv run ruff format --check . && uv run pytest
```
