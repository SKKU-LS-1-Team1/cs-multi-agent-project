// 단종·호환·대체: 쓰던 제품의 정격과 현재 판매 중인 모델의 스펙을 비교해 대체 모델을 추천한다.
// 단종품은 카탈로그에 없어서 고객이 정격을 직접 알려 준다(비워도 된다). 비교 기준은 제품 사양(info.json)의 문자열에서 뽑는다.
// 이 판단은 안내용이다. 확정은 담당 기술지원이 한다. 모르는 것을 맞다고 하지 않도록 "확인 필요"와 "정보 없음"을 숨기지 않는다.
import { getFamily } from './catalog.js'
import { LEGACY_TYPE } from './legacy.js'

let cache
export const loadInfo = () => (cache ??= import('../data/info.json').then((m) => m.default))

export const STATUS = { same: '일치', ok: '충족', near: '확인 필요', low: '맞지 않음', unknown: '정보 없음' }
const SCORE = { same: 3, ok: 2, near: 1, unknown: 0.5, low: 0 }
export const LIFECYCLE = { ACTIVE: '판매 중', MATURE: '판매 중 · 성숙 단계' }

// "1,300 W" → 1300, "15, 20, 30 A" → [15, 20, 30]
const numbers = (text) => [...String(text ?? '').replace(/(\d),(\d{3})(?!\d)/g, '$1$2').matchAll(/\d+(?:\.\d+)?/g)].map((m) => Number(m[0]))
const attr = (re) => (p) => p.specs.find((s) => re.test(s.attr))?.value
const near = (a, b) => Math.abs(a - b) <= Math.max(1e-9, Math.abs(b) * 0.001)

// 제품군별 비교 기준. mode — list: 정해진 정격 중 하나(차단기 정격전류) · cover: 후보가 같거나 커야 한다 · same: 같아야 한다
//   near: 비슷하면 된다(임피던스) · has: 후보가 지원하는 항목에 들어 있어야 한다 · text: 글자가 같아야 한다
export const CRITERIA = {
  LV_BREAKER: [
    { key: 'current', label: '정격전류', unit: 'A', kind: 'number', mode: 'list', read: attr(/^Rated current \(In\)/i), placeholder: '예: 100' },
    { key: 'icu', label: '차단용량 (415V)', unit: 'kA', kind: 'number', mode: 'cover', read: attr(/^Ultimate breaking capacity Icu/i), placeholder: '예: 35' },
    { key: 'poles', label: '극수', kind: 'select', options: ['2P', '3P', '4P'], mode: 'has', read: attr(/^Number of poles/i) },
  ],
  MV_EQUIP: [
    { key: 'voltage', label: '정격전압', unit: 'kV', kind: 'number', mode: 'cover', read: attr(/^Rated voltage$/i), placeholder: '예: 24' },
    { key: 'current', label: '정격전류', unit: 'A', kind: 'number', mode: 'cover', read: attr(/^Rated (normal|busbar) current/i), placeholder: '예: 1250' },
    { key: 'shortTime', label: '단시간 내전류', unit: 'kA', kind: 'number', mode: 'cover', read: attr(/^Rated short-time withstand/i), placeholder: '예: 25' },
  ],
  TRANSFORMER: [
    { key: 'kva', label: '용량', unit: 'kVA', kind: 'number', mode: 'cover', read: attr(/^Rated power/i), placeholder: '예: 630' },
    { key: 'primary', label: '1차 전압', unit: 'kV', kind: 'number', mode: 'same', read: attr(/^Voltage ratio/i), pick: (raw) => numbers(raw).slice(0, 1), placeholder: '예: 11' },
    { key: 'secondary', label: '2차 전압', unit: 'V', kind: 'number', mode: 'same', read: attr(/^Voltage ratio/i), pick: (raw) => numbers(raw).slice(1, 2).map((kv) => Number((kv * 1000).toFixed(3))), placeholder: '예: 415' },
    { key: 'type', label: '방식', kind: 'select', options: ['건식', '유입'], mode: 'text', read: (p) => (/dry/i.test(p.master.product_name) ? '건식' : /oil/i.test(p.master.product_name) ? '유입' : '') },
    { key: 'vector', label: '결선', kind: 'text', mode: 'text', read: attr(/^Vector group/i), placeholder: '예: Dyn11' },
    { key: 'impedance', label: '임피던스', unit: '%', kind: 'number', mode: 'near', read: attr(/^Impedance voltage/i), placeholder: '예: 6' },
  ],
}
export const hasCriteria = (family) => Object.hasOwn(CRITERIA, family)
// 단종·호환·대체 문의는 먼저 비교·추천 화면을 거친다. 추천 화면에서 "추천 없이 문의"로 온 초안(direct)은 문의서로 바로 간다.
export const needsReplace = (draft) => draft?.type === LEGACY_TYPE && !draft.direct && hasCriteria(draft.family)

const show = (c, v) => (c.kind === 'number' ? `${v} ${c.unit}` : String(v))
const shorten = (s, n = 64) => (s.length > n ? `${s.slice(0, n - 1)}…` : s)

// 고객이 입력한 값 중 쓸 수 있는 것만 { c, mine }으로 모은다. 쓸 수 없는 값(0 이하·숫자가 아님·목록에 없음)은 invalid로 알려 준다.
export function parseEntered(family, values = {}) {
  const entered = [], invalid = []
  for (const c of CRITERIA[family] ?? []) {
    const raw = String(values[c.key] ?? '').trim()
    if (!raw) continue
    if (c.kind === 'number') { const n = Number(raw); (Number.isFinite(n) && n > 0 ? entered.push({ c, mine: n }) : invalid.push(c.key)) }
    else if (c.kind === 'select') (c.options.includes(raw) ? entered.push({ c, mine: raw }) : invalid.push(c.key))
    else (raw.length <= 20 ? entered.push({ c, mine: raw }) : invalid.push(c.key))
  }
  return { entered, invalid }
}

// 한 기준을 한 모델과 비교한다. p = info.json의 모델 항목({ master, specs })
function judge(c, mine, p) {
  const raw = c.read(p)
  const missing = { status: 'unknown', theirs: '—', note: '사양에 정보가 없어요' }
  if (raw == null || raw === '') return missing
  let theirs = shorten(raw)
  if (c.kind === 'number') {
    const v = (c.pick ?? numbers)(raw)
    if (!v.length) return missing
    if (c.pick) theirs = show(c, v[0]) // 한 문장에서 일부만 뽑은 기준(전압비의 1차·2차)은 그 값만 보여 준다
    const base = v[0], max = Math.max(...v), min = Math.min(...v)
    if (c.mode === 'list') {
      if (v.some((x) => near(x, mine))) return { status: 'same', theirs }
      if (mine > min && mine < max) return { status: 'near', theirs, note: '정격 범위 안이라 설정값을 확인해야 해요' }
      return { status: 'low', theirs, note: mine > max ? '정격이 부족해요' : '정격이 너무 커요' }
    }
    if (c.mode === 'cover') {
      if (near(base, mine)) return { status: 'same', theirs }
      if (base > mine) return { status: 'ok', theirs, note: '같거나 더 큰 사양이에요' }
      if (max >= mine) return { status: 'near', theirs, note: '기본 사양은 부족하고, 옵션(강제 냉각·확장)이면 가능해요' }
      return { status: 'low', theirs, note: '사양이 부족해요' }
    }
    if (c.mode === 'same') return near(base, mine) ? { status: 'same', theirs } : { status: 'low', theirs, note: '값이 달라요' }
    if (c.mode === 'near') {
      const d = Math.abs(base - mine)
      return d <= 0.5 ? { status: 'same', theirs } : d <= 1.5 ? { status: 'near', theirs, note: '조금 달라요. 계통 협조 확인이 필요해요' } : { status: 'low', theirs, note: '차이가 커요' }
    }
  }
  const norm = (s) => String(s).replace(/\s+/g, '').toLowerCase()
  if (c.mode === 'has') return norm(raw).includes(norm(mine)) ? { status: 'same', theirs } : { status: 'low', theirs, note: '지원하지 않아요' }
  return norm(raw) === norm(mine) ? { status: 'same', theirs } : { status: 'low', theirs, note: '달라요' }
}

// 비교·추천. rows는 "조건에 맞는 모델이 먼저, 맞는 정도가 높은 순"이다. 입력이 하나도 없으면 비교하지 않는다(rows가 비어 있다).
export function compare(family, values, info, { exclude } = {}) {
  const { entered, invalid } = parseEntered(family, values)
  const empty = { entered, invalid, rows: [], fits: [], misfits: [] }
  if (!entered.length || !info) return empty
  const rows = getFamily(family).models.filter((code) => code !== exclude && info[code]).map((code) => {
    const p = info[code]
    const checks = entered.map(({ c, mine }) => ({ key: c.key, label: c.label, mine: show(c, mine), ...judge(c, mine, p) }))
    const counts = Object.fromEntries(Object.keys(STATUS).map((k) => [k, checks.filter((x) => x.status === k).length]))
    return { code, name: p.master.product_name, master: p.master, checks, counts, fit: counts.low === 0, score: checks.reduce((a, x) => a + SCORE[x.status], 0) }
  })
  rows.sort((a, b) => (Number(b.fit) - Number(a.fit)) || (b.score - a.score) || (Number(a.master.std_lead_time_weeks) - Number(b.master.std_lead_time_weeks)) || a.code.localeCompare(b.code))
  return { entered, invalid, rows, fits: rows.filter((r) => r.fit), misfits: rows.filter((r) => !r.fit) }
}

// 카탈로그의 모델로 입력 칸을 채운다("이 모델과 비슷해요"). 정해진 정격 목록은 가장 큰 값을, 나머지는 기본 사양을 쓴다.
export function fromProduct(family, code, info) {
  const p = info?.[code]
  const out = {}
  if (!p) return out
  for (const c of CRITERIA[family] ?? []) {
    const raw = c.read(p)
    if (raw == null || raw === '') continue
    if (c.kind === 'number') {
      const v = (c.pick ?? numbers)(raw)
      if (v.length) out[c.key] = String(c.mode === 'list' ? Math.max(...v) : v[0])
    } else if (c.kind === 'select') {
      const hit = c.options.filter((o) => raw.replace(/\s+/g, '').toLowerCase().includes(o.toLowerCase()))
      if (hit.length) out[c.key] = hit.includes('3P') ? '3P' : hit[0]
    } else out[c.key] = String(raw).slice(0, 20)
  }
  return out
}

// 선택한 대체 모델로 견적 문의서를 열 초안. 비교 결과를 본문에 남겨 담당자가 같은 내용을 보게 한다.
export function quoteDraft({ family, row, entered }) {
  const lines = [
    '[대체 모델 견적 문의] 단종 · 호환 비교에서 고른 모델이에요.',
    `기존 제품 정격: ${entered.map(({ c, mine }) => `${c.label} ${show(c, mine)}`).join(', ')}`,
    `선택한 모델: ${row.name} (${row.code})`,
    '비교 결과:',
    ...row.checks.map((x) => `- ${x.label}: ${STATUS[x.status]} (기존 ${x.mine} / 이 모델 ${x.theirs})${x.note ? ` — ${x.note}` : ''}`),
  ]
  if (row.counts.low) lines.push('맞지 않는 항목이 있지만 이 모델로 견적을 받고 싶어요. 대체 가능한지 담당 기술지원이 확인해 주세요.')
  if (row.counts.near || row.counts.unknown) lines.push('확인 필요·정보 없음 항목은 담당 기술지원이 확인해 주세요.')
  return { type: 'QUOTE', family, model: row.code, vals: {}, subject: `${row.name} 교체 견적 문의`.slice(0, 100), body: lines.join('\n') }
}
