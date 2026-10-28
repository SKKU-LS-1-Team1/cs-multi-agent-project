// 내 문의: tickets.csv 의 상태값을 고객이 이해하기 쉬운 3단계로 옮긴다. 기록에 없는 이력은 만들지 않는다.
import data from '../data/inquiries.json'
import biz from '../data/biz.json'

export const customer = data.customer
export const pauseRule = data.pause_rule.replace(/^WAITING_CUSTOMER\((.*?)\)\s*/, '$1 ')
export const ESC_REASON = { SPEC_INTERPRETATION: '규격 해석', ONSITE_REQUIRED: '현장 확인 필요', QUALITY_RETURN: '품질 관련 반품', RMA_REQUIRED: 'RMA 필요', COMMERCIAL_TERMS: '상업 조건 협의', CAUSE_ANALYSIS: '원인 분석', FW_UPDATE_FAILURE: '펌웨어 업데이트 실패' }
export const dept = (c) => biz.depts[c] ?? c
export const fieldLabel = (k) => FIELD_KO[k] ?? data.labels[k] ?? k

export const CHANNEL = {
  EMAIL: { emoji: '✉️', label: '이메일' },
  PHONE: { emoji: '📞', label: '전화' },
  PARTNER_PORTAL: { emoji: '🌐', label: '파트너 포털' },
  WEB_FORM: { emoji: '📝', label: '웹 문의서' },
  CHAT: { emoji: '💬', label: '채팅' },
}

// 실제 상태값(NEW / IN_PROGRESS / ESCALATED / WAITING_CUSTOMER / RESOLVED / CLOSED) → 1·2·3단계
export const CHANNEL_SHORT = { EMAIL: '✉️ 이메일', PHONE: '📞 전화', PARTNER_PORTAL: '🌐 웹', WEB_FORM: '🌐 웹', CHAT: '💬 채팅' }
export const STATUS = {
  NEW: { stage: 1, emoji: '📥', label: '접수됐어요', note: '', kind: 'open' },
  IN_PROGRESS: { stage: 2, emoji: '🔍', label: '확인하고 있어요', note: '', kind: 'open' },
  ESCALATED: { stage: 2, emoji: '🏢', label: '전문 부서에서 확인하고 있어요', note: '', kind: 'open' },
  WAITING_CUSTOMER: { stage: 2, emoji: '✋', label: '추가 정보 필요', note: '', kind: 'need' },
  RESOLVED: { stage: 3, emoji: '✅', label: '처리가 완료됐어요', note: '', kind: 'done' },
  CLOSED: { stage: 3, emoji: '✅', label: '처리가 완료됐어요', note: '', kind: 'done' },
}
export const STEPS = [
  { n: 1, label: '접수 완료', icon: '📥' },
  { n: 2, label: '확인 · 처리 중', icon: '🔍' },
  { n: 3, label: '처리 완료', icon: '✅' },
]
export const FILTERS = [
  ['all', '전체', () => true],
  ['open', '진행 중', (t) => STATUS[t.status].kind !== 'done'],
  ['need', '추가 정보 필요', (t) => STATUS[t.status].kind === 'need'],
  ['done', '완료', (t) => STATUS[t.status].kind === 'done'],
]

export const FINAL_ACTION = {
  SPEC_ANSWERED: '사양 문의에 답변했어요', DOC_SENT: '요청하신 문서를 보냈어요', CERT_PROVIDED: '인증서를 안내했어요', QUOTE_ISSUED: '견적을 안내했어요',
  FAULT_RESOLVED_REMOTE: '원격으로 문제를 해결했어요', LEADTIME_CONFIRMED: '납기를 확인해 드렸어요', FW_PROVIDED: '펌웨어를 안내했어요', RMA_REPLACEMENT: '교체(RMA)로 진행했어요',
  CLOSED_NO_RESPONSE: '회신이 없어 종료했어요', WARRANTY_APPROVED: '보증이 승인됐어요', INSTALL_GUIDED: '설치 방법을 안내했어요', INSTALL_FAULT_FIXED: '설치 문제를 해결했어요',
  ONSITE_SCHEDULED: '현장 방문이 예정됐어요', ONSITE_REPAIR: '현장에서 수리했어요', RMA_ISSUED: 'RMA 번호가 발급됐어요', WARRANTY_REJECTED_EXPIRED: '보증 기간이 지나 보증이 적용되지 않았어요',
  FW_FIX_APPLIED: '펌웨어로 해결했어요', RMA_CREDIT: 'RMA(크레딧)로 진행했어요', DOC_FROM_LIBRARY: '자료실 문서를 안내했어요', CERT_NOT_AVAILABLE: '요청하신 인증이 없어요',
  FW_ESCALATED_RND: '펌웨어 개발팀으로 넘겼어요', PARTIAL_SHIPMENT: '나눠서 출하하기로 했어요', FW_ALREADY_LATEST: '이미 최신 펌웨어예요', SPEC_ESCALATED_CERT: '인증 담당 부서가 공식 답변을 줄 예정이에요',
  EXPEDITE_DECLINED: '납기 단축이 어려워요', RETURN_REJECTED: '반품이 받아들여지지 않았어요', WARRANTY_REJECTED_MISUSE: '사용 조건 때문에 보증이 적용되지 않았어요',
  DOC_SENT_EN_ONLY: '영문 문서로 보냈어요', QUOTE_TO_DISTRIBUTOR: '견적을 대리점으로 전달했어요', EXPEDITE_APPROVED: '납기 단축이 승인됐어요',
}
export const FIELD_KO = {
  product_model: '제품 모델명(주문 코드)', serial_no: '시리얼 번호(명판)', application: '사용 용도(전압·부하·사용 방식)', target_standard: '필요한 규격·인증서', target_country: '사용할 국가·시장',
  site_condition: '설치 환경(온도·고도·습도)', wiring_diagram: '배선도·단선도', photos: '제품·명판 사진', purchase_doc: 'PO 또는 송장 번호', install_date: '설치·시운전 날짜',
  failure_description: '고장 내용과 발생 시각', po_number: 'PO 번호', quantity: '수량', required_date: '희망 납기일', incoterms: '인도 조건과 도착지', document_type: '필요한 문서 종류',
  doc_language: '원하는 문서 언어', error_code: '화면에 표시된 에러 코드·증상', operating_condition: '고장 당시 운전 조건', logs: '이벤트·트립 기록', current_fw: '현재 펌웨어 버전',
  tool_version: '엔지니어링 툴 버전', return_reason: '반품 사유', packaging_condition: '도착 시 포장 상태', parameter_backup: '파라미터 백업 파일', motor_nameplate: '모터 명판 정보',
  program_backup: 'PLC·HMI 프로젝트 백업', battery_status: '이벤트 시점 배터리 상태', load_profile: '부하 전류·온도 기록', oil_test: '절연유 시험(DGA) 보고서',
  string_config: 'PV 스트링 구성', battery_age: '배터리 설치일·사용 기간',
}

export const split = (s) => (s ? s.split(';').filter(Boolean) : [])
export const fmtTime = (iso) => (iso ? `${iso.slice(0, 10)} ${iso.slice(11, 16)} (UTC)` : null)
export const titleOf = (t) => (t.inquiry_subject || `${t.inquiry_body.replace(/\s+/g, ' ').slice(0, 42)}${t.inquiry_body.length > 42 ? '…' : ''}`)
export const attachmentsOf = (t) => [...t.inquiry_body.matchAll(/\[attachment: ([^\]]+)\]/g)].map((m) => m[1])

export const tickets = data.tickets
