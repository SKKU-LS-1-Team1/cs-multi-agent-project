# 구조

기획서 v10 9장·9.1·9.2와 `analysis/agent-architecture/에이전트_구조_제안.md` 를 파일 구조로 옮긴 골격이다.

## 처리 흐름 (LangGraph, `src/cs_agent/graph/builder.py`)

슈퍼바이저 = 코드가 순서를 정한 그래프. LLM은 분류·추출(Jev), 요청문·답변 작성(Gemini), 근거 검증에만 쓴다.

```
① 접수 ─┬ ② 분류 ─┐
        ├ ③ 추출 ─┼→ ⑤ 규칙 처리 → ⑥ 분기 ─┬ 안전 → 사람 큐
        └ ④ 검색 ─┘                      ├ 차단성 누락 → ⑦ 추가정보 요청문 → 상담원 검토
                                         └ 정상 → ⑧ 근거 확정 → ⑨ 답변 작성 → ⑩ 자동 점검
⑩ 통과 → 상담원 검토 (interrupt) / 실패 → ⑨ 재작성 (최대 2회) / 초과 → 보류 → 상담원 검토
상담원 검토 → 승인 · 수정 후 승인 · AI 재작성 · 추가정보 요청 · 전문부서 이관 · 반려
해결 확정 → 사례 DB 저장 (기획서 7.1)
```

상담원 검토 지점에서 그래프가 멈추고(체크포인트), `POST /api/tickets/{id}/action` 이 `Command(resume=...)` 로 같은 그래프를 이어서 돌린다.

## 폴더

| 폴더 | 내용 |
|---|---|
| `src/cs_agent/graph/` | 상태(`TicketState`)와 그래프 조립 |
| `src/cs_agent/agents/` | 문의 분석 · 추가정보 요청 · 지식 검색 · 답변 작성 · 자동 점검 · 사례 저장 |
| `src/cs_agent/chatbot/` | 챗봇 대화 · 화면 이동 · 문의서 작성 · 문의 전환 |
| `src/cs_agent/rules/` | 기준표 로더 · 우선순위/부서/필수정보 · SLA |
| `src/cs_agent/llm/` | 모델 분기 (Jev 판단 / Gemini 작성) · Langfuse |
| `src/cs_agent/api/` | FastAPI 라우터 (`/api/tickets`, `/api/chat`, `/api/products`, `/api/dashboard`) |
| `src/cs_agent/db/` | PostgreSQL 모델 · SQL 쿼리 |
| `src/cs_agent/cache/` | Redis (캐시 · 호출 제한 · 챗봇 세션) |
| `src/cs_agent/pipeline/` | 데이터 정제 · 문서 청킹/임베딩 · mock 데이터 |
| `src/cs_agent/evaluation/` | KPI 계산 · 시험 문의 평가 |
| `data/ref/` | 기준표 CSV (아래 참고) |
| `frontend/` | React (고객 화면 · 관리자 화면) |
| `infra/` | Nginx · GCP 안내 |

## 지금 상태

`src/cs_agent/` 의 .py 파일은 코드 없이 주석만 있다. 파일 맨 위 주석에 담당·Jira 키·할 일·완료 기준·참고 문서가,
아래 "만들 것" 주석에 다른 파일이 부를 함수·클래스 모양이 적혀 있다. 이름과 모양은 그대로 맞춰서 구현한다.
`domain.py`·`schemas.py`·`graph/state.py` 는 팀이 같이 쓰는 값이라 먼저 만들고, 바꿀 때는 팀에 알린다.

## 기준표 (`data/ref/`)

받은 원본 기준표(`CS_AI_Agent_Training_Data_v1/ref/`)를 그대로 둔다. 파일별 내용과 읽는 방법은
`src/cs_agent/rules/tables.py` 맨 위 주석에 있다.
`navigation_rules.csv`(기획서 5.4, CSA-33)와 `family_divisions.csv`(제품군 → 대분류, CSA-19)는
원본에 없어서 직접 만든 표다. 기준표와 tickets 대조 검수는
`uv run python -m cs_agent.rules.tables` 로 한다.
