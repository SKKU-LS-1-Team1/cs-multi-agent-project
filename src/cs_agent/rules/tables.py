# 기준표 로더 (CSA-19 기준표 정리 · 담당 박종석 · Sprint 1)
#
# 규칙 처리(⑤)·근거 확정(⑧)·자동 점검(⑩)·화면 이동이 모두 여기 표를 읽는다.
# 규칙은 코드가 아니라 파일에 둔다 (N-02). 파일은 data/ref/ 에 있다.
#
# data/ref/ 현재 상태 (원본 ref/ 파일은 제공되지 않는다. 아래 표가 이 프로젝트의 정식 기준표다)
# - sla_policy.csv      복원본 (tickets 의 SLA 목표값과 100% 일치)
# - routing_rules.csv   tickets 에서 역산 (제품군 × 유형 → 담당 부서). tickets 4,000건 중 3,824건
#                       일치, 나머지 176건은 모두 RETURN 비불량 → SCM 예외 (할 일 4)
# - required_info.csv   tickets 에서 역산 (유형 × 제품군 → 필수 항목). 4,000건 모두 일치.
#                       blocking_info(처리 차단 항목)는 missing_blocking_info 빈도로 추정한 값
# - priority_rules.csv  tickets 에서 역산 (PR-01~07). 규칙과 다른 등급은 상담원이 조정한 건
#                       (priority_adjusted_by_agent)
# - product_master.csv  doc_index 의 데이터시트 23개. 대분류(POWER/AUTOMATION/ENERGY)는 가정
# - navigation_rules.csv 기획서 5.4 표 (CSA-33)
#
# 할 일
# 1. 위 표를 tickets 와 다시 대조해 검수한다 (routing_rule_id·priority_rule_id·required_info 열
#    일치율). 원본은 없으므로 표를 고칠 때는 tickets 를 근거로 삼고 팀에 알린다.
# 2. 추가할 표: product_spec_facts(사양값), fault_catalog(에러코드 97건), firmware_history,
#    warranty(제품별 보증기간), price_list(정가·최소 주문·표준 납기). 답변 슬롯을 여기서 채운다.
# 3. load_tables(): 위 CSV를 읽어 RefTables 로 돌려준다. 한 번만 읽도록 캐시(lru_cache).
# 4. 이관 규칙(예: RETURN 비불량 → SCM, RT-ALL-RETURN-NON_DEFECT)도 표로 정리한다.
#
# 완료 기준: 김동규 님 규칙 처리(CSA-22)가 이 표만으로 valid 부서·우선순위 일치율을 낼 수 있음
#
# 만들 것 (이름·모양은 다른 파일이 이대로 부른다)
#
#   @dataclass(frozen=True)
#   class Product:
#       code: str
#       name: str
#       family: str
#       division: str
#
#   @dataclass(frozen=True)
#   class RefTables:
#       products: dict[str, Product]
#       routing: dict[tuple[str, str], tuple[str, str]]  # (family, category) -> (rule_id, dept)
#       required: dict[tuple[str, str], tuple[list[str], list[str]]]  # -> (required, blocking)
#       priority: list[dict[str, str]]
#       sla: dict[tuple[str, str, str], dict[str, str]]  # (category, tier, priority) -> row
#       navigation: dict[str, dict[str, str]]  # intent -> row (CSA-33)
#
#   def load_tables(ref_dir: Path | None = None) -> RefTables:
#       """data/ref/*.csv → RefTables. 경로 기본값은 config.Settings.ref_dir."""
