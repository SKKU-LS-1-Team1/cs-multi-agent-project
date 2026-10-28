import { useEffect, useState } from 'react'
import {
  NONE, getFamily, getProduct, groupByCode, issuePool, summarize,
} from '../lib/catalog.js'
import { FamilyStep, ModelStep, PathTags, STEPS, Stepper, Title, UNKNOWN } from './common.jsx'

const INIT = { hl: null, family: null, model: null, code: null, issue: null, tried: [], result: null, handoff: false }

const poolOf = (s) => issuePool(s.family, s.model === UNKNOWN ? null : s.model)

// 모델(또는 제품군)을 고른 뒤 자동으로 건너뛸 수 있는 질문은 건너뛴다.
function settle(s) {
  if (!s.family || !s.model) return s
  const groups = groupByCode(poolOf(s))
  if (s.code === null && groups.size === 1) s = { ...s, code: [...groups.keys()][0] }
  if (s.code !== null && s.issue === null && groups.get(s.code)?.length === 1) s = { ...s, issue: groups.get(s.code)[0] }
  return s
}

const stepOf = (s) => (!s.family ? 0 : !s.model ? 1 : !s.issue ? 2 : 3)

function back(s) {
  const groups = s.family && s.model ? groupByCode(poolOf(s)) : null
  if (s.issue) {
    s = { ...s, issue: null, tried: [], result: null, handoff: false }
    if (groups.get(s.code).length > 1) return s
  }
  if (s.code !== null) {
    s = { ...s, code: null }
    if (groups.size > 1) return s
  }
  if (s.model) return { ...s, model: null }
  return { ...INIT, hl: s.family }
}

function CodeStep({ s, pick }) {
  const groups = groupByCode(poolOf(s))
  return (
    <>
      <Title emoji="🔎" sub="제품 화면이나 표시창에 보이는 글자를 골라 주세요.">화면에 표시된 글자가 있나요?</Title>
      <div className="opt-list cols">
        {[...groups.entries()].filter(([k]) => k !== NONE).map(([k, list]) => (
          <button type="button" key={k} className={`opt${s.code === k ? ' sel' : ''}`} onClick={() => pick(k)}>
            <b className="mono">{k}</b><small>{list.length === 1 ? list[0].symptom : `${list.length}가지 경우`}</small>
          </button>
        ))}
        {groups.has(NONE) && (
          <button type="button" className={`opt ghost${s.code === NONE ? ' sel' : ''}`} onClick={() => pick(NONE)}>
            <b>표시된 글자는 없어요</b><small>증상으로 찾아볼게요 · {groups.get(NONE).length}가지</small>
          </button>
        )}
      </div>
    </>
  )
}

function SymptomStep({ s, pick }) {
  const list = groupByCode(poolOf(s)).get(s.code)
  return (
    <>
      <Title emoji="🔎" sub="가장 비슷한 상황을 하나 골라 주세요.">{s.code !== NONE ? `${s.code}, 어떤 상황인가요?` : '어떤 증상인가요?'}</Title>
      <div className="opt-list">
        {list.map((it) => (
          <button type="button" key={it.id} className="opt" onClick={() => pick(it)}>
            <b>{it.symptom}</b>{s.model === UNKNOWN && <small>{getProduct(it.model).name}</small>}
          </button>
        ))}
      </div>
    </>
  )
}

function Solution({ s, set, onHandoff, onExit, onInquire }) {
  const it = s.issue
  const prod = getProduct(it.model)
  // 다른 증상 = 이 모델의 증상 중 내가 고르지 않은 나머지 (에러 코드가 달라도 포함, 이미 본 것은 제외)
  const siblings = poolOf(s).filter((x) => x.model === it.model && x.id !== it.id && !s.tried.some((t) => t.id === x.id))
  const [others, setOthers] = useState(false) // [다른 증상 보기]로 펼친 내용(다른 증상 목록 · 이어가기). 버튼 줄은 그대로 둔다.
  // withCurrent: 지금 화면의 조치를 해 본 조치로 같이 담는다 ("아직 해결되지 않았어요 · 문의 남기기"를 바로 누른 경우)
  const goInquire = (withCurrent = false) => {
    const tried = withCurrent ? [...s.tried, it] : s.tried
    onInquire?.({
      type: 'DEFECT', family: s.family, model: it.model,
      vals: { ...(it.code ? { error_code: it.code } : { error_code: it.symptom }) },
      subject: `${prod.name} ${it.code ? `${it.code} ` : ''}${it.symptom}`.slice(0, 100),
      body: `증상: ${it.symptom}\n${tried.map((x) => `이미 해 본 조치: ${x.action} (확인: ${x.check}) → 해결되지 않았어요`).join('\n')}`,
    })
  }

  if (s.result === 'resolved') {
    return (
      <div className="done-box done-center">
        <svg className="done-ck" width="88" height="88" viewBox="0 0 56 56" fill="none" aria-hidden="true">
          <circle className="ck-ring" cx="28" cy="28" r="25" />
          <path className="ck-tick" d="M17 29.5l7.5 7.5L39.5 20.5" />
        </svg>
        <h2>해결되었다니 다행이에요!</h2>
        <button type="button" className="pbtn" onClick={onExit}>돌아가기</button>
      </div>
    )
  }

  return (
    <>
      <Title>이렇게 해 보세요</Title>
      <div className="sol">
        <div className="why"><small>이런 원인일 수 있어요</small><p>{it.cause}</p></div>
        <ol className="steps">
          <li><span className="sn">1</span><div><small>먼저 확인해요</small><p>{it.check}</p></div></li>
          <li><span className="sn">2</span><div><small>이렇게 조치해요</small><p>{it.action}</p></div></li>
        </ol>
        {it.note && <div className="warn"><b>꼭 알아 두세요</b><p>{it.note}</p></div>}
      </div>

      <div className="gfoot">
        <button type="button" className="gbtn" aria-expanded={others} onClick={() => setOthers((v) => !v)}>{others ? '다른 증상 닫기' : '다른 증상 보기'}</button>
        <button type="button" className="gbtn" onClick={() => goInquire(true)}>아직 해결되지 않았어요 · 문의 남기기</button>
        <button type="button" className="pbtn" onClick={onExit}>처음 화면으로</button>
      </div>

      {others && (
        <div className="next">
          <div className="opt-list" aria-label="다른 증상">
            {siblings.length === 0 && <p className="next-none">비슷한 다른 증상이 없어요.</p>}
            {siblings.map((x) => (
              <button type="button" key={x.id} className="opt" onClick={() => set({ tried: [...s.tried, it], issue: x, code: x.code ?? NONE, result: null })}>
                <b>{x.symptom}</b>{x.code && <em className="opt-code">{x.code}</em>}
              </button>
            ))}
          </div>
        </div>
      )}

    </>
  )
}

export default function Flow({ onExit, onContext, onHandoff, onInquire }) {
  const [s, setS] = useState(INIT)
  const merge = (p) => setS((cur) => ({ ...cur, ...p }))
  const step = stepOf(s)

  // 챗봇에 이어 줄 현재 선택 내용
  useEffect(() => {
    onContext(s.family ? summarize({ family: s.family, model: s.model === UNKNOWN ? null : s.model, issue: s.issue, tried: s.tried }) : [])
  }, [s.family, s.model, s.issue, s.tried, onContext])

  const goStep = (i) => setS((cur) => { let n = cur; while (stepOf(n) > i) n = back(n); return n })
  const prev = () => (s.family ? setS(back(s)) : onExit())

  const pickModel = (m) => setS((c) => settle({ ...c, model: m, code: null, issue: null, tried: [], result: null }))
  const pickCode = (k) => setS((c) => settle({ ...c, code: k, issue: null }))
  const pickIssue = (it) => setS((c) => ({ ...c, issue: it, tried: [], result: null }))

  // 제품군을 고르면 잠깐 강조를 보여 준 뒤 다음 단계로
  const [pending, setPending] = useState(null)
  useEffect(() => {
    if (!pending) return
    const t = setTimeout(() => { setS((c) => settle({ ...c, hl: pending, family: pending, model: null, code: null, issue: null, tried: [], result: null })); setPending(null) }, 260)
    return () => clearTimeout(t)
  }, [pending])

  const sol = step === 3
  return (
    <div className="flow">
      <div className="fhead">
        <button type="button" className="backbtn" onClick={prev}>← 이전</button>
        <Stepper step={step} onGo={(i) => goStep(i)} />
      </div>
      <PathTags items={[
        { key: '제품군', label: s.family ? getFamily(s.family).name : '' },
        { key: '모델', label: s.model ? (s.model === UNKNOWN ? '모델 모름' : getProduct(s.model).name) : '' },
        { key: '증상', label: s.code && s.code !== NONE ? s.code : (s.issue ? s.issue.symptom : '') },
      ]} />
      {step === 0 && <FamilyStep s={{ ...s, family: pending ?? s.hl }} pick={setPending} />}
      {step === 1 && <ModelStep s={s} pick={pickModel} />}
      {step === 2 && (s.code === null ? <CodeStep s={s} pick={pickCode} /> : <SymptomStep s={s} pick={pickIssue} />)}
      {sol && <Solution key={s.issue.id} s={s} set={merge} onHandoff={onHandoff} onExit={onExit} onInquire={onInquire} />}
    </div>
  )
}
