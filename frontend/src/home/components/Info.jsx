import { useEffect, useMemo, useRef, useState } from 'react'
import { familyImage, getFamily, getProduct } from '../lib/catalog.js'
import { DOC_LABEL, DOC_ORDER } from '../lib/guide.js'
import { FamilyStep, ModelStep, PathTags, Stepper, Title } from './common.jsx'

const LABELS = ['제품군', '모델', '제품 정보']
const INIT = { hl: null, family: null, model: null, tab: 'spec', sel: null }
const stageOf = (s) => (!s.family ? 0 : !s.model ? 1 : 2)

let infoCache, docsCache
const loadInfo = () => (infoCache ??= import('../data/info.json').then((m) => m.default))
const loadDocs = () => (docsCache ??= import('../data/docs.json').then((m) => m.default))

export const fmtSize = (n) => (n < 1024 ? `${n} B` : `${(n / 1024).toFixed(1)} KB`)
const DOC_ICON = { DS: '📊', IG: '🛠️', MG: '🧰', RN: '🔄', TG: '🔎' }

function QuickFacts({ m }) {
  const rows = [
    ['생산 상태', m.lifecycle_status], ['표준', m.standards.split(';').join(' · ')], ['인증', m.certifications.split(';').join(' · ')],
    ['보증', m.warranty_months && `${m.warranty_months}개월`], ['표준 납기', m.std_lead_time_weeks && `${m.std_lead_time_weeks}주`],
    ['무게', m.weight_kg && `${m.weight_kg} kg`], ['크기(mm)', m.dimensions_mm], ['보호 등급', m.ip_rating], ['사용 온도', m.operating_temp],
  ].filter(([, v]) => v)
  return (
    <dl className="qf">
      {rows.map(([k, v]) => <div key={k}><dt>{k}</dt><dd>{v}</dd></div>)}
    </dl>
  )
}

// nav: 챗봇이 정한 이동 { family, model, tab, attr, n }. 적용한 뒤에는 onNavDone 으로 알린다.
const fromNav = (nav) => ({ ...INIT, hl: nav.family, family: nav.family, model: nav.model ?? null, tab: nav.tab ?? 'spec' })

export default function Info({ onExit, onContext, onInquire, nav, onNavDone }) {
  const [s, setS] = useState(() => (nav ? fromNav(nav) : INIT))
  const [hit, setHit] = useState(null) // 챗봇이 가리킨 항목 { attr, n } — 잠깐만 강조한다
  const listRef = useRef(null)
  const [info, setInfo] = useState(null)
  const [docs, setDocs] = useState(null)
  useEffect(() => { loadInfo().then(setInfo); loadDocs().then(setDocs) }, [])

  const stage = stageOf(s)
  const p = s.model ? getProduct(s.model) : null
  const data = info?.[s.model]
  const mdocs = docs?.[s.model]
  const tabs = useMemo(() => {
    if (!data || !mdocs) return []
    return [
      data.specs.length > 0 && { id: 'spec', label: '주요 사양' },
      Object.keys(mdocs).length > 0 && { id: 'docs', label: '관련 문서' },
      data.fw.length > 0 && { id: 'fw', label: '펌웨어' },
    ].filter(Boolean)
  }, [data, mdocs])
  const tab = tabs.find((t) => t.id === s.tab) ? s.tab : tabs[0]?.id

  // 챗봇 대화에서 온 이동: 제품군 → 모델 → 제품 정보로 옮기고, 요청한 항목을 가리킨다
  useEffect(() => {
    if (!nav) return
    setS({ ...fromNav(nav), sel: nav.attr ? { label: nav.attr } : null })
    setHit(nav.attr ? { attr: nav.attr, n: nav.n } : null)
    onNavDone?.()
  }, [nav?.n]) // eslint-disable-line

  // 가리킨 항목으로 스크롤하고 잠깐 강조한다 (자료가 준비된 뒤)
  useEffect(() => {
    if (!hit || stage !== 2 || tab !== 'spec' || !data) return
    const el = listRef.current?.querySelector(`[data-attr="${CSS.escape(hit.attr)}"]`)
    el?.scrollIntoView({ block: 'center', behavior: window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth' })
    const timer = setTimeout(() => setHit(null), 2400)
    return () => clearTimeout(timer)
  }, [hit, stage, tab, !!data]) // eslint-disable-line

  useEffect(() => {
    if (!s.family) return onContext([])
    const lines = [`제품군: ${getFamily(s.family).name}`]
    if (p) { lines.push(`모델: ${p.name} (${p.code})`); lines.push(`보고 있는 정보: ${tabs.find((t) => t.id === tab)?.label ?? ''}`) }
    if (s.sel?.label) lines.push(`선택한 항목: ${s.sel.label}`)
    onContext(lines)
  }, [s.family, s.model, tab, s.sel, p, tabs, onContext])

  const back = () => {
    if (stage === 2) return setS({ ...s, model: null, sel: null })
    if (stage === 1) return setS({ ...INIT, hl: s.family })
    onExit()
  }
  const goStage = (i) => setS((c) => (i === 0 ? { ...INIT, hl: c.family } : { ...c, model: null, sel: null }))

  return (
    <div className="flow info">
      <div className="fhead">
        <button type="button" className="backbtn" onClick={back}>← 이전</button>
        <Stepper step={stage} onGo={goStage} labels={LABELS} />
      </div>
      <PathTags items={[
        { key: '제품군', label: s.family ? getFamily(s.family).name : '' },
        { key: '모델', label: s.model ? getProduct(s.model).name : '' },
      ]} />

      {stage === 0 && <FamilyStep title="어떤 제품이 궁금하세요?" emoji="📘" s={{ family: s.hl }} pick={(f) => setS({ ...INIT, hl: f, family: f })} pickModel={(f, m) => setS({ ...INIT, hl: f, family: f, model: m })} />}
      {stage === 1 && <ModelStep s={s} allowUnknown={false} pick={(m) => setS((c) => ({ ...c, model: m, sel: null, tab: 'spec' }))} />}

      {stage === 2 && (!data || !mdocs ? <p className="faq-sub">자료를 불러오는 중이에요…</p> : (
        <>
          <div className="pcard">
            <img src={familyImage(s.family)} alt="" />
            <div>
              <small>{getFamily(s.family).name} · {p.code}</small>
              <h2>{p.name}</h2>
              <p>{data.master.description}</p>
              <span className="imgnote">이미지는 제품군 대표 이미지예요</span>
            </div>
          </div>
          <QuickFacts m={data.master} />

          <div className="itabs" role="tablist">
            {tabs.map((t) => (
              <button type="button" role="tab" aria-selected={t.id === tab} key={t.id} className={t.id === tab ? 'on' : ''} onClick={() => setS({ ...s, tab: t.id })}>{t.label}</button>
            ))}
          </div>

          {tab === 'spec' && (
            <div className="ilist" ref={listRef}>
              {data.specs.map((r) => (
                <div key={r.attr} data-attr={r.attr} className={`irow${hit?.attr === r.attr ? ' hit' : ''}`}>
                  <span>{r.attr}</span><b>{r.value}</b>
                </div>
              ))}
            </div>
          )}

          {tab === 'docs' && (
            <div className="ilist">
              {DOC_ORDER.filter((t) => mdocs[t]).map((t) => {
                const d = mdocs[t]
                return (
                  <div key={t} className="dcard">
                    <div className="dmain">
                      <span className="di">{DOC_ICON[t]}</span>
                      <span><b>{DOC_LABEL[t]}</b><small>{d.title}</small><em>{d.id} · Rev. {d.revision}</em></span>
                    </div>
                    <a className="dl" href={`${import.meta.env.BASE_URL}${d.file}`} download>⬇️ 원본 다운로드<small>{d.fmt} · {fmtSize(d.bytes)}</small></a>
                  </div>
                )
              })}
              <p className="hintline">원본은 Markdown(.md) 파일만 있어요. PDF 원본은 제공 자료에 없어요.</p>
            </div>
          )}

          {tab === 'fw' && (
            <div className="ilist">
              <div className="gblock info">
                <b>최신 펌웨어 {data.master.fw_latest}</b>
                <p>아래는 <strong>변경 이력</strong>(릴리스 노트)이에요. 펌웨어 <strong>설치 파일</strong>은 제공 자료에 없어서 내려받을 수 없어요.</p>
              </div>
              {data.fw.slice().reverse().map((f) => {
                return (
                  <div key={f.version} className="fwrow">
                    <div className="fwh"><b>v{f.version}</b>{f.latest && <i>최신</i>}<small>{f.date}</small></div>
                    <ul>{f.changes.map((c) => <li key={c}>{c}</li>)}</ul>
                  </div>
                )
              })}
            </div>
          )}
        </>
      ))}
    </div>
  )
}
