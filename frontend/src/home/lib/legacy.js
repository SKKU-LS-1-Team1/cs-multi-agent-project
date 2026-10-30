// 오래된 제품(단종·호환·대체) 문의. 모델 선택 목록에 "단종 · 호환 · 대체 문의" 선택지를 두어 문의서로 바로 보낸다.
// 제품 데이터에 출시·단종 정보가 없고, 오래된 제품이면 고객이 이미 알고 있어서 사용 기간을 묻지 않는다.

export const LEGACY_TYPE = 'LEGACY'
export const LEGACY_NAME = '단종 · 호환 · 대체'
// 상담 중인 제품 카드에서는 문의 유형 태그가 아니라 제품 이름 옆 괄호로 표시한다(제품의 상태라서 '제품 고장' 같은 경로와 같은 위계가 아니다).
export const LEGACY_TOPIC = '단종·호환'

// 선택지를 보여 주는 제품군: 저압차단기·고압전력기기(VCB·MV 스위치기어)·변압기. 현업 확인 후 늘리거나 줄인다.
export const LEGACY_FAMILIES = ['LV_BREAKER', 'MV_EQUIP', 'TRANSFORMER']
export const hasLegacy = (family) => LEGACY_FAMILIES.includes(family)

// ---- 문의서: 단종·호환 유형의 담당 부서와 질문 (생성 파일 biz.json은 고치지 않고 여기서 덧붙인다)
// 담당 부서·에스컬레이션은 목업 가정이다(현업 확정 필요). 제품군별 기술지원이 받고, 교체 견적이 필요하면 해외영업 운영으로 넘긴다.
const ROUTE = (primary) => ({ primary, escalation: 'SALES_OPS', cond: '교체 견적·대체 모델 주문이 필요한 경우', source: 'LEGACY_OVERLAY' })
export const LEGACY_ROUTING = { LV_BREAKER: ROUTE('TS_LV'), MV_EQUIP: ROUTE('TS_MV'), TRANSFORMER: ROUTE('TS_TRF') }
// 대상이 아닌 제품군에서 이 유형을 고른 경우: 담당을 정하지 못하므로 글로벌 C/S 센터가 먼저 받는다
export const LEGACY_FALLBACK_ROUTE = { primary: 'GCS_L1', escalation: null, cond: '담당 제품 확인이 필요한 경우', source: 'LEGACY_OVERLAY' }
export const legacyRoute = (family) => LEGACY_ROUTING[family] ?? LEGACY_FALLBACK_ROUTE

// 문의서는 모든 질문을 채워야 제출할 수 있다(inquiryForm.js 규칙). 오래된 제품은 명판이 지워져 시리얼 같은 것을 못 읽는 일이 많아
// 고객이 막히지 않도록 질문을 4개로 줄였다. 현재 상태·설치 공간 같은 나머지는 상세 내용 초안(legacyDraft)에 적어 두고 고객이 자유롭게 쓴다.
export const LEGACY_FIELDS = [
  { key: 'product_model', blocking: false },
  { key: 'manufacture_year', blocking: false },
  { key: 'legacy_goal', blocking: true },
  { key: 'photos', blocking: false },
]

// 모델 선택에서 문의서로 넘길 초안. model을 주지 않으면(모델을 아직 고르지 않았다) 문의서에서 모델을 묻는다.
export const legacyDraft = ({ family, familyName, model = '__unknown' }) => ({
  type: LEGACY_TYPE, family, model,
  subject: `${familyName} 단종 · 호환 문의`.slice(0, 100),
  body: '지금 상태(운전 중 · 고장 · 철거 예정):\n기존 제품이 들어간 자리의 크기나 연결 방식(알면):\n',
})
