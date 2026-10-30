// 설치·사용 안내를 모델의 실제 문서(docs.json)에서 STEP 으로 만든다. 문서에 없는 절차는 만들지 않는다.
export const DOC_LABEL = {
  IG: '설치 가이드', DS: '데이터시트', MG: '유지보수', RN: '릴리스 노트', TG: '문제 해결',
  'POL-WARRANTY': '보증 정책', 'POL-RETURN': '교환·반품 정책', 'POL-ORDER': '주문·납기 정책', 'POL-SERVICE': '서비스 수준',
}
export const DOC_ORDER = ['IG', 'DS', 'MG', 'RN', 'TG']

const sentences = (t) => t.split(/(?<=\.)\s+(?=[A-Z(])/).map((x) => x.trim()).filter(Boolean)

const sec = (doc, num) => doc?.sections.find((s) => s.num === num && (s.blocks.length || s.title))
const itemsOf = (s) =>
  (s?.blocks ?? []).flatMap((b) => (b.t === 'p' ? sentences(b.text) : b.items ?? []))

const src = (doc, num) => ({ doc: doc.id.split('-')[0], sec: num, ref: `${doc.id.split('-')[0]} §${num}`, title: sec(doc, num)?.title ?? '' })

// ── 설치·사용 안내를 사용자용 단계로 만든다.
// 원문의 순서와 값은 그대로 두고, 한국어 제목·짧은 설명만 붙인다. 원문에 없는 절차·수치는 만들지 않는다.
// 문장은 "자료에 있는 정해진 문장"과 일치할 때만 한국어로 옮기고, 아니면 원문을 그대로 보여 준다.
const CHECK_KO = {
  'Product rating matches the drawing': '제품 정격이 도면과 일치해요',
  'All terminals tightened to specified torque': '모든 단자를 지정한 토크로 조였어요',
  'Protective earth connected': '보호 접지를 연결했어요',
  'Insulation resistance measured and recorded': '절연 저항을 측정하고 기록했어요',
  'Settings / parameters recorded': '설정·파라미터를 기록했어요',
}
const cleanCheck = (t) => t.replace(/^\[[ xX]?\]\s*/, '').trim()
const checklistOf = (s) => itemsOf(s).map(cleanCheck).map((t) => CHECK_KO[t] ?? t)

function safetyStep(IG) {
  const raw = itemsOf(sec(IG, '1'))
  const std = /qualified personnel/i.test(raw[0] ?? '') && /lock out/i.test(raw[1] ?? '') && /absence of voltage/i.test(raw[2] ?? '')
  return {
    id: 'safety', group: '준비하기', title: '안전부터 확인해요',
    lead: std ? '작업 전에 먼저 전원을 안전하게 막아 두세요.' : null,
    checks: std ? ['모든 전원을 차단하고 잠가요', '전압이 없는지 확인해요'] : [],
    cautions: std ? ['설치·배선·시운전은 자격을 갖춘 담당자가 해야 해요.'] : raw,
    raw: std ? raw : [], src: [src(IG, '1')],
  }
}

function receiveStep(IG) {
  const raw = itemsOf(sec(IG, '2'))
  const m = raw.join(' ').match(/within (\d+) days \(see ([A-Z-]+)\)\. Store indoors in a dry place between (-?\d+) and \+?(\d+) °C, relative humidity below (\d+)%/)
  return {
    id: 'receive', group: '준비하기', title: '받은 제품을 확인하고 보관해요',
    lead: m ? '도착하면 포장부터 살펴보고, 설치 전까지는 아래 조건으로 보관해요.' : null,
    checks: m ? [`포장이 파손됐다면 ${m[1]}일 이내에 알려요 (${m[2]} 참고)`, `실내 건조한 곳, ${m[3]} ~ +${m[4]} °C`, `상대습도 ${m[5]}% 미만, 결로 없이`] : [],
    cautions: [], bullets: m ? [] : raw, raw: m ? raw : [], src: [src(IG, '2')],
  }
}

function mountStep(IG) {
  const raw = itemsOf(sec(IG, '3'))
  const bullets = raw.map((t) => {
    let m
    if ((m = t.match(/^Required clearances:\s*(.*)$/))) return `필요한 간격: ${m[1]}`
    if ((m = t.match(/^Operating temperature:\s*(.*)$/))) return `사용 온도: ${m[1]}`
    if ((m = t.match(/^Degree of protection:\s*(.*)$/))) return `보호 등급: ${m[1]}`
    if ((m = t.match(/^Above ([\d,]+) m altitude, apply derating per the datasheet\.?$/))) return `고도 ${m[1]} m 이상에서는 데이터시트에 따라 용량을 낮춰 써요 (디레이팅)`
    return t
  })
  return { id: 'mount', group: '설치하기', title: '설치할 자리를 정해요', lead: '필요한 간격과 사용 환경을 확인하고 자리를 잡아요.', bullets, raw, src: [src(IG, '3')] }
}

function wireStep(IG) {
  const raw = itemsOf(sec(IG, '4'))
  const bullets = [], notes = []
  for (const t of raw) {
    let m
    if ((m = t.match(/^Terminal tightening torque:\s*(.*)$/))) {
      if (/\d/.test(m[1])) bullets.push(`단자 조임 토크: ${m[1]}`)
      else notes.push(`조임 토크 수치가 자료에 없어요 (원문: "${m[1]}"). 치수 도면을 확인해 주세요.`)
    } else if ((m = t.match(/^Use copper conductors rated for at least (\d+) °C\.?$/))) bullets.push(`${m[1]} °C 이상 등급의 구리 도체를 써요`)
    else if ((m = t.match(/^Separate power and signal cables by at least (\d+) mm\.?$/))) bullets.push(`전력선과 신호선은 ${m[1]} mm 이상 떨어뜨려요`)
    else bullets.push(t)
  }
  return { id: 'wire', group: '설치하기', title: '배선하고 조여요', lead: '자료에 적힌 배선 조건대로 연결해요.', bullets, notes, raw, src: [src(IG, '4')] }
}

const commissionStep = (IG) => ({ id: 'commission', group: '설치 후 확인하기', title: '시운전해요', lead: '아래 순서대로 하나씩 진행해요. 문장은 원문 그대로예요.', ordered: itemsOf(sec(IG, '5')), src: [src(IG, '5')] })
const preStep = (IG) => ({ id: 'check', group: '설치 후 확인하기', title: '전원을 넣기 전에 점검해요', lead: '모두 확인한 뒤에 전원을 넣어요.', checklist: checklistOf(sec(IG, '6')), src: [src(IG, '6')] })
function issuesStep(IG) {
  const s = sec(IG, '7')
  const table = s?.blocks.find((b) => b.t === 'table')
  const tail = s?.blocks.find((b) => b.t === 'p')?.text
  return { id: 'issues', title: '막히면 이렇게 확인해요', lead: '설치 중 자주 생기는 문제예요. 오른쪽의 "See" 문서에 자세한 방법이 있어요.', table, raw: tail ? [tail] : [], src: [src(IG, '7')] }
}

export function buildGuide(purpose, docs) {
  const { IG, DS, MG, RN } = docs
  if (!IG) return { steps: [], notice: null }
  if (purpose === 'install') {
    return { steps: [safetyStep(IG), receiveStep(IG), mountStep(IG), wireStep(IG), commissionStep(IG), preStep(IG), issuesStep(IG)], notice: null }
  }
  // 사용 방법: 제공 자료에 일반 조작 설명서는 없다. 문서에서 확인되는 사용 관련 내용만 모은다.
  const steps = []
  const ratings = sec(DS, '2.1')
  if (ratings) {
    const rows = ratings.blocks.find((b) => b.t === 'table')?.rows ?? []
    const env = (sec(DS, '3.1')?.blocks ?? []).flatMap((b) => b.items ?? []).filter((t) => /operating temperature|degree of protection/i.test(t))
    steps.push({ id: 'limits', title: '사용 범위를 확인해요', lead: '자료에 적힌 정격과 사용 환경이에요.', kv: rows.map((r) => [r[0], r[1]]), bullets: env, src: [src(DS, '2.1'), ...(env.length ? [src(DS, '3.1')] : [])] })
  }
  steps.push({ id: 'first', title: '처음 켜고 설정해요', lead: '아래 순서대로 하나씩 진행해요. 문장은 원문 그대로예요.', ordered: itemsOf(sec(IG, '5')), src: [src(IG, '5')] })
  steps.push({ id: 'precheck', title: '켜기 전에 확인해요', lead: '모두 확인한 뒤에 전원을 넣어요.', checklist: checklistOf(sec(IG, '6')), src: [src(IG, '6')] })
  // 펌웨어 업데이트 순서는 보여 주지 않는다. 현장 조건(24시간 가동, 정지 불가)에 따라 방법이 달라서 기술팀이 안내한다.
  if (RN) steps.push({ id: 'fw', title: '펌웨어 업데이트는 기술팀과 진행해요', lead: '최신 버전이 나와 있어도, 전원을 끊을 수 없거나 24시간 돌아가야 하는 설비라면 바로 올리지 못할 수 있어요. 현장 조건에 맞는 방법은 기술팀이 안내해요.', summary: itemsOf(sec(RN, '1')), src: [src(RN, '1')] })
  if (MG) {
    const t = sec(MG, '1')?.blocks.find((b) => b.t === 'table')
    steps.push({ id: 'maint', title: '점검 주기를 확인해요', lead: '사용법이 아니라 유지보수 자료에 적힌 주기예요.', kv: t?.rows.map((r) => [r[0], r[1]]), src: [src(MG, '1')] })
  }
  return { steps, notice: '이 모델은 현재 확인 가능한 사용 정보만 안내해요.', noticeDoc: src(DS ?? IG, DS ? '1' : '1') }
}

// 목적 선택 카드의 설명 — 실제로 안내할 수 있는 내용만 쓴다.
export function purposeDesc(purpose, docs) {
  if (purpose === 'install') return '안전 확인부터 시운전, 전원 넣기 전 점검까지 알아보세요.'
  const parts = ['사용 범위', '처음 켜는 방법', '켜기 전 확인']
  if (docs.RN) parts.push('펌웨어 업데이트 문의처')
  if (docs.MG) parts.push('점검 주기')
  return `제품 사용에 필요한 내용을 확인해보세요. (${parts.join(' · ')})`
}
