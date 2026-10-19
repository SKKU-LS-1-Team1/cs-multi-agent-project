# 문의 처리 그래프 조립 (CSA-21 · 담당 김동규 · Sprint 1)
#
# 슈퍼바이저 = 코드가 순서를 정한 LangGraph StateGraph(TicketState). LLM이 다음 단계를 고르지
#   않는다.
#
# 만들 흐름
#   START → ① intake ─┬─ ② classify ─┐
#                     ├─ ③ extract  ──┼→ ⑤ rules → ⑥ 분기 ─┬ human → END (사람 큐, 초안 없음)
#                     └─ ④ retrieve ─┘                    ├ info_request → ⑦ → ready → review
#                                                         └ draft → ⑧ evidence → ⑨ draft → ⑩ verify
#   ⑩ verify ─┬ 통과 → ready → review
#             ├ 실패 · 재시도 남음 → ⑨ draft (실패 사유를 fix_notes 로)
#             └ 실패 · 재시도 초과 → hold(ON_HOLD) → review
#   review (interrupt: 상담원 버튼을 기다리며 멈춤) ─┬ approve / edit_approve / reject → finish →
#     END
#                                                ├ rewrite → ⑨ draft (상담원 피드백 포함, 재시도
#                                                  0으로)
#                                                ├ info_request → ⑦ → ready → review
#                                                └ escalate → escalate(상태·부서 변경, 알림) → END
#
# 할 일
# 1. GraphDeps(dataclass): llm(LLMRouter), docs·cases(Retriever), tables(RefTables), max_retries.
# 2. build_ticket_graph(deps, checkpointer): 위 노드·엣지를 만들고 compile 한다.
#    - ②③④ 병렬: intake 에서 세 노드로 add_edge, add_edge(["classify","extract","retrieve"],
#        "rules")
#    - 분기: add_conditional_edges
#    - 노드 함수는 짧게: 각 에이전트 모듈 함수를 부르고 바꾼 키만 돌려준다
# 3. review 노드: langgraph.types.interrupt({...}) 로 멈추고, 재개 값(ReviewIn)을 state.review 에
#      넣는다.
#    API(POST /api/tickets/{id}/action)가 Command(resume=ReviewIn.model_dump()) 로 이어서 돌린다.
#    interrupt 앞에서 상태를 바꾸면 재개 때 노드가 다시 실행되므로, 상태 표시는 ready 노드에서 한다.
# 4. finish: 승인 → APPROVED + final_reply (수정 후 승인이면 edited_text),
#    추가정보 요청문 승인 → WAITING_CUSTOMER (SLA 정지), 반려 → REJECTED.
# 5. 체크포인터: 개발은 MemorySaver, 운영은 PostgresSaver (langgraph-checkpoint-postgres,
#      CSA-24·25).
#    체크포인트에 넣는 Enum·모델은 JsonPlusSerializer(allowed_msgpack_modules=...)에 등록한다
#    (안 하면 역직렬화 경고).
# 6. 고객 회신이 오면 ① 접수에서 같은 thread_id 로 재개 (thread_ref 로 기존 티켓 찾기, 재문의 +1).
#
# 완료 기준: 단순 문의 1건이 접수 → 추천 답변 → 상담원 승인까지 끝까지 돈다 (Sprint 1 목표)
# 참고: 에이전트_구조_제안.md 2장, 관리자_대시보드_AI기능_구조검토.md 4장
