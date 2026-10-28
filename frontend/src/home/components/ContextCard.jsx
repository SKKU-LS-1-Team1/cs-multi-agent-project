import { useEffect, useId, useRef, useState } from 'react'

// 'AI가 어떤 제품·증상을 기준으로 상담하는지' 보여 주는 작은 카드.
// 입력은 각 화면이 넘기는 "라벨: 값" 문장 목록 그대로 — 화면 쪽은 건드리지 않는다.
const parse = (lines) => lines.map((l) => {
  const i = l.indexOf(': ')
  return i < 0 ? { label: '', value: l } : { label: l.slice(0, i), value: l.slice(i + 2) }
})
const UNKNOWN_MODEL = '모델을 잘 모르겠어요'
// "이름 (코드)" → 이름과 코드를 나눈다
const splitModel = (v) => {
  const m = v.match(/^(.*?)\s*\(([^()]+)\)\s*$/)
  return m ? { name: m[1], code: m[2] } : { name: v, code: '' }
}

export default function ContextCard({ lines, topics = [], onRemove, active = false, onActivate }) {
  const [open, setOpen] = useState(false)
  const [flash, setFlash] = useState({})
  const prev = useRef(null)
  const id = useId()

  const items = parse(lines)
  const get = (label) => items.find((x) => x.label === label)?.value
  const family = get('제품군')
  const modelRaw = get('모델')
  const model = modelRaw && modelRaw !== UNKNOWN_MODEL ? splitModel(modelRaw) : null
  const symptom = get('증상')
  const extras = items.filter((x) => !['제품군', '모델', '증상'].includes(x.label))

  const title = model?.name ?? family ?? items[0]?.value ?? ''
  // 접힌 상태의 한 줄 요약: 증상, 없으면 지금 하고 있는 일(첫 보조 항목)
  const summary = symptom ?? extras[0]?.value ?? ''

  // 값이 바뀐 항목만 잠깐 연한 파랑으로 표시한다. (처음 나타날 때는 표시하지 않는다)
  const key = JSON.stringify(items)
  useEffect(() => {
    const now = Object.fromEntries(items.map((x) => [x.label || x.value, x.value]))
    const old = prev.current
    prev.current = now
    if (!old) return
    const changed = {}
    for (const k of Object.keys(now)) if (old[k] !== now[k]) changed[k] = true
    if (!Object.keys(changed).length) return
    setFlash(changed)
    const t = setTimeout(() => setFlash({}), 1400)
    return () => clearTimeout(t)
  }, [key]) // eslint-disable-line

  const f = (k) => (flash[k] ? ' flash' : '')
  const titleKey = model ? '모델' : family ? '제품군' : items[0]?.label || items[0]?.value
  const sumKey = symptom ? '증상' : extras[0] ? (extras[0].label || extras[0].value) : ''

  return (
    <section className={`cc${active ? ' is-active' : ''}`} aria-label="상담 중인 제품">
      {onRemove && (
        <button type="button" className="cc-x" aria-label={`${title} 상담 목록에서 지우기`} onClick={onRemove}>
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18" /></svg>
        </button>
      )}
      <div className="cc-h">
        <button type="button" className="cc-pick" aria-pressed={active} aria-label={`${title} 대화 열기`} onClick={onActivate}>
          <span className="cc-t">
            {active && <small className="cc-live"><i aria-hidden="true" />대화 중</small>}
            <b className={`cc-name${f(titleKey)}`}>{title}</b>
            {topics.length > 0
              ? <span className="cc-tags">{topics.map((x) => <i key={x}>{x}</i>)}</span>
              : summary && <span className={`cc-sum${open ? ' off' : ''}${f(sumKey)}`}>{summary}</span>}
          </span>
        </button>
        <button type="button" className="cc-toggle" aria-expanded={open} aria-controls={id} aria-label={`${title} 자세히 ${open ? '접기' : '보기'}`} onClick={() => setOpen((v) => !v)}>
          <svg className="cc-chev" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M6 9l6 6 6-6" /></svg>
        </button>
      </div>
      <div className={`cc-wrap${open ? ' open' : ''}`} id={id} role="region" aria-label="상담 중인 내용 자세히">
        <div className="cc-in"><dl className="cc-dl">
          {family && <div className={f('제품군')}><dt>제품군</dt><dd>{family}</dd></div>}
          {modelRaw && (
            <div className={f('모델')}>
              <dt>모델</dt>
              <dd>{model ? <>{model.name}{model.code && <small>{model.code}</small>}</> : modelRaw}</dd>
            </div>
          )}
          {symptom && <div className={f('증상')}><dt>증상</dt><dd>{symptom}</dd></div>}
          {extras.map((x) => <div key={x.label || x.value} className={f(x.label || x.value)}><dt>{x.label}</dt><dd>{x.value}</dd></div>)}
        </dl></div>
      </div>
    </section>
  )
}
