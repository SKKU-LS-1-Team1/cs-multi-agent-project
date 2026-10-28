import { useEffect, useMemo, useRef, useState } from 'react'
import { getFamily, getProduct } from '../lib/catalog.js'
import { customer, dept } from '../lib/inquiry.js'
import {
  CATEGORIES, EXAMPLES, LANGUAGES, TYPE_NAME, confOf, errorText, fieldsFor, filled, humanSize, isDate, missingOf, routeOf, typeInfo,
} from '../lib/inquiryForm.js'
import CuteIcon from './CuteIcon.jsx'
import { FamilyStep, ModelStep, PathTags, Stepper, Title, UNKNOWN } from './common.jsx'

const LABELS = ['문의 선택', '필요한 정보', '내용 · 연락처', '확인 · 제출']
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
const Auto = () => <em className="autot">자동 입력</em>

function start(draft = {}) {
  const vals = { ...(draft.vals ?? {}) }
  const s = {
    stage: 1, hl: draft.family ?? null, type: draft.type ?? null, catId: draft.type ? typeInfo(draft.type)?.cat : null,
    family: draft.family ?? null, model: draft.model ?? null, vals, files: {},
    auto: Object.fromEntries(Object.keys(vals).map((k) => [k, true])),
    snap: null, page: 0, editing: {}, attempted: false, touched: {}, help: {}, focusKey: null,
    subject: draft.subject ?? '', body: draft.body ?? '', subjectAuto: !!draft.subject, bodyAuto: !!draft.body,
    contact: { country: customer.country_name, lang: customer.language, company: customer.company_masked, email: customer.contact_email_masked, phone: '', pref: '' },
    contactEdited: {}, submitting: false, error: null, done: null, chatOpen: false, chat: draft.chat ?? null,
  }
  return s.type && s.family && s.model ? enter2(applyModel(s)) : s
}
function applyModel(s) {
  if (!s.model || s.model === UNKNOWN) return s
  const p = getProduct(s.model)
  if (s.vals.product_model && !s.auto.product_model) return s
  return { ...s, vals: { ...s.vals, product_model: `${p.name} (${p.code})` }, auto: { ...s.auto, product_model: true } }
}
const enter2 = (s) => {
  const fields = fieldsFor(s.type, s.family)
  return { ...s, stage: 2, page: 0, snap: new Set(fields.filter((f) => filled(f, s.vals, s.files)).map((f) => f.key)) }
}

function pagesOf(fields, snap) {
  const rest = fields.filter((f) => !snap.has(f.key))
  const chunk = (a) => Array.from({ length: Math.ceil(a.length / 3) }, (_, i) => a.slice(i * 3, i * 3 + 3))
  const pages = [...chunk(rest.filter((f) => confOf(f.key).type !== 'file')), ...chunk(rest.filter((f) => confOf(f.key).type === 'file'))]
  return pages.length ? pages : [[]]
}

function Dropzone({ f, files, setFiles, error, onTouch }) {
  const ref = useRef(null)
  const [over, setOver] = useState(false)
  const add = (list) => { onTouch(); setFiles([...(files ?? []), ...[...list].map((file) => ({ file, id: `${file.name}-${file.size}-${Math.random()}` }))]) }
  return (
    <div>
      <div className={`drop${over ? ' over' : ''}${error ? ' bad' : ''}`} onDragOver={(e) => { e.preventDefault(); setOver(true) }} onDragLeave={() => setOver(false)} onDrop={(e) => { e.preventDefault(); setOver(false); add(e.dataTransfer.files) }}>
        <span>📎 여기로 끌어 놓거나</span>
        <button type="button" className="gbtn" onClick={() => ref.current.click()}>파일 선택</button>
        <input ref={ref} type="file" multiple hidden onChange={(e) => { add(e.target.files); e.target.value = '' }} aria-label={f.label} />
      </div>
      {(files ?? []).length > 0 && (
        <ul className="flist">{files.map((x) => (
          <li key={x.id}><span>📄 {x.file.name}</span><small>{humanSize(x.file.size)} · 선택됨</small>
            <button type="button" aria-label={`${x.file.name} 삭제`} onClick={() => setFiles(files.filter((y) => y.id !== x.id))}>삭제</button></li>
        ))}</ul>
      )}
    </div>
  )
}

export default function Inquire({ draft, onSubmitted, onOpenMine, onExit, onContext }) {
  const [s, setS] = useState(() => start(draft))
  const set = (p) => setS((c) => ({ ...c, ...(typeof p === 'function' ? p(c) : p) }))
  const fields = useMemo(() => (s.type && s.family ? fieldsFor(s.type, s.family) : []), [s.type, s.family])
  const missing = useMemo(() => missingOf(fields, s.vals, s.files), [fields, s.vals, s.files])
  const pages = useMemo(() => (s.snap ? pagesOf(fields, s.snap) : [[]]), [fields, s.snap])
  const p = s.model && s.model !== UNKNOWN ? getProduct(s.model) : null
  const route = s.type && s.type !== 'USAGE' && s.family ? routeOf(s.family, s.type) : null

  // 내용·연락처 필수 (제목 · 상세 내용 · 이메일)
  const contentMissing = [!s.subject.trim() && { key: '__subject', label: '문의 제목', stage: 3 }, !s.body.trim() && { key: '__body', label: '상세 내용', stage: 3 }, !s.contact.email.trim() && { key: '__email', label: '이메일', stage: 3 }].filter(Boolean)
  const allMissing = [...missing.map((f) => ({ key: f.key, label: f.label, stage: 2, blocking: f.blocking })), ...contentMissing]

  useEffect(() => {
    onContext([...(s.family ? [`제품군: ${getFamily(s.family).name}`] : []), ...(p ? [`모델: ${p.name} (${p.code})`] : []), ...(s.type ? [`문의 유형: ${TYPE_NAME[s.type]}`] : []), `작성 단계: ${LABELS[s.stage - 1]}`])
  }, [s.family, s.model, s.type, s.stage, p, onContext]) // eslint-disable-line

  useEffect(() => {
    if (!s.focusKey) return
    const el = document.querySelector(`[data-field="${s.focusKey}"] input:not([type=file]), [data-field="${s.focusKey}"] textarea, [data-field="${s.focusKey}"] button.gbtn`)
    el?.focus(); el?.scrollIntoView({ block: 'center', behavior: 'smooth' })
    set({ focusKey: null })
  }, [s.focusKey, s.page, s.stage]) // eslint-disable-line

  const setVal = (k, v) => set((c) => ({ vals: { ...c.vals, [k]: v }, auto: { ...c.auto, [k]: false } }))
  const touch = (k) => set((c) => ({ touched: { ...c.touched, [k]: true } }))
  const goMissing = () => {
    const m = allMissing[0]
    if (!m) return
    if (m.stage === 2) {
      const all = pagesOf(fields, s.snap ?? new Set())
      const idx = Math.max(0, all.findIndex((pg) => pg.some((f) => f.key === m.key)))
      // 이미 파악해 둔 항목이면 첫 쪽의 확인 요약에서 고친다
      set({ stage: 2, page: s.snap?.has(m.key) ? 0 : idx, attempted: true, editing: { ...s.editing, [m.key]: true }, focusKey: m.key })
    } else set({ stage: 3, attempted: true, focusKey: m.key })
  }

  const renderField = (f) => {
    const cf = confOf(f.key), val = s.vals[f.key] ?? '', show = (s.attempted || s.touched[f.key]) && !filled(f, s.vals, s.files)
    const dateOk = cf.type !== 'date' || !val || isDate(val)
    return (
      <div className={`fld${show ? ' err' : ''}`} key={f.key} data-field={f.key}>
        <label>
          <span>{f.label}{f.blocking && <i className="must">꼭 필요해요</i>}{s.auto[f.key] && val && <Auto />}</span>
          {cf.help && <small>{cf.help}</small>}
          {cf.type === 'file' ? <Dropzone f={f} files={s.files[f.key]} error={show} onTouch={() => touch(f.key)} setFiles={(l) => set((c) => ({ files: { ...c.files, [f.key]: l } }))} />
            : cf.type === 'textarea' ? <textarea className="qin" rows={3} value={val} placeholder={cf.placeholder} onChange={(e) => setVal(f.key, e.target.value)} onBlur={() => touch(f.key)} />
              : <input className="qin" type={cf.type === 'date' && dateOk ? 'date' : cf.type === 'number' ? 'number' : 'text'} min={cf.type === 'number' ? 1 : undefined} list={cf.list ? `dl-${f.key}` : undefined}
                value={val} placeholder={cf.placeholder} onChange={(e) => setVal(f.key, e.target.value)} onBlur={() => touch(f.key)} aria-invalid={show} />}
        </label>
        {cf.list && <datalist id={`dl-${f.key}`}>{cf.list.map((x) => <option key={x} value={x} />)}</datalist>}
        {cf.needsHelp && <button type="button" className="gbtn" onClick={() => set((c) => ({ help: { ...c.help, [f.key]: !c.help[f.key] } }))}>잘 모르겠어요</button>}
        {s.help[f.key] && <p className="helpbox">{cf.help} 정해지지 않았거나 모르면 이 칸은 비워 두고 AI 상담에서 먼저 물어보세요. <b>값이 정해지기 전에는 입력 완료로 처리되지 않아요.</b></p>}
        {show && <p className="ferr" role="alert">{errorText(f)}</p>}
      </div>
    )
  }

  const submit = async () => {
    if (s.submitting || allMissing.length) return
    set({ submitting: true, error: null })
    try {
      await sleep(700)
      const now = new Date()
      const id = `WEB-${now.toISOString().slice(0, 10).replaceAll('-', '')}-${String(now.getTime()).slice(-5)}`
      const provided = fields.filter((f) => filled(f, s.vals, s.files))
      const details = provided.map((f) => `- ${f.label}: ${confOf(f.key).type === 'file' ? (s.files[f.key] ?? []).map((x) => `[attachment: ${x.file.name}]`).join(' ') : s.vals[f.key]}`).join('\n')
      const t = {
        demoSubmit: true, ticket_id: id, received_at_utc: now.toISOString().slice(0, 19) + 'Z', channel: 'WEB_FORM', language: s.contact.lang, body_language: s.contact.lang, customer_tier: customer.tier,
        product_code: p?.code ?? '', product_name: p?.name ?? '(모델 미확인)', product_family: s.family, category_code: s.type === 'USAGE' ? '' : s.type,
        inquiry_subject: s.subject.trim(), inquiry_body: `${s.body.trim()}\n\nDetails:\n${details}`, error_code_reported: '', fw_version_reported: '', priority: '',
        assigned_dept: route?.primary ?? 'GCS_L1', escalated: 'N', escalated_to: '', escalation_reason: '', required_info: fields.map((f) => f.key).join(';'),
        provided_info: provided.map((f) => f.key).join(';'), missing_info: '', missing_blocking_info: '', info_request_sent: 'N', info_request_message: '', status: 'NEW',
        first_response_at_utc: '', resolved_at_utc: '', first_response_hours: '', sla_first_response_target_h: '', sla_resolution_target_h: '', sla_elapsed_hours: '',
        sla_first_response_status: '', sla_resolution_status: '', final_action: '', final_reply: '', rma_no: '', reference_doc_id: '', reference_section: '',
        thread_from: draft?.fromTicket ?? '',
      }
      onSubmitted(t)
      set({ submitting: false, done: t })
    } catch (e) {
      set({ submitting: false, error: `${e.message}. 작성한 내용은 그대로 남아 있어요. 다시 시도해 주세요.` })
    }
  }

  const back = () => {
    if (s.stage === 4) return set({ stage: 3 })
    if (s.stage === 3) return set({ stage: 2, page: pages.length - 1 })
    if (s.stage === 2) return s.page > 0 ? set({ page: s.page - 1 }) : set({ stage: 1, model: null })
    if (s.model) return set({ model: null })
    if (s.family) return set({ family: null, hl: s.family })
    if (s.type) return set({ type: null, catId: s.catId })
    onExit()
  }
  const goStage = (i) => set((c) => (i === 0 ? { stage: 1, model: null } : { stage: i + 1 }))

  if (s.done) {
    return (
      <div className="flow inquire">
        <div className="done-box">
          <h2>접수 완료</h2>
          <p>문의번호 <b>{s.done.ticket_id}</b></p>
          <div className="row"><button type="button" className="gbtn" onClick={onExit}>처음 화면으로</button>
            <button type="button" className="pbtn" onClick={() => onOpenMine(s.done.ticket_id)}>내 문의에서 확인하기</button></div></div>
      </div>
    )
  }

  const tInfo = s.type ? typeInfo(s.type) : null
  const cat = CATEGORIES.find((c) => c.id === s.catId)
  const page = pages[Math.min(s.page, pages.length - 1)] ?? []
  const knownFields = s.snap ? fields.filter((f) => s.snap.has(f.key)) : []

  return (
    <div className="flow inquire is-write">
      <div className="fhead"><button type="button" className="backbtn" onClick={back}>← 이전</button>
        <span className="wbadge"><CuteIcon name="doc" size={16} />문의서 작성</span>
        <Stepper step={s.stage - 1} onGo={goStage} labels={LABELS} /></div>
      <div className="wsheet">

      {s.stage === 1 && (
        <>
          <PathTags items={[
            { key: '유형', label: s.type ? TYPE_NAME[s.type] : '', onClick: () => set({ type: null, model: null }) },
            { key: '제품군', label: s.family ? getFamily(s.family).name : '', onClick: () => set({ family: null, model: null, hl: s.family }) },
          ]} />
          {!s.type && !cat && (
            <>
              <Title emoji="📝" sub="가장 가까운 것을 골라 주세요.">어떤 문의를 남기실래요?</Title>
              <div className="opt-list">{CATEGORIES.map((c) => (
                <button type="button" key={c.id} className="opt big" onClick={() => (c.types.length === 1 ? set({ catId: c.id, type: c.types[0].id }) : set({ catId: c.id }))}>
                  <b><span className="emo emo-i" aria-hidden="true"><CuteIcon name={c.icon} size={22} /></span>{c.label}</b><small>{c.sub}</small></button>))}</div>
            </>
          )}
          {!s.type && cat && (
            <>
              <Title sub={cat.label}>어떤 내용이세요?</Title>
              <div className="opt-list">{cat.types.map((t) => (
                <button type="button" key={t.id} className="opt big" onClick={() => set({ type: t.id })}><b>{t.label}</b><small>{t.sub}</small></button>))}</div>
            </>
          )}
          {s.type && !s.family && <FamilyStep title="어떤 제품에 대한 문의인가요?" emoji="📝" s={{ family: s.hl }} pick={(f) => set({ family: f, hl: f, model: null })} />}
          {s.type && s.family && !s.model && <ModelStep s={s} pick={(m) => setS((c) => enter2(applyModel({ ...c, model: m })))} />}
        </>
      )}

      {s.stage === 2 && (
        <>
          {pages.length > 1 && <div className="pnum" aria-label={`질문 ${s.page + 1} / ${pages.length}`}>질문 <b>{s.page + 1}</b> / {pages.length}</div>}
          <Title emoji="🔎" sub={route ? `${tInfo?.label.replace(/^[^\p{L}\p{N}]+\s*/u, '')} 문의에 필요한 정보예요.` : '이 문의는 내용을 보고 담당 부서가 유형을 정해요. 제품 모델만 알려 주세요.'}>필요한 정보를 알려 주세요</Title>
          {s.page === 0 && knownFields.length > 0 && (
            <div className="known"><b>✓ 이미 알고 있어요</b>
              {knownFields.map((f) => (
                <div key={f.key} data-field={f.key}>
                  {s.editing[f.key] ? (
                    <>{renderField(f)}
                      <div className="kdone"><button type="button" className="pbtn" onClick={() => set({ editing: { ...s.editing, [f.key]: false } })}>수정 완료</button></div></>
                  ) : (
                    <div className="krow"><span>{f.label}{s.auto[f.key] && <Auto />}</span>
                      <em>{confOf(f.key).type === 'file' ? `${(s.files[f.key] ?? []).length}개 파일` : s.vals[f.key]}</em>
                      <button type="button" onClick={() => set({ editing: { ...s.editing, [f.key]: true } })}>수정</button></div>
                  )}
                </div>
              ))}
            </div>
          )}
          {page.map((f) => renderField(f))}
          {page.length === 0 && knownFields.length === 0 && <p className="hintline">추가로 필요한 정보가 없어요.</p>}
          <div className="qnav"><button type="button" className="gbtn" onClick={back}>이전</button>
            <button type="button" className="pbtn" onClick={() => (s.page + 1 < pages.length ? set({ page: s.page + 1 }) : set({ stage: 3 }))}>다음</button></div>
        </>
      )}

      {s.stage === 3 && (
        <>
          <Title emoji="✍️" sub="상황과 원하는 도움을 편하게 적어 주세요.">문의 내용을 적어 주세요</Title>
          <div className={`fld${s.attempted && !s.subject.trim() ? ' err' : ''}`} data-field="__subject"><label><span>문의 제목{s.subjectAuto && s.subject && <Auto />}</span>
            <input className="qin" value={s.subject} placeholder="한 줄로 요약해 주세요" onChange={(e) => set({ subject: e.target.value, subjectAuto: false })} /></label>
            {s.attempted && !s.subject.trim() && <p className="ferr" role="alert">문의 제목을 입력해 주세요</p>}</div>
          <div className={`fld${s.attempted && !s.body.trim() ? ' err' : ''}`} data-field="__body"><label><span>상세 내용{s.bodyAuto && s.body && <Auto />}</span>
            <textarea className="qin" rows={6} value={s.body} placeholder={EXAMPLES[s.type] ?? ''} onChange={(e) => set({ body: e.target.value, bodyAuto: false })} /></label>
            {s.attempted && !s.body.trim() && <p className="ferr" role="alert">상세 내용을 입력해 주세요</p>}</div>
          <div className="cust"><b>연락처 <small>로그인한 고객 정보예요. 고칠 수 있어요.</small></b>
            {[['country', '국가', 'text'], ['company', '회사', 'text'], ['email', '이메일', 'text'], ['phone', '전화번호 (선택)', 'tel']].map(([k, l, t]) => (
              <div className={`fld${k === 'email' && s.attempted && !s.contact.email.trim() ? ' err' : ''}`} key={k} data-field={k === 'email' ? '__email' : k}><label><span>{l}{k !== 'phone' && !s.contactEdited[k] && s.contact[k] && <Auto />}</span>
                <input className="qin" type={t} value={s.contact[k]} onChange={(e) => set({ contact: { ...s.contact, [k]: e.target.value }, contactEdited: { ...s.contactEdited, [k]: true } })} /></label>
                {k === 'email' && s.attempted && !s.contact.email.trim() && <p className="ferr" role="alert">이메일을 입력해 주세요</p>}</div>
            ))}
            <div className="fld"><label><span>답변 언어{!s.contactEdited.lang && <Auto />}</span>
              <select className="qin" value={s.contact.lang} onChange={(e) => set({ contact: { ...s.contact, lang: e.target.value }, contactEdited: { ...s.contactEdited, lang: true } })}>
                {LANGUAGES.map(([c, n]) => <option key={c} value={c}>{n}</option>)}</select></label></div>
            <div className="fld"><label><span>선호 연락 수단 (선택)</span><small>접수 채널은 웹으로 자동 기록돼요. 이메일·전화는 연락 수단으로만 쓰여요.</small>
              <select className="qin" value={s.contact.pref} onChange={(e) => set({ contact: { ...s.contact, pref: e.target.value } })}>
                <option value="">상관없어요</option><option value="email">✉️ 이메일</option><option value="phone">📞 전화</option></select></label></div>
          </div>
          <div className="qnav"><button type="button" className="gbtn" onClick={back}>이전</button><button type="button" className="pbtn" onClick={() => set({ stage: 4 })}>다음</button></div>
        </>
      )}

      {s.stage === 4 && (
        <>
          <Title emoji="📋" sub="내용을 확인하고 직접 제출해 주세요. 자동으로 제출되지 않아요.">문의 내용을 확인해 주세요</Title>
          {allMissing.length > 0 && (
            <div className="missb" role="alert"><b>빠진 정보가 {allMissing.length}개 있어요</b>
              <ul>{allMissing.map((m) => <li key={m.key}>{m.label}{m.blocking && <i className="must">꼭 필요해요</i>}</li>)}</ul>
              <button type="button" className="pbtn" onClick={goMissing}>빠진 정보 입력하기</button></div>
          )}
          <div className="sumb"><div><b>제품</b><button type="button" onClick={() => set({ stage: 1, model: null })}>수정</button></div>
            <p>{s.family && getFamily(s.family).name} · {p ? `${p.name} (${p.code})` : '모델 미확인'}</p></div>
          <div className="sumb"><div><b>문의 유형</b><button type="button" onClick={() => set({ stage: 1, type: null, model: null })}>수정</button></div>
            <p>{TYPE_NAME[s.type]}{route && <small> · 담당 부서는 접수 후 시스템이 정해요 ({dept(route.primary)} 예정)</small>}</p></div>
          <div className="sumb"><div><b>문의 내용</b><button type="button" onClick={() => set({ stage: 3 })}>수정</button></div>
            <p><strong>{s.subject || '(제목 없음)'}</strong></p><p className="pre">{s.body || '(내용 없음)'}</p></div>
          <div className="sumb"><div><b>제출 자료</b><button type="button" onClick={() => set({ stage: 2, page: 0 })}>수정</button></div>
            <ul className="kv">{fields.map((f) => (
              <li key={f.key}><span>{f.label}</span><b>{confOf(f.key).type === 'file' ? ((s.files[f.key] ?? []).map((x) => x.file.name).join(', ') || '—') : (s.vals[f.key] || '—')}</b></li>))}</ul></div>
          <div className="sumb"><div><b>연락처</b><button type="button" onClick={() => set({ stage: 3 })}>수정</button></div>
            <p>{s.contact.company} · {s.contact.country}<br />{s.contact.email}{s.contact.phone && ` · ${s.contact.phone}`}<br />답변 언어: {LANGUAGES.find(([c]) => c === s.contact.lang)?.[1]}{s.contact.pref && ` · 선호: ${s.contact.pref === 'email' ? '이메일' : '전화'}`}</p></div>
          {s.chat && (
            <div className="sumb"><div><b>AI 상담 기록</b><button type="button" onClick={() => set({ chatOpen: !s.chatOpen })}>{s.chatOpen ? '접기' : '펼쳐보기'}</button></div>
              <p>상담 대화 기록과 참고한 문서 목록이 상담원에게 함께 전달돼요.</p>
              {s.chatOpen && (<><ul className="sumlist">{s.chat.messages.map((m, i) => <li key={i}>{m.role === 'user' ? '👤 고객' : '🤖 챗봇'}: {m.content}</li>)}</ul>
                <p className="hintline">참고한 문서: {s.chat.docs?.length ? s.chat.docs.join(', ') : '없음 (아직 연결된 챗봇 답변이 없어요)'}</p></>)}
            </div>
          )}
          {s.error && <div className="statusb" role="alert"><b>제출하지 못했어요</b><p>{s.error}</p></div>}
          <div className="qnav"><button type="button" className="gbtn" onClick={back} disabled={s.submitting}>이전</button>
            <button type="button" className="pbtn" disabled={allMissing.length > 0 || s.submitting} onClick={submit}>{s.submitting ? '제출하는 중…' : s.error ? '다시 제출하기' : '문의 제출하기'}</button></div>
        </>
      )}
      </div>
    </div>
  )
}
