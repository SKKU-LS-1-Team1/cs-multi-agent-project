// 보증·주문·견적 흐름: 질문 목록과 결과를 정책(POL-*)과 ref 데이터로 만든다. 확정 판단은 하지 않는다.
import biz from '../data/biz.json'

export const UNKNOWN = '?'
export const NOTYET = 'notyet'
export const dept = (c) => biz.depts[c] ?? c
export const routingOf = (family, cat) => biz.routing[family]?.[cat]
export const requiredOf = (family, cat) => biz.required[family]?.[cat] ?? []

// ---------- 날짜 ----------
const midnight = (d) => { const x = new Date(d); x.setHours(0, 0, 0, 0); return x }
export const today = () => midnight(new Date())
export const parseDate = (s) => (s && /^\d{4}-\d{2}-\d{2}$/.test(s) ? midnight(new Date(`${s}T00:00:00`)) : null)
const addMonths = (d, m) => { const x = new Date(d); x.setMonth(x.getMonth() + m); return x }
export const ymd = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
const days = (a, b) => Math.round((b - a) / 86400000)

// ---------- 선택지 ----------
const DK = { v: UNKNOWN, label: '잘 모르겠어요', emoji: '🤔' }
export const REASONS = {
  doa: { label: '받았는데 처음부터 불량이에요', sub: '초기 불량 (DOA)', emoji: '📦', limit: 14, row: 'Dead on arrival (DOA)' },
  wrong: { label: '주문과 다른 제품이 왔어요', sub: '오배송', emoji: '🔀', limit: 14, row: 'Wrong item shipped' },
  damaged: { label: '배송 중에 파손됐어요', sub: '배송 파손', emoji: '💥', limit: 7, row: 'Shipping damage' },
  excess: { label: '주문을 잘못했거나 재고가 남았어요', sub: '주문 실수 · 잉여 재고', emoji: '🧾', limit: 30, row: 'Ordering error / excess stock' },
  used: { label: '이미 설치하거나 사용한 제품이에요', sub: '사용 · 설치 후', emoji: '🔧', limit: null, row: 'Used or installed units' },
  other: { label: '위에 없어요', sub: '담당자가 확인해요', emoji: '❔', limit: null },
}
const INCOTERMS = {
  fob: 'FOB Busan', exw: 'EXW Factory', other: 'CIF / CFR / DAP (요청 시 견적)',
}
export const LABEL = {
  w_goal: { check: '보증 확인', return: '교환·반품' },
  o_when: { pre: '구매 전 확인', existing: '기존 주문 문의' },
  q_inco: { ...INCOTERMS, [UNKNOWN]: '잘 모르겠어요' },
  q_custom: { std: '표준 사양 그대로', special: '표준 외 사양이 필요해요', [UNKNOWN]: '잘 모르겠어요' },
  w_partner: { yes: '예', no: '아니요', [UNKNOWN]: '잘 모르겠어요' },
  r_used: { no: '아니요, 새 제품 그대로예요', installed: '설치했어요', tried: '써 봤어요', [UNKNOWN]: '잘 모르겠어요' },
  r_pack: { orig: '원래 포장 그대로예요', opened: '포장을 뜯었거나 훼손됐어요', [UNKNOWN]: '잘 모르겠어요' },
  r_photo: { yes: '사진이 있어요', no: '사진이 없어요', [UNKNOWN]: '잘 모르겠어요' },
  o_topic: { lead: '납기 · 출하 시기가 궁금해요', expedite: '납기를 앞당기고 싶어요', partial: '나눠서 먼저 받고 싶어요', other: '그 밖의 문의' },
}
const opts = (id, extra = {}) => Object.entries(LABEL[id]).map(([v, label]) => ({ v, label, ...(extra[v] ?? {}) }))

// ---------- 질문 목록 (이전 답에 따라 필요한 것만) ----------
export function questionsFor(task, a) {
  if (task === 'warranty') {
    if (a.w_goal === 'return') {
      const r = a.r_reason
      return [
        { id: 'w_goal', type: 'choice', title: '무엇을 도와드릴까요?', options: [{ v: 'check', label: '보증 확인', sub: '보증 기간 · 조건 확인', emoji: '🛡️' }, { v: 'return', label: '교환 · 반품', sub: '사유를 알려 주세요', emoji: '🔁' }], src: { doc: 'POL-WARRANTY', sec: '1' } },
        { id: 'r_reason', type: 'choice', title: '어떤 일이 있었나요?', options: Object.entries(REASONS).map(([v, o]) => ({ v, label: o.label, sub: o.sub, emoji: o.emoji })), src: { doc: 'POL-RETURN', sec: '1' } },
        { id: 'r_deliv', type: 'date', title: '제품을 받은 날은 언제인가요?', sub: '배송 후 경과일로 정책 조건을 확인해요.', unknown: true, max: 'today', src: { doc: 'POL-RETURN', sec: '1' } },
        ...(r && !['damaged', 'used'].includes(r) ? [{ id: 'r_used', type: 'choice', title: '제품을 설치하거나 써 봤나요?', options: opts('r_used'), src: { doc: 'POL-RETURN', sec: '1', mark: 'Used or installed units' } }] : []),
        ...(r === 'excess' ? [{ id: 'r_pack', type: 'choice', title: '포장 상태는 어떤가요?', options: opts('r_pack'), src: { doc: 'POL-RETURN', sec: '1', mark: 'Ordering error / excess stock' } }] : []),
        ...(r === 'damaged' ? [{ id: 'r_photo', type: 'choice', title: '포장이 파손된 사진이 있나요?', sub: '파손은 사진과 함께 7일 안에 알려야 해요.', options: opts('r_photo'), src: { doc: 'POL-RETURN', sec: '1', mark: 'Shipping damage' } }] : []),
      ]
    }
    return [
      { id: 'w_goal', type: 'choice', title: '무엇을 도와드릴까요?', options: [{ v: 'check', label: '보증 확인', sub: '보증 기간 · 조건 확인', emoji: '🛡️' }, { v: 'return', label: '교환 · 반품', sub: '사유를 알려 주세요', emoji: '🔁' }], src: { doc: 'POL-WARRANTY', sec: '1' } },
      { id: 'w_ship', type: 'date', title: '제품이 출하된 날은 언제인가요?', sub: '보증은 시운전일부터 시작하지만, 늦어도 출하 6개월 뒤에는 시작돼요.', unknown: true, max: 'today', src: { doc: 'POL-WARRANTY', sec: '1' } },
      { id: 'w_comm', type: 'date', title: '시운전한 날은 언제인가요?', sub: '처음 켜서 설정을 마친 날이에요.', unknown: true, notyet: true, max: 'today', src: { doc: 'POL-WARRANTY', sec: '1' } },
      { id: 'w_excl', type: 'multi', title: '문제가 생긴 상황에 해당하는 게 있나요?', sub: '해당하면 정책상 보증에서 제외될 수 있어서, 담당자가 확인해요.', options: [
        { v: 'spec', label: '정격 밖에서 썼어요', sub: '잘못된 전압 · 과부하 · 주변 환경' },
        { v: 'damage', label: '물이 들어갔거나 충격을 받았어요', sub: '임의로 고친 적이 있어도 해당돼요' },
        { v: 'wear', label: '팬 · 배터리 · 필터 같은 소모품이에요', sub: '12개월이 지난 경우' },
      ], noneLabel: '해당하는 게 없어요', src: { doc: 'POL-WARRANTY', sec: '3' } },
      { id: 'w_partner', type: 'choice', title: '인증 파트너가 설치했나요?', sub: '현장 작업 비용 보증에 영향을 줘요.', options: opts('w_partner'), src: { doc: 'POL-WARRANTY', sec: '2' } },
    ]
  }
  if (task === 'order') {
    const pre = a.o_when === 'pre'
    return [
      { id: 'o_when', type: 'choice', title: '어떤 문의인가요?', options: [{ v: 'pre', label: '구매 전 확인', sub: '수량 · 희망 수령일', emoji: '🛒' }, { v: 'existing', label: '기존 주문 문의', sub: 'PO 번호로 문의', emoji: '📑' }], src: { doc: 'POL-ORDER', sec: '1' } },
      ...(pre ? [
        { id: 'o_qty', type: 'number', title: '몇 개가 필요하세요?', min: 1, src: { doc: 'POL-ORDER', sec: '1' } },
        { id: 'o_date', type: 'date', title: '언제까지 받고 싶으세요?', sub: '희망 수령일이에요.', unknown: true, min: 'today', src: { doc: 'POL-ORDER', sec: '1' } },
      ] : []),
      ...(a.o_when === 'existing' ? [
        { id: 'o_po', type: 'text', title: '주문번호 또는 PO 번호를 알려 주세요', unknown: true, placeholder: '예: PO-12345', src: { doc: 'POL-ORDER', sec: '2' } },
        { id: 'o_topic', type: 'choice', title: '무엇이 궁금하세요?', options: opts('o_topic'), src: { doc: 'POL-ORDER', sec: '3' } },
        { id: 'o_note', type: 'text', title: '추가로 알려 주실 내용이 있나요?', optional: true, long: true, placeholder: '예: 희망 출하일, 나누어 받고 싶은 수량', src: { doc: 'POL-ORDER', sec: '3' } },
      ] : []),
    ]
  }
  // 견적
  return [
    { id: 'q_qty', type: 'number', title: '몇 개의 견적이 필요하세요?', min: 1, src: { doc: 'POL-ORDER', sec: '5' } },
    { id: 'q_inco', type: 'choice', title: '어떤 인도 조건으로 받고 싶으세요?', sub: '표준 조건은 FOB Busan 또는 EXW Factory예요.', options: opts('q_inco'), src: { doc: 'POL-ORDER', sec: '4' } },
    { id: 'q_dest', type: 'text', title: '납품 국가나 지역은 어디인가요?', sub: '지역에 공인 대리점이 있으면 최종 사용자 요청이 대리점으로 전달될 수 있어요.', placeholder: '예: 대한민국, 베트남 하노이', src: { doc: 'POL-ORDER', sec: '5' } },
    { id: 'q_date', type: 'date', title: '희망 납기일이 있나요?', unknown: true, min: 'today', src: { doc: 'POL-ORDER', sec: '1' } },
    { id: 'q_custom', type: 'choice', title: '표준 사양 그대로 괜찮으세요?', options: opts('q_custom'), src: { doc: 'POL-ORDER', sec: '5' } },
    { id: 'q_note', type: 'text', title: '추가 요구사항이 있나요?', optional: true, long: true, placeholder: '예: 인증서 필요, 분할 납품', src: { doc: 'POL-ORDER', sec: '5' } },
  ]
}

export const catOf = (task, a) => (task === 'warranty' ? (a.w_goal === 'return' ? 'RETURN' : 'WARRANTY') : task === 'order' ? 'ORDER_LEAD' : 'QUOTE')

// 답변을 사람이 읽는 문장으로
export function answerText(q, a) {
  const v = a[q.id]
  if (v === undefined || v === '') return null
  if (v === UNKNOWN) return '잘 모르겠어요'
  if (v === NOTYET) return '아직 시운전 전이에요'
  if (q.type === 'multi') return v.length === 0 ? '해당하는 게 없어요' : v.map((x) => q.options.find((o) => o.v === x)?.label).join(', ')
  if (q.type === 'choice') return q.options.find((o) => o.v === v)?.label ?? v
  if (q.id === 'o_qty' || q.id === 'q_qty') return `${v}개`
  return String(v)
}

// ---------- 결과 ----------
export function resultFor(task, a, ctx) {
  const { master: m, family } = ctx
  const cat = catOf(task, a)
  const route = routingOf(family, cat)
  const r = { cat, conds: [], todo: [], next: [], route, srcs: [], cta: null, notice: null }
  const cond = (t, src) => r.conds.push({ t, src })
  const todo = (t, src) => r.todo.push({ t, src })

  if (task === 'warranty' && a.w_goal !== 'return') {
    const months = Number(m.warranty_months)
    cond(`이 모델의 보증 기간은 ${months}개월이에요.`, { doc: 'POL-WARRANTY', sec: '1', mark: ctx.code })
    cond('보증은 시운전일부터 시작하고, 늦어도 출하 6개월 뒤에는 시작돼요.', { doc: 'POL-WARRANTY', sec: '1' })
    const ship = parseDate(a.w_ship), comm = parseDate(a.w_comm)
    let start = null, upper = false
    if (ship) {
      const cap = addMonths(ship, 6)
      if (comm) start = comm > cap ? cap : comm
      else { start = cap; upper = true }
    } else if (comm) start = comm
    if (start) {
      const end = addMonths(start, months)
      const inside = today() <= end
      cond(`${upper ? '시작일을 늦게 잡아도' : '시작일을 ' + ymd(start) + '로 보면'} 보증 종료는 ${ymd(end)}${upper ? ' 이전이에요.' : '이에요.'} 계산상 ${inside ? '아직 기간 안' : '기간이 지난 것'}으로 보여요(참고용).`, { doc: 'POL-WARRANTY', sec: '1' })
    }
    if (!ship) todo('출하일을 알 수 없어요. 구매 서류나 출하 기록으로 확인이 필요해요.', { doc: 'POL-WARRANTY', sec: '1' })
    if (!comm) todo(a.w_comm === NOTYET ? '아직 시운전 전이면 보증 시작일이 정해지지 않았어요. 담당자가 시작일을 안내해요.' : '시운전일을 알 수 없어요. 확인이 필요해요.', { doc: 'POL-WARRANTY', sec: '1' })
    const ex = a.w_excl ?? []
    const EXT = { spec: '정격 밖 사용', damage: '침수·충격·임의 개조', wear: '12개월이 지난 소모품' }
    ex.forEach((k) => todo(`"${EXT[k]}"은 정책상 보증 제외 항목이에요. 해당 여부는 담당자가 확인해요.`, { doc: 'POL-WARRANTY', sec: '3' }))
    if (a.w_excl && ex.length === 0) cond('정책상 제외 항목(정격 밖 사용, 침수·충격·임의 개조, 12개월 지난 소모품)에 해당하지 않는다고 답했어요.', { doc: 'POL-WARRANTY', sec: '3' })
    if (a.w_partner === 'yes') cond('인증 파트너가 설치한 제품은 현장 작업 비용도 보증 범위에 들어가요.', { doc: 'POL-WARRANTY', sec: '2' })
    else todo('현장 작업 비용 보증은 인증 파트너가 설치한 제품에만 해당해요. 설치 업체 확인이 필요해요.', { doc: 'POL-WARRANTY', sec: '2' })
    todo('보증 범위는 재료·제작 결함의 수리 또는 교체예요. 실제 결함 여부는 접수 후 보증·RMA 데스크가 판단하고, 필요하면 품질보증 팀이 원인을 분석해요.', { doc: 'POL-WARRANTY', sec: '4' })
    r.headline = '보증 기간 계산은 참고용이에요'
    r.next.push('시리얼 번호, 구매 서류(PO·송장), 설치일, 증상 설명, 사진을 준비해 주세요.')
    r.next.push('접수하면 보증·RMA 데스크가 심사하고, 승인되면 RMA 번호가 발급돼요.')
    r.cta = { label: '보증 문의하기', kind: 'warranty' }
    r.srcs = [{ doc: 'POL-WARRANTY', sec: '4' }]
    return r
  }

  if (task === 'warranty') {
    const reason = a.r_reason, R = REASONS[reason]
    const del = parseDate(a.r_deliv)
    const el = del ? days(del, today()) : null
    const used = a.r_used && a.r_used !== 'no' && a.r_used !== UNKNOWN
    r.headline = '정책 조건을 확인했어요 (최종 판단은 담당자가 해요)'
    const nonDefect = reason === 'wrong' || reason === 'excess'
    r.route = nonDefect ? { ...biz.routing.RETURN_NON_DEFECT, source: 'SUBTYPE_OVERRIDE' } : route
    if (reason === 'used') {
      cond('설치하거나 사용한 제품은 반품·교환을 받지 않아요. 대신 보증 청구로 진행해요.', { doc: 'POL-RETURN', sec: '1', mark: 'Used or installed units' })
      r.next.push('결함이 있다면 [보증 확인]으로 보증 조건을 확인해 보세요.')
      r.cta = { label: '교환·반품 문의', kind: 'return' }
    } else if (reason === 'other') {
      todo('알려 주신 사유가 정책의 사례에 바로 맞지 않아요. 담당자가 사유를 확인해요.', { doc: 'POL-RETURN', sec: '1' })
      r.cta = { label: '교환·반품 문의', kind: 'return' }
    } else {
      cond(`${R.sub}: ${{ doa: '배송 후 14일 안에 알리면 무상 교체', wrong: '당사 오류이고 14일 안에 알리면 무상 교환(수거는 당사가 진행)', damaged: '7일 안에 포장 사진과 함께 알리면 교체(운송사 클레임은 당사가 처리)', excess: '미사용·원 포장·30일 안이면 재입고 수수료 15%를 뺀 크레딧 노트' }[reason]}`, { doc: 'POL-RETURN', sec: '1', mark: R.row })
      if (el === null) todo('받은 날을 몰라서 기한(' + R.limit + '일)을 확인하지 못했어요.', { doc: 'POL-RETURN', sec: '1', mark: R.row })
      else if (el <= R.limit) cond(`받은 지 ${el}일이라 ${R.limit}일 기한 안이에요.`, { doc: 'POL-RETURN', sec: '1', mark: R.row })
      else { todo(`받은 지 ${el}일이라 ${R.limit}일 기한을 넘었어요. 정책상 받지 않을 수 있어요.`, { doc: 'POL-RETURN', sec: '1', mark: R.row }) }
      if (el !== null && el > 30) todo('30일이 지나면 정책상 반품을 받지 않아요.', { doc: 'POL-RETURN', sec: '1', mark: 'After 30 days' })
      if (used) todo('설치하거나 써 본 제품은 정책상 받지 않아요. 보증 청구로 안내될 수 있어요.', { doc: 'POL-RETURN', sec: '1', mark: 'Used or installed units' })
      else if (a.r_used === UNKNOWN) todo('설치·사용 여부를 확인해야 해요.', { doc: 'POL-RETURN', sec: '1', mark: 'Used or installed units' })
      if (reason === 'excess') { if (a.r_pack === 'orig') cond('원래 포장 그대로라서 조건에 맞아요.', { doc: 'POL-RETURN', sec: '1', mark: reason && R.row }); else todo('원래 포장이어야 해요. 포장 상태를 확인해야 해요.', { doc: 'POL-RETURN', sec: '1', mark: R.row }) }
      if (reason === 'damaged') { if (a.r_photo === 'yes') cond('포장 파손 사진이 있어요.', { doc: 'POL-RETURN', sec: '1', mark: R.row }); else todo('포장이 파손된 사진이 필요해요.', { doc: 'POL-RETURN', sec: '1', mark: R.row }) }
      if (reason === 'damaged') todo('배송 파손은 정책에 담당 부서가 따로 정해져 있지 않아요. 담당자가 확인해요.', { doc: 'POL-RETURN', sec: '2' })
      todo(`${reason === 'doa' ? '품질 이슈(초기 불량)는 품질보증 팀이 검토해요.' : '비불량 반품은 주문·물류 팀이 처리해요.'} 최종 결정과 RMA 발급은 담당자가 해요.`, { doc: 'POL-RETURN', sec: '2' })
      r.cta = { label: '교환·반품 문의', kind: 'return' }
    }
    r.next.push('구매 서류(PO·송장), 시리얼 번호, 사유, 사진으로 RMA를 요청해요. RMA 없이 보낸 제품은 받지 않아요.')
    r.srcs = [{ doc: 'POL-RETURN', sec: '2' }]
    return r
  }

  if (task === 'order') {
    const lead = Number(m.std_lead_time_weeks), moq = Number(m.moq)
    cond(`표준 납기는 ${lead}주(공장 출고 기준), 최소 주문 수량은 ${moq}개예요.`, { doc: 'POL-ORDER', sec: '1', mark: ctx.code })
    r.notice = '주문별 출고일이나 배송 상태, 재고는 조회하지 않아요. 아래는 정책 기준 안내예요.'
    if (a.o_when === 'pre') {
      const q = Number(a.o_qty), d = parseDate(a.o_date)
      if (q < moq) todo(`희망 수량(${q}개)이 최소 주문 수량(${moq}개)보다 적어요. 담당자가 확인해요.`, { doc: 'POL-ORDER', sec: '1', mark: ctx.code })
      else cond(`희망 수량 ${q}개는 최소 주문 수량 이상이에요.`, { doc: 'POL-ORDER', sec: '1', mark: ctx.code })
      if (d) {
        const gap = days(today(), d)
        if (gap < lead * 7) todo(`희망일까지 ${gap}일이라 표준 납기(${lead * 7}일)보다 짧아요(오늘 주문한다고 가정한 참고). 단축은 생산 계획 검토 후 가능하며 추가 비용이 생길 수 있어요.`, { doc: 'POL-ORDER', sec: '3' })
        else cond(`희망일까지 ${gap}일이라 표준 납기(${lead * 7}일)보다 길어요(오늘 주문한다고 가정한 참고).`, { doc: 'POL-ORDER', sec: '1', mark: ctx.code })
      } else todo('희망 수령일을 몰라서 표준 납기와 비교하지 못했어요.', { doc: 'POL-ORDER', sec: '1' })
      cond('주문 확정서는 PO를 받고 2영업일 안에 출고 예정일과 함께 보내요.', { doc: 'POL-ORDER', sec: '2' })
      todo('재고와 실제 출고 가능일은 이 화면에서 알 수 없어요. 납기 확인을 요청해 주세요.', { doc: 'POL-ORDER', sec: '1' })
      r.headline = '표준 납기를 알려 드려요'
      r.next.push('[납기 확인 요청]을 보내면 주문·물류 팀이 실제 가능 일정을 알려 줘요.')
      r.cta = { label: '납기 확인 요청', kind: 'order' }
    } else {
      if (a.o_po === UNKNOWN || !a.o_po) todo('주문번호(PO)를 모르면 담당자가 주문을 찾는 데 시간이 걸려요.', { doc: 'POL-ORDER', sec: '2' })
      else cond(`PO ${a.o_po}로 문의해요.`, { doc: 'POL-ORDER', sec: '2' })
      if (a.o_topic === 'expedite') todo('납기 단축은 생산 계획과 검토하며 추가 비용이 생길 수 있어요.', { doc: 'POL-ORDER', sec: '3' })
      if (a.o_topic === 'partial') todo('재고에서 나눠 출하하는 것은 요청하면 가능하지만, 가능 여부는 담당자가 확인해요.', { doc: 'POL-ORDER', sec: '3' })
      r.headline = '담당 부서에 연결할게요'
      r.next.push('문의 내용을 담당 부서에 그대로 전달해요. 실제 출고·배송 상태는 담당자가 확인해서 알려 줘요.')
      r.cta = { label: '담당 부서에 문의하기', kind: 'order' }
    }
    r.srcs = [{ doc: 'POL-ORDER', sec: '1', mark: ctx.code }]
    return r
  }

  // 견적
  cond('견적서는 발행일로부터 30일 동안 유효해요.', { doc: 'POL-ORDER', sec: '5' })
  cond('수량이 많으면 수량 할인이 적용될 수 있어요. 금액은 담당자가 견적서로 알려 드려요.', { doc: 'POL-ORDER', sec: '5' })
  cond('표준 인도 조건은 FOB Busan 또는 EXW Factory예요.', { doc: 'POL-ORDER', sec: '4' })
  if (a.q_inco === 'other') todo('CIF · CFR · DAP는 요청에 따라 별도로 견적해요.', { doc: 'POL-ORDER', sec: '4' })
  if (a.q_inco === UNKNOWN) todo('인도 조건을 모르면 담당자가 함께 정해요.', { doc: 'POL-ORDER', sec: '4' })
  todo('납품 지역에 공인 대리점이 있으면 요청이 대리점으로 전달돼요. 대리점이 있는 지역 목록은 제공 자료에 없어서 담당자가 확인해요.', { doc: 'POL-ORDER', sec: '5' })
  if (a.q_custom === 'special') todo('표준 외 사양은 기술지원 팀이 함께 검토해요.', { doc: 'POL-ORDER', sec: '5' })
  if (a.q_custom === UNKNOWN) todo('표준 사양으로 충분한지 담당자가 확인해요.', { doc: 'POL-ORDER', sec: '5' })
  if (a.q_date === UNKNOWN) todo('희망 납기를 몰라도 접수할 수 있어요. 표준 납기는 ' + m.std_lead_time_weeks + '주예요.', { doc: 'POL-ORDER', sec: '1', mark: ctx.code })
  r.headline = '견적 요청 내용을 확인해 주세요'
  r.next.push('가격은 이 화면에서 계산하지 않아요. 정가나 할인, 배송비는 담당자가 견적서로 안내해요.')
  r.cta = { label: '견적 문의하기', kind: 'quote' }
  r.srcs = [{ doc: 'POL-ORDER', sec: '5' }]
  return r
}

// ---------- 접수 양식 ----------
export function formFields(cat, a, ctx, extra = {}) {
  const pre = {
    product_model: `${ctx.name} (${ctx.code})`,
    install_date: a.w_comm && a.w_comm !== UNKNOWN && a.w_comm !== NOTYET ? a.w_comm : a.w_comm === NOTYET ? '아직 시운전 전' : '',
    return_reason: a.r_reason ? REASONS[a.r_reason].sub : '',
    packaging_condition: a.r_pack ? LABEL.r_pack[a.r_pack] : a.r_photo ? `포장 파손 사진: ${LABEL.r_photo[a.r_photo]}` : '',
    po_number: a.o_po && a.o_po !== UNKNOWN ? a.o_po : '',
    quantity: a.o_qty ?? a.q_qty ?? '',
    required_date: a.o_date && a.o_date !== UNKNOWN ? a.o_date : a.q_date && a.q_date !== UNKNOWN ? a.q_date : '',
    incoterms: a.q_inco ? `${LABEL.q_inco[a.q_inco]}${a.q_dest ? ` · ${a.q_dest}` : ''}` : '',
    failure_description: '',
  }
  return requiredOf(ctx.family, cat).map((f) => ({ ...f, value: extra[f.key] ?? pre[f.key] ?? '' }))
}

export function summaryLines(task, a, ctx, fields) {
  const lines = [`제품: ${ctx.familyName} / ${ctx.name} (${ctx.code})`]
  lines.push(`업무: ${{ warranty: a.w_goal === 'return' ? '교환·반품' : '보증 확인', order: '주문·납기', quote: '견적 요청' }[task]}`)
  fields.forEach((f) => lines.push(`${f.label}: ${f.value || '(미입력)'}${f.blocking && !f.value ? ' ← 필수' : ''}`))
  return lines
}
