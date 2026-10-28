import { useEffect, useMemo, useState } from 'react'
import { getFamily, getProduct } from '../lib/catalog.js'
import { LABEL, NOTYET, UNKNOWN, answerText, catOf, dept, formFields, questionsFor, resultFor, summaryLines, ymd, today } from '../lib/biz.js'
import { FamilyStep, ModelStep, PathTags, Stepper, Title } from './common.jsx'
import info from '../data/info.json'

const LABELS = ['제품군', '모델', '업무', '진행']
const TASKS = [
  { id: 'warranty', label: '보증 · 교환 · 반품', sub: '보증 조건 확인과 교환·반품 안내' },
  { id: 'order', label: '주문 · 납기', sub: '주문 조건과 표준 납기 확인' },
  { id: 'quote', label: '견적 요청', sub: '수량과 요구사항을 정리해 견적 문의' },
]
const INIT = { hl: null, family: null, model: null, task: null, a: {}, i: 0, phase: 'q', form: {}, evi: null }
const stageOf = (s) => (!s.family ? 0 : !s.model ? 1 : !s.task ? 2 : 3)

function Evidence({ src, onOpen, label = '판단 근거 보기' }) {
  return null // 오른쪽 원문 패널을 없애서 근거 버튼도 없앴다
}

function QuestionView({ q, a, commit, back, last }) {
  const cur = a[q.id]
  const [text, setText] = useState(cur && cur !== UNKNOWN ? String(cur) : '')
  const [sel, setSel] = useState(Array.isArray(cur) ? cur : [])
  const [none, setNone] = useState(Array.isArray(cur) && cur.length === 0)
  const [num, setNum] = useState(cur && !isNaN(cur) ? Number(cur) : q.min ?? 1)
  useEffect(() => {
    setText(cur && cur !== UNKNOWN && cur !== NOTYET ? String(cur) : ''); setSel(Array.isArray(cur) ? cur : []); setNone(Array.isArray(cur) && cur.length === 0)
    setNum(cur && !isNaN(cur) ? Number(cur) : q.min ?? 1)
  }, [q.id]) // eslint-disable-line
  const isD = (v) => typeof v === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(v)
  // 출하일과 시운전일은 앞뒤가 맞아야 한다: 시운전일 ≥ 출하일
  const shipD = isD(a.w_ship) ? a.w_ship : null, commD = isD(a.w_comm) ? a.w_comm : null
  const clash = (id, v) => (id === 'w_comm' && shipD && v < shipD ? `시운전일은 출하일(${shipD})보다 빠를 수 없어요. 출하일 이후 날짜를 골라 주세요.`
    : id === 'w_ship' && commD && v > commD ? `출하일은 시운전일(${commD})보다 늦을 수 없어요. 시운전일 이전 날짜를 골라 주세요.` : '')
  const [warn, setWarn] = useState('')
  useEffect(() => { setWarn('') }, [q.id])
  const bound = (k) => {
    const today_ = ymd(today())
    if (k === 'max') return q.max !== 'today' ? undefined : q.id === 'w_ship' && commD && commD < today_ ? commD : today_
    return q.min === 'today' ? today_ : q.id === 'w_comm' && shipD ? shipD : undefined
  }
  const curWarn = warn || (isD(cur) ? clash(q.id, cur) : '')
  const nextLabel = last ? '결과 보기' : '다음'

  return (
    <div className="qv" key={q.id}>
      <Title emoji="💬" sub={q.sub}>{q.title}</Title>
      {q.type === 'choice' && (
        <div className="opt-list">
          {q.options.map((o) => (
            <button type="button" key={o.v} className={`opt big${cur === o.v ? ' sel' : ''}`} onClick={() => commit(q.id, o.v)}>
              <b>{o.label}</b>{o.sub && <small>{o.sub}</small>}
            </button>
          ))}
        </div>
      )}
      {q.type === 'multi' && (
        <>
          <div className="opt-list">
            {q.options.map((o) => (
              <button type="button" key={o.v} className={`opt big${sel.includes(o.v) ? ' sel' : ''}`} aria-pressed={sel.includes(o.v)} onClick={() => { setNone(false); setSel(sel.includes(o.v) ? sel.filter((x) => x !== o.v) : [...sel, o.v]) }}>
                <b>{o.label}</b>{o.sub && <small>{o.sub}</small>}
              </button>
            ))}
            <button type="button" className={`opt big ghost${none ? ' sel' : ''}`} onClick={() => { setSel([]); setNone(true) }}><b>{q.noneLabel}</b></button>
          </div>
          <div className="qnav"><button type="button" className="gbtn" onClick={back}>이전</button><button type="button" className="pbtn" disabled={!none && sel.length === 0} onClick={() => commit(q.id, sel)}>{nextLabel}</button></div>
        </>
      )}
      {q.type === 'date' && (
        <>
          <input className="qin" type="date" value={cur && cur !== UNKNOWN && cur !== NOTYET ? cur : ''} min={bound('min')} max={bound('max')} onChange={(e) => { const v = e.target.value; if (!v) return; const m = clash(q.id, v); setWarn(m); if (!m) commit(q.id, v, false) }} aria-label={q.title} aria-invalid={!!curWarn} />
          {curWarn && <div className="datewarn" role="alert"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M12 8v5M12 17h.01" /><circle cx="12" cy="12" r="9.5" /></svg><span>{curWarn}</span></div>}
          <div className="chiprow">
            {q.notyet && <button type="button" className={`opt ghost${cur === NOTYET ? ' sel' : ''}`} onClick={() => commit(q.id, NOTYET)}><b>⏳ 아직 시운전 전이에요</b></button>}
            {q.unknown && <button type="button" className={`opt ghost${cur === UNKNOWN ? ' sel' : ''}`} onClick={() => commit(q.id, UNKNOWN)}><b>🤔 잘 모르겠어요</b></button>}
          </div>
          <div className="qnav"><button type="button" className="gbtn" onClick={back}>이전</button><button type="button" className="pbtn" disabled={!cur || !!curWarn} onClick={() => commit(q.id, cur)} style={{ display: cur || curWarn ? '' : 'none' }}>{nextLabel}</button></div>
        </>
      )}
      {q.type === 'number' && (
        <>
          <div className="stepper-n">
            <button type="button" aria-label="하나 줄이기" onClick={() => setNum(Math.max(q.min ?? 1, num - 1))}>−</button>
            <input type="number" inputMode="numeric" min={q.min ?? 1} value={num} onChange={(e) => setNum(Math.max(q.min ?? 1, Math.floor(Number(e.target.value) || 0)))} aria-label={q.title} />
            <button type="button" aria-label="하나 늘리기" onClick={() => setNum(num + 1)}>＋</button><span>개</span>
          </div>
          <div className="qnav"><button type="button" className="gbtn" onClick={back}>이전</button><button type="button" className="pbtn" onClick={() => commit(q.id, num)}>{nextLabel}</button></div>
        </>
      )}
      {q.type === 'text' && (
        <>
          {q.long ? <textarea className="qin" rows={4} value={text} onChange={(e) => setText(e.target.value)} placeholder={q.placeholder} aria-label={q.title} />
            : <input className="qin" value={text} onChange={(e) => setText(e.target.value)} placeholder={q.placeholder} aria-label={q.title} />}
          <div className="chiprow">{q.unknown && <button type="button" className={`opt ghost${cur === UNKNOWN ? ' sel' : ''}`} onClick={() => commit(q.id, UNKNOWN)}><b>🤔 잘 모르겠어요</b></button>}</div>
          <div className="qnav">
            <button type="button" className="gbtn" onClick={back}>이전</button>
            {q.optional && <button type="button" className="gbtn" onClick={() => commit(q.id, '')}>건너뛰기</button>}
            <button type="button" className="pbtn" disabled={!text.trim()} onClick={() => commit(q.id, text.trim())}>{nextLabel}</button>
          </div>
        </>
      )}
      {q.type === 'choice' && <div className="qnav"><button type="button" className="gbtn" onClick={back}>이전</button></div>}
    </div>
  )
}

export default function Biz({ onExit, onContext, onSend, onInquire }) {
  const [s, setS] = useState(INIT)
  const [n, setN] = useState(0)
  const [copied, setCopied] = useState(false)
  const stage = stageOf(s)
  const p = s.model ? getProduct(s.model) : null
  const master = s.model ? info[s.model].master : null
  const ctx = useMemo(() => p && ({ code: p.code, name: p.name, family: s.family, familyName: getFamily(s.family).name, master }), [p, s.family, master])
  const list = useMemo(() => (s.task ? questionsFor(s.task, s.a) : []), [s.task, s.a])
  const q = s.phase === 'q' ? list[Math.min(s.i, list.length - 1)] : null
  const res = useMemo(() => (stage === 3 && s.phase !== 'q' ? resultFor(s.task, s.a, ctx) : null), [stage, s.phase, s.task, s.a, ctx])
  const cat = s.task ? catOf(s.task, s.a) : null
  const fields = useMemo(() => (ctx && cat ? formFields(cat, s.a, ctx, s.form) : []), [ctx, cat, s.a, s.form])

  const open = (src) => { setN((v) => v + 1); setS((c) => ({ ...c, evi: src })) }

  useEffect(() => {
    if (!s.family) return onContext([])
    const lines = [`제품군: ${getFamily(s.family).name}`]
    if (p) lines.push(`모델: ${p.name} (${p.code})`)
    if (s.task) lines.push(`업무: ${TASKS.find((t) => t.id === s.task).label}`)
    if (q) lines.push(`지금 질문: ${q.title}`)
    if (res) lines.push(`지금 화면: ${s.phase === 'result' ? '결과 확인' : s.phase === 'form' ? '접수 내용 확인' : '접수 상태'}`)
    onContext(lines)
  }, [s.family, s.model, s.task, q?.id, s.phase, p, res, onContext]) // eslint-disable-line

  const commit = (id, val, advance = true) => setS((c) => {
    const a = { ...c.a, [id]: val }
    const nl = questionsFor(c.task, a)
    const ids = new Set(nl.map((x) => x.id))
    const pruned = Object.fromEntries(Object.entries(a).filter(([k]) => ids.has(k)))
    if (!advance) return { ...c, a: pruned }
    const ni = nl.findIndex((x) => x.id === id) + 1
    return { ...c, a: pruned, i: ni, phase: ni >= nl.length ? 'result' : 'q', evi: null }
  })
  // 정리한 내용을 문의 남기기 양식으로 넘긴다
  const goInquire = () => onInquire?.({
    type: cat, family: s.family, model: s.model,
    vals: Object.fromEntries(fields.filter((f) => f.value && f.key !== 'product_model' && f.key !== 'photos').map((f) => [f.key, String(f.value)])),
    subject: `${p.name} ${{ WARRANTY: '보증', RETURN: '교환·반품', ORDER_LEAD: '주문·납기', QUOTE: '견적' }[cat]} 문의`,
    body: summary.join('\n'),
  })
  const back = () => {
    if (s.phase === 'sent') return setS({ ...s, phase: res?.cta?.kind === 'quote' ? 'result' : 'form', evi: null })
    if (s.phase === 'form') return setS({ ...s, phase: 'result', evi: null })
    if (s.phase === 'result') return setS({ ...s, phase: 'q', i: list.length - 1, evi: null })
    if (s.i > 0) return setS({ ...s, i: s.i - 1, evi: null })
    setS({ ...s, task: null, a: {}, i: 0, evi: null })
  }
  const topBack = () => (stage === 3 ? back() : stage === 2 ? setS({ ...s, model: null }) : stage === 1 ? setS({ ...INIT, hl: s.family }) : onExit())
  const goStage = (i) => setS((c) => (i === 0 ? { ...INIT, hl: c.family } : i === 1 ? { ...INIT, hl: c.family, family: c.family } : { ...c, task: null, a: {}, i: 0, phase: 'q', evi: null }))

  const summary = res ? summaryLines(s.task, s.a, ctx, fields) : []
  const sendChat = () => { onSend(['보증·주문·견적 접수 내용을 정리했어요.', ...summary, `담당: ${dept(res.route.primary)}${res.route.escalation ? ` (필요 시 ${dept(res.route.escalation)})` : ''}`].join('\n')); setS({ ...s, sent: true }) }
  const copy = async () => { try { await navigator.clipboard.writeText(summary.join('\n')); setCopied(true) } catch { setCopied(false) } }

  const headerBlock = q && (
    q.id === 'w_ship' ? <div className="infob"><div><small>이 모델의 보증 기간</small><b>{master.warranty_months}개월</b></div><Evidence src={{ doc: 'POL-WARRANTY', sec: '1', mark: ctx.code }} onOpen={open} /></div>
      : q.id === 'o_when' ? <div className="infob"><div><small>표준 납기 (공장 출고 기준)</small><b>{master.std_lead_time_weeks}주 · 최소 주문 {master.moq}개</b></div><Evidence src={{ doc: 'POL-ORDER', sec: '1', mark: ctx.code }} onOpen={open} /></div>
        : null
  )

  return (
    <div className="flow biz">
      <div className="fhead">
        <button type="button" className="backbtn" onClick={topBack}>← 이전</button>
        <Stepper step={stage} onGo={goStage} labels={LABELS} />
      </div>

      <PathTags items={[
        { key: '제품군', label: s.family ? getFamily(s.family).name : '', onClick: stage > 0 ? () => goStage(0) : undefined },
        { key: '모델', label: p ? p.name : '', onClick: stage > 1 ? () => goStage(1) : undefined },
        { key: '업무', label: s.task ? TASKS.find((x) => x.id === s.task).label : '', onClick: stage > 2 ? () => goStage(2) : undefined },
      ]} />

      {stage === 0 && <FamilyStep title="어떤 제품에 대해 문의하세요?" emoji="🧾" s={{ family: s.hl }} pick={(f) => setS({ ...INIT, hl: f, family: f })} />}
      {stage === 1 && <ModelStep s={s} allowUnknown={false} pick={(m) => setS((c) => ({ ...INIT, hl: c.hl, family: c.family, model: m }))} />}
      {stage === 2 && (
        <>
          <Title emoji="💬" sub={`${p.name} (${p.code})`}>어떤 일을 도와드릴까요?</Title>
          <div className="opt-list">
            {TASKS.map((t) => (
              <button type="button" key={t.id} className="opt big" onClick={() => setS({ ...s, task: t.id, a: {}, i: 0, phase: 'q', evi: null })}>
                <b>{t.label}</b><small>{t.sub}</small>
              </button>
            ))}
          </div>
        </>
      )}

      {stage === 3 && s.phase === 'q' && q && (
        <>
          <div className="prog"><div className="bar"><i style={{ width: `${((Math.min(s.i, list.length - 1) + 1) / (list.length + 1)) * 100}%` }} /></div><span>{Math.min(s.i, list.length - 1) + 1} / {list.length}</span></div>
          {headerBlock}
          <QuestionView q={q} a={s.a} commit={commit} back={back} last={s.i >= list.length - 1} />
          <Evidence src={q.src} onOpen={open} />
        </>
      )}

      {stage === 3 && s.phase === 'result' && res && (
        <div className="qv">
          <Title emoji={s.task === 'quote' ? '🧾' : '✅'} sub={res.notice}>{res.headline}</Title>
          <div className="rsec ok"><b>확인된 조건</b>
            <ul>{res.conds.map((c) => <li key={c.t}>{c.t}<Evidence src={c.src} onOpen={open} label="근거" /></li>)}</ul></div>
          {res.todo.length > 0 && <div className="rsec ask"><b>추가 확인이 필요한 내용</b>
            <ul>{res.todo.map((c) => <li key={c.t}>{c.t}<Evidence src={c.src} onOpen={open} label="근거" /></li>)}</ul></div>}
          <div className="rsec next"><b>다음 행동</b>
            <ul>{res.next.map((t) => <li key={t}>{t}</li>)}</ul>
            <p className="route">담당: <strong>{dept(res.route.primary)}</strong>{res.route.escalation && <> · 필요 시 {dept(res.route.escalation)} ({res.route.cond})</>}</p></div>
          <div className="qnav"><button type="button" className="gbtn" onClick={back}>이전</button>
            <button type="button" className="pbtn" onClick={() => (res.cta.kind === 'quote' ? goInquire() : setS({ ...s, phase: 'form', evi: null }))}>{res.cta.label}</button></div>
        </div>
      )}

      {stage === 3 && s.phase === 'form' && res && (
        <div className="qv">
          <Title emoji="📝" sub="앞에서 답한 내용이 자동으로 들어갔어요. 비어 있는 곳은 채워 주세요.">접수 내용을 확인해 주세요</Title>
          <div className="formc">
            {fields.map((f) => (
              <label key={f.key} className={f.blocking && !f.value ? 'need' : ''}>
                <span>{f.label}{f.blocking && <i>필수</i>}</span>
                {f.key === 'photos' ? <input type="file" multiple accept="image/*" onChange={(e) => setS({ ...s, form: { ...s.form, photos: [...e.target.files].map((x) => x.name).join(', ') } })} />
                  : f.key === 'failure_description' ? <textarea rows={3} value={f.value} onChange={(e) => setS({ ...s, form: { ...s.form, [f.key]: e.target.value } })} />
                    : <input value={f.value} onChange={(e) => setS({ ...s, form: { ...s.form, [f.key]: e.target.value } })} placeholder={f.blocking ? '모르면 비워 두세요. 담당자가 다시 물어봐요' : ''} />}
              </label>
            ))}
          </div>
          {fields.some((f) => f.blocking && !f.value) && <p className="warnline">필수 항목이 비어 있어요. 이대로 보내면 담당자가 추가로 물어봐요.</p>}
          <p className="hintline">사진 파일은 이 화면에서 전송되지 않아요. 접수 기능이 연결되면 함께 보낼 수 있어요.</p>
          <div className="qnav"><button type="button" className="gbtn" onClick={back}>이전</button>
            <button type="button" className="pbtn" onClick={() => setS({ ...s, phase: 'sent', evi: null })}>{res.cta.label}</button></div>
        </div>
      )}

      {stage === 3 && s.phase === 'sent' && res && (
        <div className="qv">
          <div className="statusb"><b>아직 접수되지 않았어요</b>
            <p>접수·견적 시스템이 연결되지 않아서 <strong>[{res.cta.label}]</strong> 요청은 전달되지 않았고, 접수 번호나 견적서도 발급되지 않았어요. 정리한 내용만 아래에서 AI 상담으로 보내거나 복사할 수 있어요.</p></div>
          <ul className="sumlist">{summary.map((l) => <li key={l}>{l}</li>)}</ul>
          <p className="route">담당 부서: <strong>{dept(res.route.primary)}</strong>{res.route.escalation && <> · 필요 시 {dept(res.route.escalation)}</>}</p>
          <div className="qnav"><button type="button" className="gbtn" onClick={back}>이전</button>
            <button type="button" className="gbtn" onClick={copy}>{copied ? '복사했어요 ✓' : '내용 복사'}</button>
            <button type="button" className="gbtn" onClick={sendChat}>AI 상담으로 내용 보내기</button>
            <button type="button" className="pbtn" onClick={goInquire}>문의 남기기로 이어가기</button></div>
          {s.sent && <p className="hintline">AI 상담 대화에 내용을 보냈어요. 오른쪽 AI 상담에서 확인할 수 있어요.</p>}
          <button type="button" className="link" onClick={onExit}>처음 화면으로</button>
        </div>
      )}
    </div>
  )
}
