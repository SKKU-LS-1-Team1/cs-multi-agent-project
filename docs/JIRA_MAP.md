# Jira 작업 ↔ 코드 위치

Jira 프로젝트 **CSA** 의 에픽 9개(CSA-5~13)와 작업 45개(CSA-14~51, CSA-53~58, CSA-60)를 저장소 위치에 연결한 표다.
코드 안의 `TODO(CSA-n)` 는 그 작업에서 채울 자리다. `grep -rn "TODO(CSA-22)" src frontend` 로 찾는다.

브랜치·PR 제목에는 작업 키를 넣는다. 예: `feature/CSA-26-analysis-agent`, `CSA-26 문의 분석 에이전트 키워드 → Jev 분류`.

## CSA-5 프로젝트 관리·협업
| 키 | 작업 | 담당 | 스프린트 | 위치 |
|---|---|---|---|---|
| CSA-14 | Jira 에픽·스프린트 세팅, GitHub 연동 확인 | 김동규 | 1 | `docs/JIRA_INTEGRATION.md`, `.github/workflows/jira-key-check.yml` |
| CSA-15 | 피드백 루프 시연 방식 결정 | 김동규 | 1 | `src/cs_agent/agents/case_memory.py`, `services/tickets.py` (`review_log`, `cases`) |
| CSA-16 | 최종 발표 자료 준비·발표 | 김동규 | 2 | (코드 없음) |

## CSA-6 데이터·기준표
| 키 | 작업 | 담당 | 스프린트 | 위치 |
|---|---|---|---|---|
| CSA-17 | 상담 이력 정제, 학습·시험 분리 | 박종석 | 1 | `src/cs_agent/pipeline/prepare_data.py` |
| CSA-18 | 기술문서 나누기·임베딩 → pgvector | 박종석 | 1 | `pipeline/chunking.py`, `pipeline/embed_docs.py` |
| CSA-19 | 기준표 정리 (제품 기준정보, 규칙표, SLA 정책) | 박종석 | 1 | `data/ref/*.csv`, `rules/tables.py` |
| CSA-20 | SQL 쿼리 작성 (작업 목록·대시보드·평가용) | 박종석 | 2 | `src/cs_agent/db/sql/*.sql` |

## CSA-7 백엔드 처리 흐름
| 키 | 작업 | 담당 | 스프린트 | 위치 |
|---|---|---|---|---|
| CSA-21 | FastAPI 프로젝트 구조 + LangGraph 처리 흐름 골격 | 김동규 | 1 | `main.py`, `api/`, `graph/`, `services/tickets.py` |
| CSA-22 | 규칙 처리·SLA 계산 | 김동규 | 1 | `rules/engine.py`, `rules/sla.py` |
| CSA-23 | mock 데이터 생성 | 김동규 | 1 | `pipeline/mock_data.py` |
| CSA-24 | PostgreSQL 스키마 | 조수빈 | 1 | `db/models.py`, `db/session.py` |
| CSA-25 | 상담원 승인·수정·반려 API와 피드백 기록 | 김동규 | 2 | `api/tickets.py` (`/action`, `/resolve`), `graph/builder.py` (`review`) |
| CSA-53 | 담당 부서·담당자 자동 배정 + 재배정 API | 김동규 | 2 | `services/assignment.py`, `api/tickets.py` (`/assign`, `/assignments`), `api/agents.py`, `data/ref/agents.csv`, `services/records.py` (`set_assignee`) |

## CSA-8 상담 처리 에이전트
| 키 | 작업 | 담당 | 스프린트 | 위치 |
|---|---|---|---|---|
| CSA-26 | 문의 분석 에이전트 (유형·제품·에러코드) | 김도연 | 1 | `agents/analysis.py` |
| CSA-27 | 추가정보 요청 에이전트 | 김동규 | 1 | `agents/info_request.py` |
| CSA-28 | 지식 검색 에이전트 (답변·챗봇 공용) | 박종석 | 1 | `agents/retrieval.py` |
| CSA-29 | 답변 작성 – 단순 문의(정보 안내형) | 김도연 | 1 | `agents/drafting.py` |
| CSA-30 | 답변 작성 – 유형별(문서·영업·수리) 확장 | 김도연 | 2 | `agents/drafting.py` (`TEMPLATES`) |
| CSA-31 | 자동 점검(검증) 에이전트 | 김동규 | 2 | `agents/verification.py` |
| CSA-55 | 이관 요청서 작성 에이전트 (부서·사유·진단 요약·근거) | 김도연 | 2 | `agents/escalation.py` |
| CSA-57 | 원문 한국어 번역 생성 (상담원 표시용) | 김도연 | 2 | `agents/translation.py` |

## CSA-9 고객 챗봇 에이전트
| 키 | 작업 | 담당 | 스프린트 | 위치 |
|---|---|---|---|---|
| CSA-32 | 챗봇 대화 에이전트 | 조수빈 | 2 | `chatbot/agent.py`, `api/chat.py`, `cache/store.py` (`ChatSessionStore`) |
| CSA-33 | 화면 이동 규칙표 + 화면 이동 에이전트 | 조수빈 | 2 | `data/ref/navigation_rules.csv`, `chatbot/navigation.py` |
| CSA-34 | 문의서 작성 에이전트 | 조수빈 | 2 | `chatbot/form_filler.py` |
| CSA-35 | 문의 전환 기준값 확정 | 박종석 | 2 | `chatbot/handoff.py` |

## CSA-10 사용자 화면
| 키 | 작업 | 담당 | 스프린트 | 위치 |
|---|---|---|---|---|
| CSA-36 | 제품 대시보드 분류 트리 (대 3·중 11·소 23) | 조수빈 | 1 | `frontend/src/pages/customer/ProductTree.tsx` (API: CSA-60) |
| CSA-37 | 제품 상세 탭 화면 | 조수빈 | 1 | `frontend/src/pages/customer/ProductDetail.tsx` (API: CSA-60) |
| CSA-60 | 제품 대시보드 API (트리·상세 탭 내용) | 김동규 | 2 | `api/products.py`, `services/catalog.py` |
| CSA-38 | 우측 챗봇 창 + 대시보드 이동 연동 | 조수빈 | 2 | `frontend/src/pages/customer/ChatPanel.tsx`, `CustomerHome.tsx` |
| CSA-39 | 문의하기(자동 채움) · 내 문의 내역 | 조수빈 | 2 | `InquiryForm.tsx`, `MyInquiries.tsx` |

## CSA-11 관리자 화면
| 키 | 작업 | 담당 | 스프린트 | 위치 |
|---|---|---|---|---|
| CSA-40 | 상담원 작업 목록 (SLA 순, 75% 경고) | 김도연 | 2 | `frontend/src/pages/admin/WorkList.tsx`, `services/tickets.py` (`work_list`) |
| CSA-41 | 추천 답변 검토·승인·수정·반려 + 수정 사유 | 김도연 | 2 | `frontend/src/pages/admin/ReviewPage.tsx` |
| CSA-42 | 근거 문서·자동 점검 결과 표시 | 김도연 | 2 | `frontend/src/pages/admin/EvidencePanel.tsx` |
| CSA-43 | 부서별 대시보드 | 김도연 | 2 | `frontend/src/pages/admin/DeptDashboard.tsx`, `api/dashboard.py` |
| CSA-54 | 담당자 배정·재배정 (75% 경고 시 넘기기) | 김도연 | 2 | `frontend/src/pages/admin/WorkList.tsx`, `ReviewPage.tsx` (API: CSA-53) |
| CSA-56 | 이관 요청서 검토·전달 | 김도연 | 2 | `frontend/src/pages/admin/ReviewPage.tsx` (요청서: CSA-55) |
| CSA-58 | 원문·번역 보기 전환 | 김도연 | 2 | `frontend/src/pages/admin/ReviewPage.tsx` (번역: CSA-57) |

## CSA-12 인프라·배포
| 키 | 작업 | 담당 | 스프린트 | 위치 |
|---|---|---|---|---|
| CSA-44 | Docker Compose 구성 | 김도연 | 1 | `docker-compose.yml`, `Dockerfile`, `infra/nginx/` |
| CSA-45 | Redis 연동 (캐시, 호출 제한, 챗봇 세션) | 김동규 | 2 | `cache/store.py` |
| CSA-46 | GCP VM·도메인·HTTPS | 김동규 | 2 | `infra/gcp/README.md`, `infra/nginx/nginx.conf` |
| CSA-47 | GitHub Actions 배포 자동화 | 김동규 | 2 | `.github/workflows/deploy.yml` |

## CSA-13 평가·성과 측정
| 키 | 작업 | 담당 | 스프린트 | 위치 |
|---|---|---|---|---|
| CSA-48 | Langfuse 연동 (모든 LLM 호출 기록) | 김동규 | 1 | `llm/tracing.py`, `llm/router.py` |
| CSA-49 | 성과 지표 기준선 측정·목표치 확정 | 김동규 | 1 | `evaluation/metrics.py` |
| CSA-50 | 시험 문의 597건 평가 스크립트 | 박종석 | 2 | `evaluation/run_eval.py` |
| CSA-51 | 최종 시험 결과 정리 (MVP 시연용) | 박종석 | 2 | `evaluation/run_eval.py` 출력 → 발표 자료 |

`src/cs_agent/` 접두어는 생략했다.
