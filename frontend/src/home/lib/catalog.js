// 제공 자료(scripts/build_data.py 가 생성한 catalog.json)를 화면에서 쓰기 좋게 꺼내는 함수들.
import catalog from '../data/catalog.json'

const images = import.meta.glob('../assets/products/*.webp', { eager: true, import: 'default' })
export const familyImage = (id) => images[`../assets/products/${id}.webp`]

export const families = catalog.families
export const getFamily = (id) => families.find((f) => f.id === id)
export const products = catalog.products
export const getProduct = (code) => catalog.products[code]

// 제품 목록(대분류 3 · 제품군 11 · 모델 23). 대분류는 data/ref/family_divisions.csv 와 같은 순서·이름.
const DIVISIONS = [
  ['POWER', '전력', ['LV_BREAKER', 'MV_EQUIP', 'TRANSFORMER', 'METER']],
  ['AUTOMATION', '자동화', ['CONTROL', 'DRIVE', 'PLC', 'HMI']],
  ['ENERGY', '에너지', ['ESS', 'PV', 'UPS']],
]
const listed = new Set(DIVISIONS.flatMap(([, , ids]) => ids))
export const divisions = [
  ...DIVISIONS.map(([id, label, ids]) => ({ id, label, families: ids.map(getFamily).filter(Boolean) })),
  // 표에 없는 제품군이 생기면 빠뜨리지 않고 맨 아래에 둔다
  { id: 'OTHER', label: '기타', families: families.filter((f) => !listed.has(f.id)) },
].filter((d) => d.families.length)
export const NONE = '__none'

// 모델명을 모르는 경우: 제품군에 속한 모델의 증상을 모두 모아 보여 준다.
export function issuePool(familyId, modelCode) {
  const codes = modelCode ? [modelCode] : getFamily(familyId).models
  return codes.flatMap((c) =>
    getProduct(c).issues.map((it, i) => ({ ...it, id: `${c}#${i}`, model: c })),
  )
}

export function groupByCode(pool) {
  const groups = new Map()
  for (const it of pool) {
    const k = it.code ?? NONE
    if (!groups.has(k)) groups.set(k, [])
    groups.get(k).push(it)
  }
  return groups
}

export function summarize({ family, model, issue, tried }) {
  const fam = family ? getFamily(family).name : null
  const prod = model ? getProduct(model) : null
  const lines = []
  if (fam) lines.push(`제품군: ${fam}`)
  lines.push(`모델: ${prod ? `${prod.name} (${prod.code})` : '모델을 잘 모르겠어요'}`)
  if (issue) lines.push(`증상: ${issue.code ? `${issue.code} · ` : ''}${issue.symptom}`)
  for (const t of tried) lines.push(`해 본 조치: ${t.action} (확인: ${t.check})`)
  return lines
}
