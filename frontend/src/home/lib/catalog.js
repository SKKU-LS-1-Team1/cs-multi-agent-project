// 제공 자료(scripts/build_data.py 가 생성한 catalog.json)를 화면에서 쓰기 좋게 꺼내는 함수들.
import catalog from '../data/catalog.json'
import issuesKo from '../data/issues_ko.json'

const images = import.meta.glob('../assets/products/*.webp', { eager: true, import: 'default' })
export const familyImage = (id) => images[`../assets/products/${id}.webp`]
// 모델 전용 사진(assets/models/<모델코드>.webp)이 있으면 그 사진, 없으면 제품군 사진.
const modelImages = import.meta.glob('../assets/models/*.webp', { eager: true, import: 'default' })
export const productImage = (code) => modelImages[`../assets/models/${code}.webp`] ?? familyImage(catalog.products[code]?.family)

// 고장 증상·원인·확인·조치 문구는 원본 자료(TG 문서)가 영어라 catalog.json 에도 영어로 들어 있다.
// 고객 화면은 한국어 원문 기준(다른 언어는 lib/autoTranslate.js 가 한국어에서 번역)이라 한국어로 바꿔 보여 준다.
// 원문은 *_en 에 남긴다. 번역이 없는 문구는 영어 그대로 둔다 (data/issues_ko.json 에 추가하면 된다).
const ISSUE_TEXT = ['symptom', 'cause', 'check', 'action', 'note']
for (const p of Object.values(catalog.products)) {
  for (const it of p.issues ?? []) {
    for (const k of ISSUE_TEXT) {
      const ko = it[k] && issuesKo[it[k]]
      if (ko) { it[`${k}_en`] = it[k]; it[k] = ko }
    }
  }
}

export const families = catalog.families
export const getFamily = (id) => families.find((f) => f.id === id)
export const products = catalog.products
export const getProduct = (code) => catalog.products[code]
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

export function summarize({ family, model, issues = [], tried }) {
  const fam = family ? getFamily(family).name : null
  const prod = model ? getProduct(model) : null
  const lines = []
  if (fam) lines.push(`제품군: ${fam}`)
  lines.push(`모델: ${prod ? `${prod.name} (${prod.code})` : '모델을 잘 모르겠어요'}`)
  if (issues.length) lines.push(`증상: ${issues.map((x) => `${x.code ? `${x.code} · ` : ''}${x.symptom}`).join(' / ')}`)
  for (const t of tried) lines.push(`해 본 조치: ${t.action} (확인: ${t.check})`)
  return lines
}
