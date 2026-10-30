import { useEffect, useMemo, useRef, useState } from 'react'
import { getFamily, getProduct } from '../lib/catalog.js'
import { buildGuide, purposeDesc } from '../lib/guide.js'
import { FamilyStep, ModelStep, PathTags, Stepper, Title } from './common.jsx'

const LABELS = ['제품군', '모델', '목적', '안내']
const PURPOSE = { install: '설치 방법', usage: '사용 방법' }
const INIT = { hl: null, family: null, model: null, purpose: null }

const stageOf = (s) => (!s.family ? 0 : !s.model ? 1 : !s.purpose ? 2 : 3)

let docsCache
const loadDocs = () => (docsCache ??= import('../data/docs.json').then((m) => m.default))

const Chev = () => (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M9 5l7 7-7 7" /></svg>
)

// 단계가 화면에 들어올 때 한 번만 짧게 나타난다.
function useReveal(dep) {
  const root = useRef(null)
  useEffect(() => {
    const els = [...(root.current?.querySelectorAll('.gs') ?? [])]
    if (!('IntersectionObserver' in window)) { els.forEach((e) => e.classList.add('in')); return }
    const io = new IntersectionObserver((es) => es.forEach((e) => { if (e.isIntersecting) { e.target.classList.add('in'); io.unobserve(e.target) } }), { rootMargin: '0px 0px -8% 0px' })
    els.forEach((e) => io.observe(e))
    return () => io.disconnect()
  }, [dep])
  return root
}

function Step({ st, n, onInquire }) {
  const [checked, setChecked] = useState({})
  const list = (items) => <ul className="gl-ul">{items.map((x) => <li key={x}>{x}</li>)}</ul>
  return (
    <li className="gs">
      <span className="gn" aria-hidden="true">{n}</span>
      <div className="gc">
        <h3>{st.title}</h3>
        {st.lead && <p className="glead">{st.lead}</p>}
        {st.summary?.length > 0 && list(st.summary)}
        {st.checks?.length > 0 && <ul className="gchk">{st.checks.map((x) => <li key={x}>{x}</li>)}</ul>}
        {st.bullets?.length > 0 && list(st.bullets)}
        {st.kv?.length > 0 && <dl className="gkv">{st.kv.map(([k, v]) => <div key={k}><dt>{k}</dt><dd>{v}</dd></div>)}</dl>}
        {st.ordered?.length > 0 && <ol className="gol">{st.ordered.map((x) => <li key={x}>{x.replace(/^\d+\.\s*/, '')}</li>)}</ol>}
        {st.checklist?.length > 0 && (
          <ul className="gcl">{st.checklist.map((x) => (
            <li key={x}><label><input type="checkbox" checked={!!checked[x]} onChange={(e) => setChecked({ ...checked, [x]: e.target.checked })} /><span>{x}</span></label></li>
          ))}</ul>
        )}
        {st.table && (
          <ul className="giss">{st.table.rows.map((r) => <li key={r[0]}><b>{r[0]}</b><span>{r[1]}</span><small>{r[2]}</small></li>)}</ul>
        )}
        {st.cautions?.length > 0 && <div className="gwarn"><b>주의</b>{st.cautions.map((x) => <p key={x}>{x}</p>)}</div>}
        {st.notes?.map((x) => (
          <div className="gnote" key={x}>
            <p>{x}</p>
            <div>
              <button type="button" onClick={() => onInquire(x)}>문의 남기기</button>
            </div>
          </div>
        ))}
        {st.raw?.length > 0 && (
          <details className="gdet"><summary>자세히 보기</summary>{list(st.raw)}</details>
        )}
      </div>
    </li>
  )
}

export default function Guide({ onExit, onContext, onInquire }) {
  const [s, setS] = useState(INIT)
  const [docs, setDocs] = useState(null)
  useEffect(() => { loadDocs().then(setDocs) }, [])

  const stage = stageOf(s)
  const mine = docs?.[s.model]
  const guide = useMemo(() => (mine && s.purpose ? buildGuide(s.purpose, mine) : { steps: [], notice: null }), [mine, s.purpose])
  const steps = guide.steps
  const rootRef = useReveal(`${s.model}-${s.purpose}-${steps.length}`)

  // AI 상담에 이어 줄 현재 상황
  useEffect(() => {
    if (!s.family) return onContext([])
    const p = s.model ? getProduct(s.model) : null
    const lines = [`제품군: ${getFamily(s.family).name}`]
    if (p) lines.push(`모델: ${p.name} (${p.code})`)
    if (s.purpose) lines.push(`보고 있는 안내: ${PURPOSE[s.purpose]}`)
    onContext(lines)
  }, [s, onContext])

  const back = () => {
    if (stage === 3) return setS({ ...s, purpose: null })
    if (stage === 2) return setS({ ...s, model: null })
    if (stage === 1) return setS({ ...INIT, hl: s.family })
    onExit()
  }
  const goStage = (n) => setS((c) => {
    if (n === 0) return { ...INIT, hl: c.family }
    if (n === 1) return { ...c, model: null, purpose: null }
    return { ...c, purpose: null }
  })
  const ask = (text) => onInquire?.({
    type: s.purpose === 'install' ? 'INSTALL' : 'USAGE', family: s.family, model: s.model,
    body: `${PURPOSE[s.purpose]} 안내를 보다가 문의드려요.\n${text ? `${text}\n` : ''}보던 안내: ${steps.map((x) => x.title).join(' → ')}`,
  })

  return (
    <div className="flow guide">
      <div className="fhead">
        <button type="button" className="backbtn" onClick={back}>← 이전</button>
        <Stepper step={stage} onGo={goStage} labels={LABELS} />
      </div>
      <PathTags items={[
        { key: '제품군', label: s.family ? getFamily(s.family).name : '' },
        { key: '모델', label: s.model ? getProduct(s.model).name : '' },
        { key: '목적', label: s.purpose ? PURPOSE[s.purpose] : '' },
      ]} />

      {stage === 0 && <FamilyStep title="어떤 제품을 설치·사용하시나요?" emoji="📘" s={{ family: s.hl }} pick={(f) => setS({ ...INIT, hl: f, family: f })} />}
      {stage === 1 && <ModelStep s={s} allowUnknown={false} pick={(m) => setS((c) => ({ ...c, model: m, purpose: null }))} />}

      {stage === 2 && (
        <>
          <Title emoji="📘" sub={`${getProduct(s.model).name} (${getProduct(s.model).code})`}>무엇이 궁금하세요?</Title>
          {!mine ? <p className="faq-sub">원문을 불러오는 중이에요…</p> : (
            <div className="pmenu">
              {['install', 'usage'].map((p) => (
                <button type="button" key={p} className="pm" onClick={() => setS({ ...s, purpose: p })}>
                  <span className="pm-t"><b>{PURPOSE[p]}</b><small>{purposeDesc(p, mine)}</small></span>
                  <Chev />
                </button>
              ))}
            </div>
          )}
        </>
      )}

      {stage === 3 && (
        <div className="gview" ref={rootRef}>
          <Title sub={`${getProduct(s.model).name} (${getProduct(s.model).code})`}>{PURPOSE[s.purpose]}</Title>
          {steps.length === 0 ? <p className="faq-sub">원문을 불러오는 중이에요…</p> : (
            <ol className="gl">
              {steps.map((st, i) => (
                <GroupedStep key={`${s.purpose}-${st.id}`} st={st} n={i + 1} prev={steps[i - 1]} onInquire={ask} />
              ))}
            </ol>
          )}
          <div className="gfoot">
            <button type="button" className="gbtn" onClick={() => setS({ ...s, purpose: null })}>다른 안내 보기</button>
            <button type="button" className="gbtn" onClick={() => ask('')}>해결되지 않았어요 · 문의 남기기</button>
            <button type="button" className="pbtn" onClick={onExit}>처음 화면으로</button>
          </div>
        </div>
      )}
    </div>
  )
}

// 원문이 묶음으로 뒷받침하는 경우(설치 가이드의 준비·설치·확인)에만 묶음 제목을 붙인다.
function GroupedStep({ st, n, prev, onInquire }) {
  return (
    <>
      {st.group && st.group !== prev?.group && <li className="gg" aria-hidden="true">{st.group}</li>}
      <Step st={st} n={n} onInquire={onInquire} />
    </>
  )
}
