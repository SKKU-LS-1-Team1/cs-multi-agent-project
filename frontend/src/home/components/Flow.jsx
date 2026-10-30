import { useEffect, useRef, useState } from 'react'
import {
  NONE, getFamily, getProduct, groupByCode, issuePool, summarize,
} from '../lib/catalog.js'
import { FamilyStep, ModelStep, PathTags, STEPS, Stepper, Title, UNKNOWN } from './common.jsx'
import MediaAttach from './MediaAttach.jsx'
// 고장 모습 첨부에서는 QR을 받지 않는다 (QR은 모델 고르기 단계에서 받는다)
const FAULT_KINDS = ['photo', 'video', 'sound']
import { describe } from '../lib/media.js'

const INIT = { hl: null, family: null, model: null, code: null, issues: [], picked: [], tried: [], result: null, handoff: false }

const poolOf = (s) => issuePool(s.family, s.model === UNKNOWN ? null : s.model)

// 모델(또는 제품군)을 고른 뒤 자동으로 건너뛸 수 있는 질문은 건너뛴다.
function settle(s) {
  if (!s.family || !s.model) return s
  const groups = groupByCode(poolOf(s))
  if (s.code === null && groups.size === 1) s = { ...s, code: [...groups.keys()][0] }
  if (s.code !== null && s.issues.length === 0 && groups.get(s.code)?.length === 1) s = { ...s, issues: [groups.get(s.code)[0]] }
  return s
}

const stepOf = (s) => (!s.family ? 0 : !s.model ? 1 : !s.issues.length ? 2 : 3)

function back(s) {
  const groups = s.family && s.model ? groupByCode(poolOf(s)) : null
  if (s.issues.length) {
    s = { ...s, issues: [], tried: [], result: null, handoff: false }   // 고른 체크(picked)는 남겨 두어 돌아가서 바꿀 수 있다
    if (groups.get(s.code).length > 1) return s
  }
  if (s.code !== null) {
    s = { ...s, code: null, picked: [] }
    if (groups.size > 1) return s
  }
  if (s.model) return { ...s, model: null, picked: [] }
  return { ...INIT, hl: s.family }
}

// 증상 고르기(여러 개). picked = 체크한 증상. 확정하면 issues가 되고 해결 화면으로 간다.
const toggled = (c, it) => ({ ...c, picked: c.picked.some((x) => x.id === it.id) ? c.picked.filter((x) => x.id !== it.id) : [...c.picked, it] })
const confirmed = (c) => {
  if (!c.picked.length) return c
  const list = groupByCode(poolOf(c)).get(c.code) ?? []
  return { ...c, issues: list.filter((x) => c.picked.some((p) => p.id === x.id)), tried: [], result: null }   // 보여 주는 순서는 목록 순서
}

// children = 제목 바로 아래, 선택지 위에 놓을 내용(첨부 올리기). 제목이 항상 맨 위다.
function CodeStep({ s, pick, children }) {
  const groups = groupByCode(poolOf(s))
  return (
    <>
      <Title emoji="🔎" sub="제품 화면이나 표시창에 보이는 글자를 골라 주세요.">화면에 표시된 글자가 있나요?</Title>
      {children}
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

function SymptomStep({ s, toggle, confirm, children }) {
  const list = groupByCode(poolOf(s)).get(s.code)
  const n = s.picked.length
  return (
    <>
      <Title emoji="🔎">{s.code !== NONE ? `${s.code}, 어떤 상황인가요?` : '어떤 증상인가요?'}</Title>
      {children}
      <div className="opt-list" role="group" aria-label="증상 (여러 개 고를 수 있어요)">
        {list.map((it) => {
          const on = s.picked.some((x) => x.id === it.id)
          return (
            <button type="button" key={it.id} className={`opt multi${on ? ' sel' : ''}`} aria-pressed={on} onClick={() => toggle(it)}>
              <span className="chk" aria-hidden="true">{on && <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3.4" strokeLinecap="round" strokeLinejoin="round"><path d="M5 12.5l4.5 4.5L19 7.5" /></svg>}</span>
              <span className="mtxt"><b>{it.symptom}</b>{s.model === UNKNOWN && <small>{getProduct(it.model).name}</small>}</span>
            </button>
          )
        })}
      </div>
      <div className="multi-foot">
        <button type="button" className="pbtn" disabled={!n} onClick={confirm}>{n ? `선택한 ${n}가지 해결 방법 보기` : '증상을 골라 주세요'}</button>
      </div>
    </>
  )
}

// 문의서로 넘길 초안. withCurrent: 지금 화면의 조치를 해 본 조치로 같이 담는다 ("아직 해결되지 않았어요 · 문의 남기기"를 바로 누른 경우).
// 증상이 여럿이면 제목은 "첫 증상 외 N건", 본문에는 증상을 모두 적는다. 모델이 섞이면 어느 제품 증상인지 앞에 적는다.
const inquiryDraft = (s, withCurrent = false) => {
  const its = s.issues
  const [first] = its
  const tried = withCurrent ? [...s.tried, ...its] : s.tried
  const mixed = new Set(its.map((x) => x.model)).size > 1
  const label = (x) => `${mixed ? `[${getProduct(x.model).name}] ` : ''}${x.symptom}`
  return {
    type: 'DEFECT', family: s.family, model: first.model,
    vals: { error_code: its.map((x) => x.code || x.symptom).join(', ') },
    subject: `${getProduct(first.model).name} ${first.code ? `${first.code} ` : ''}${first.symptom}${its.length > 1 ? ` 외 ${its.length - 1}건` : ''}`.slice(0, 100),
    body: `${its.map((x) => `증상: ${label(x)}`).join('\n')}\n${tried.map((x) => `이미 해 본 조치: ${x.action} (확인: ${x.check}) → 해결되지 않았어요`).join('\n')}`,
  }
}

function Solution({ s, set, onHandoff, onExit, onInquire }) {
  const its = s.issues
  // 다른 증상 = 고른 증상과 같은 모델의 증상 중 고르지 않은 나머지 (에러 코드가 달라도 포함, 이미 본 것은 제외)
  const models = new Set(its.map((x) => x.model))
  const siblings = poolOf(s).filter((x) => models.has(x.model) && !its.some((i) => i.id === x.id) && !s.tried.some((t) => t.id === x.id))
  const [others, setOthers] = useState(false) // [다른 증상 보기]로 펼친 내용(다른 증상 목록 · 이어가기). 버튼 줄은 그대로 둔다.
  const goInquire = (withCurrent = false) => onInquire?.(inquiryDraft(s, withCurrent))

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
      <Title>{its.length > 1 ? `이렇게 해 보세요 (${its.length}가지 증상)` : '이렇게 해 보세요'}</Title>
      {its.map((it, n) => (
        <section key={it.id} className="sol-one" aria-label={`${it.symptom} 해결 방법`}>
          {its.length > 1 && <h3 className="sol-h"><span className="sn">{n + 1}</span>{it.symptom}{it.code && <em className="opt-code">{it.code}</em>}</h3>}
          <div className="sol">
            <div className="why"><small>이런 원인일 수 있어요</small><p>{it.cause}</p></div>
            <ol className="steps">
              <li><span className="sn">1</span><div><small>먼저 확인해요</small><p>{it.check}</p></div></li>
              <li><span className="sn">2</span><div><small>이렇게 조치해요</small><p>{it.action}</p></div></li>
            </ol>
            {it.note && <div className="warn"><b>꼭 알아 두세요</b><p>{it.note}</p></div>}
          </div>
        </section>
      ))}

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
              <button type="button" key={x.id} className="opt" onClick={() => set({ tried: [...s.tried, ...its], issues: [x], picked: [x], code: x.code ?? NONE, result: null })}>
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

  // 증상 단계에서 올린 사진·영상·소리·QR. 단계를 오가도 남도록 여기서 쥐고, 화면을 나갈 때 미리보기 주소를 푼다.
  const [media, setMedia] = useState([])
  const mediaRef = useRef(media)
  mediaRef.current = media
  useEffect(() => () => mediaRef.current.forEach((x) => URL.revokeObjectURL(x.url)), [])
  const attach = describe(media)

  // 챗봇에 이어 줄 현재 선택 내용 (올린 첨부가 있으면 "첨부: 사진 2 · 영상 1" 한 줄)
  useEffect(() => {
    onContext(s.family ? [...summarize({ family: s.family, model: s.model === UNKNOWN ? null : s.model, issues: s.issues, tried: s.tried }), ...(attach ? [`첨부: ${attach}`] : [])] : [])
  }, [s.family, s.model, s.issues, s.tried, attach, onContext])

  const goStep = (i) => setS((cur) => { let n = cur; while (stepOf(n) > i) n = back(n); return n })
  const prev = () => (s.family ? setS(back(s)) : onExit())

  const pickModel = (m) => setS((c) => settle({ ...c, model: m, code: null, issues: [], picked: [], tried: [], result: null }))
  const pickCode = (k) => setS((c) => settle({ ...c, code: k, issues: [], picked: [] }))
  const toggleIssue = (it) => setS((c) => toggled(c, it))
  const confirmIssues = () => setS((c) => confirmed(c))

  // 제품군을 고르면 잠깐 강조를 보여 준 뒤 다음 단계로
  const [pending, setPending] = useState(null)
  useEffect(() => {
    if (!pending) return
    const t = setTimeout(() => { setS((c) => settle({ ...c, hl: pending, family: pending, model: null, code: null, issues: [], picked: [], tried: [], result: null })); setPending(null) }, 260)
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
        { key: '증상', label: s.code && s.code !== NONE ? s.code : (s.issues.length ? `${s.issues[0].symptom}${s.issues.length > 1 ? ` 외 ${s.issues.length - 1}` : ''}` : '') },
      ]} />
      {step === 0 && <FamilyStep s={{ ...s, family: pending ?? s.hl }} pick={setPending} />}
      {step === 1 && <ModelStep s={s} pick={pickModel} legacy={{ onInquire }} media={media} onMedia={setMedia} />}
      {step === 2 && (s.code === null
        ? <CodeStep s={s} pick={pickCode}><MediaAttach value={media} onChange={setMedia} kinds={FAULT_KINDS} /></CodeStep>
        : <SymptomStep s={s} toggle={toggleIssue} confirm={confirmIssues}><MediaAttach value={media} onChange={setMedia} kinds={FAULT_KINDS} /></SymptomStep>)}
      {sol && <Solution key={s.issues.map((x) => x.id).join('|')} s={s} set={merge} onHandoff={onHandoff} onExit={onExit} onInquire={onInquire} />}
    </div>
  )
}
