import { useEffect, useMemo, useRef, useState } from 'react'
import { familyImage, getFamily, getProduct, issuePool, productImage } from '../lib/catalog.js'
import { STEPS, customer, dept } from '../lib/inquiry.js'
import { LEGACY_TYPE } from '../lib/legacy.js'
import {
  CATEGORIES, EXAMPLES, LANGUAGES, TYPE_NAME, confOf, errorText, fieldsFor, filled, humanSize, isDate, missingOf, routeOf, typeInfo,
} from '../lib/inquiryForm.js'
import CuteIcon from './CuteIcon.jsx'
import Attachments from './Attachments.jsx'
import { api } from '../../api/client'
import { newThreadRef, rememberInquiry } from '../../lib/myInquiries'
import MediaAttach from './MediaAttach.jsx'
import { FamilyStep, ModelStep, PathTags, Stepper, Title, UNKNOWN } from './common.jsx'

const LABELS = ['문의 선택', '필요한 정보', '내용 · 연락처', '확인 · 제출']
const Auto = () => <em className="autot">자동 입력</em>
const CUSTOM = '__custom'
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/

function start(draft = {}, lang) {
  const vals = { ...(draft.vals ?? {}) }
  const s = {
    stage: 1, hl: draft.family ?? null, type: draft.type ?? null, catId: draft.type ? typeInfo(draft.type)?.cat : null,
    family: draft.family ?? null, model: draft.model ?? null, vals, files: {}, codes: draft.codes ?? (vals.error_code ? [vals.error_code] : []), customCode: null,
    auto: Object.fromEntries(Object.keys(vals).map((k) => [k, true])),
    snap: null, page: 0, editing: {}, attempted: false, touched: {}, help: {}, focusKey: null,
    subject: draft.subject ?? '', body: draft.body ?? '', subjectAuto: !!draft.subject, bodyAuto: !!draft.body,
    // 국가·회사·이메일은 로그인한 고객 정보(시연용 값)로 채우고 고칠 수 있다. 답변 언어는 화면에서 고른 언어로 시작한다.
    contact: { country: customer.country_name, lang: LANGUAGES.some(([c]) => c === lang) ? lang : 'en', company: customer.company_masked, email: (customer.contact_email_masked ?? '').replace(/@\*+\.masked$/, '@example.com'), phone: '' },
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

// 제출 직후 접수 확인 화면: 문의번호 · 예상 소요시간 · 진행 단계 · 접수 내용 · 이후 진행 안내
const span = (h) => (h < 48 ? `${Math.round(h)}시간 이내` : `${Math.round(h / 24)}일 이내`)
const when = (iso, h, withTime) => new Date(new Date(iso).getTime() + h * 3600e3).toLocaleString('ko-KR', {
  month: 'long', day: 'numeric', weekday: 'short', ...(withTime ? { hour: 'numeric', minute: '2-digit' } : {}),
})
const Ico = ({ d }) => <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true"><path d={d} fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" /></svg>
const ICON = {
  reply: 'M4 5h16v10H8l-4 4V5z',
  done: 'M12 3l7 3v5c0 4.5-3 8.3-7 10-4-1.7-7-5.5-7-10V6l7-3zm-3 9l2 2 4-4',
  file: 'M14 3H7a2 2 0 00-2 2v14a2 2 0 002 2h10a2 2 0 002-2V8l-5-5zm0 0v5h5',
  team: 'M16 19v-1a4 4 0 00-4-4H7a4 4 0 00-4 4v1M9.5 10a3 3 0 100-6 3 3 0 000 6zM21 19v-1a4 4 0 00-3-3.9M15 4.1a3 3 0 010 5.8',
  globe: 'M12 21a9 9 0 100-18 9 9 0 000 18zM3 12h18M12 3c2.5 2.6 3.8 5.6 3.8 9s-1.3 6.4-3.8 9c-2.5-2.6-3.8-5.6-3.8-9S9.5 5.6 12 3z',
  mail: 'M4 6h16v12H4zM4 7l8 6 8-6',
}

function Receipt({ s, fields, route, onExit, onOpenMine }) {
  const t = s.done
  const [copied, setCopied] = useState(false)
  const [open, setOpen] = useState(false)
  const copy = async () => {
    try { await navigator.clipboard.writeText(t.ticket_id); setCopied(true); setTimeout(() => setCopied(false), 1800) } catch { /* 복사 권한이 없으면 번호를 직접 보고 적는다 */ }
  }
  const fam = s.family ? getFamily(s.family) : null
  const files = Object.values(s.files).flat()
  const [previews, setPreviews] = useState([])
  useEffect(() => {
    const p = files.map((x) => ({ name: x.file.name, size: x.file.size, type: x.file.type, url: URL.createObjectURL(x.file) }))
    setPreviews(p)
    return () => p.forEach((x) => URL.revokeObjectURL(x.url))
  }, [s.files]) // eslint-disable-line
  // 고객이 채운 항목 (제품 모델은 위 제품 카드에, 파일은 첨부에 따로 보여 준다)
  const details = fields.filter((f) => f.key !== 'product_model' && confOf(f.key).type !== 'file' && filled(f, s.vals, s.files))
  const first = Number(t.sla_first_response_target_h) || 0, done = Number(t.sla_resolution_target_h) || 0
  const longBody = t.inquiry_body.length > 160 || t.inquiry_body.split('\n').length > 4
  return (
    <div className="flow inquire">
      <div className="rcpt">
        <header className="rcpt-hero">
          <span className="rcpt-check" aria-hidden="true"><svg viewBox="0 0 24 24" width="28" height="28"><path d="M5 12.5l4.5 4.5L19 7.5" fill="none" stroke="currentColor" strokeWidth="2.8" strokeLinecap="round" strokeLinejoin="round" /></svg></span>
          <h2>문의가 정상적으로 접수되었습니다</h2>
          <p>담당 부서에서 내용을 확인한 뒤 순서대로 답변드릴게요.</p>
          <div className="rcpt-no">
            <div><small>문의번호</small><b>{t.ticket_id}</b></div>
            <button type="button" onClick={copy}>{copied ? '복사됐어요 ✓' : '번호 복사'}</button>
          </div>
          <small className="rcpt-at">접수 {when(t.received_at_utc, 0, true)}</small>
        </header>

        <section className="rcpt-eta" aria-label="예상 소요시간">
          {first > 0 ? (
            <>
              <div className="eta"><span className="eta-i"><Ico d={ICON.reply} /></span>
                <small>첫 답변 예상</small><b>{span(first)}</b><span>{when(t.received_at_utc, first, true)}까지</span></div>
              <div className="eta"><span className="eta-i"><Ico d={ICON.done} /></span>
                <small>처리 완료 목표</small><b>{span(done)}</b><span>{when(t.received_at_utc, done, false)}까지</span></div>
              <p className="eta-note">추가 정보를 요청드린 경우, 회신을 기다리는 시간은 소요시간에서 빠져요.</p>
            </>
          ) : <p className="eta-note">예상 소요시간은 담당자가 내용을 확인한 뒤 메일로 안내드려요.</p>}
        </section>

        <ol className="rcpt-steps" aria-label="처리 단계">
          {STEPS.map((x) => (
            <li key={x.n} className={x.n === 1 ? 'done' : x.n === 2 ? 'next' : ''}>
              <span className="dot">{x.n === 1 ? '✓' : x.n}</span>
              <b>{x.label}</b>
              <small>{x.n === 1 ? '방금 전' : x.n === 2 ? (first ? `${span(first)} 시작` : '담당자 확인 대기') : '답변 메일 발송'}</small>
            </li>
          ))}
        </ol>

        <section className="rcpt-card">
          <h3>접수 내용</h3>
          {fam && (
            <div className="rcpt-prod">
              {(productImage(t.product_code) ?? familyImage(fam.id)) && <img src={productImage(t.product_code) ?? familyImage(fam.id)} alt="" />}
              <div><small>{fam.name}</small><b>{t.product_code ? t.product_name : '모델 미확인'}</b>{t.product_code && <code>{t.product_code}</code>}</div>
              <span className="rcpt-type">{TYPE_NAME[s.type]}</span>
            </div>
          )}
          <div className="rcpt-msg">
            <b>{t.inquiry_subject}</b>
            <p className={longBody && !open ? 'clamp' : ''}>{t.inquiry_body}</p>
            {longBody && <button type="button" onClick={() => setOpen(!open)}>{open ? '접기' : '전체 보기'}</button>}
          </div>
          {details.length > 0 && (
            <dl className="rcpt-fields">{details.map((f) => <div key={f.key}><dt>{f.label}</dt><dd>{s.vals[f.key]}</dd></div>)}</dl>
          )}
          {files.length > 0 && (
            <div className="sub-att"><h5>첨부 파일 <em>{files.length}</em></h5><Attachments items={previews} />
              {t.upload_failed?.length > 0 && <p className="ferr" role="alert">{t.upload_failed.join(', ')} 파일을 올리지 못했어요. 내 문의에서 이어서 남겨 주세요.</p>}</div>
          )}
          <ul className="rcpt-meta">
            <li><Ico d={ICON.team} /><small>담당 부서</small><span>{route ? `${dept(route.primary)} (배정 예정)` : '확인 후 배정'}</span></li>
            <li><Ico d={ICON.globe} /><small>답변 언어</small><span>{LANGUAGES.find(([c]) => c === t.language)?.[1] ?? t.language}</span></li>
            <li><Ico d={ICON.mail} /><small>알림 메일</small><span>{t.notify_email}</span></li>
          </ul>
        </section>

        <section className="rcpt-card">
          <h3>앞으로 이렇게 진행돼요</h3>
          <ol className="rcpt-next">
            <li><b>담당 부서 배정 · 검토</b><span>문의 유형과 제품을 기준으로 담당 부서가 정해지고, 담당자가 내용을 검토해요.</span></li>
            <li><b>추가 정보 요청 <em>필요한 경우</em></b><span>확인에 필요한 정보가 있으면 메일로 요청드려요. 그 메일에 회신하시면 같은 문의로 이어서 처리돼요.</span></li>
            <li><b>답변 · 처리 완료</b><span>처리가 끝나면 <b>{t.notify_email}</b>로 결과를 보내 드려요.</span></li>
          </ol>
        </section>

        <aside className="rcpt-note">
          <ul>
            <li>문의번호를 메모해 두시면 문의 내역 확인과 상담이 빨라져요.</li>
            <li>같은 내용으로 다시 접수하시면 처리가 늦어질 수 있어요. 내용을 보태려면 내 문의에서 이어서 남겨 주세요.</li>
          </ul>
        </aside>

        <div className="rcpt-actions">
          <button type="button" className="gbtn" onClick={onExit}>처음 화면으로</button>
          <button type="button" className="pbtn" onClick={() => onOpenMine(t.ticket_id)}>내 문의에서 확인하기</button>
        </div>
      </div>
    </div>
  )
}

export default function Inquire({ draft, lang, onSubmitted, onOpenMine, onExit, onContext }) {
  const [s, setS] = useState(() => start(draft, lang))
  const set = (p) => setS((c) => ({ ...c, ...(typeof p === 'function' ? p(c) : p) }))
  const fields = useMemo(() => (s.type && s.family ? fieldsFor(s.type, s.family) : []), [s.type, s.family])
  const missing = useMemo(() => missingOf(fields, s.vals, s.files), [fields, s.vals, s.files])
  const pages = useMemo(() => (s.snap ? pagesOf(fields, s.snap) : [[]]), [fields, s.snap])
  const p = s.model && s.model !== UNKNOWN ? getProduct(s.model) : null
  const route = s.type && s.type !== 'USAGE' && s.family ? routeOf(s.family, s.type) : null

  // 내용·연락처 필수 (제목 · 상세 내용 · 이메일)
  const emailBad = !!s.contact.email.trim() && !EMAIL_RE.test(s.contact.email.trim())
  const contentMissing = [!s.subject.trim() && { key: '__subject', label: '문의 제목', stage: 3 }, !s.body.trim() && { key: '__body', label: '상세 내용', stage: 3 }, (!s.contact.email.trim() || emailBad) && { key: '__email', label: emailBad ? '이메일 형식' : '이메일', stage: 3 }].filter(Boolean)
  const allMissing = [...missing.map((f) => ({ key: f.key, label: f.label, stage: 2, blocking: f.blocking })), ...contentMissing]

  useEffect(() => {
    // 단종·호환 문의는 모델이 아니라 제품군 단위로 상담하므로 모델 줄을 넘기지 않는다 (같은 제품군의 모델 상담 카드와 섞이지 않게)
    onContext([...(s.family ? [`제품군: ${getFamily(s.family).name}`] : []), ...(p && s.type !== LEGACY_TYPE ? [`모델: ${p.name} (${p.code})`] : []), ...(s.type ? [`문의 유형: ${TYPE_NAME[s.type]}`] : []), `작성 단계: ${LABELS[s.stage - 1]}`])
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
    const cf = confOf(f.key), val = s.vals[f.key] ?? '', show = f.blocking && (s.attempted || s.touched[f.key]) && !filled(f, s.vals, s.files)
    const dateOk = cf.type !== 'date' || !val || isDate(val)
    return (
      <div className={`fld${show ? ' err' : ''}`} key={f.key} data-field={f.key}>
        <label>
          <span>{!cf.media && f.label}{f.blocking && <i className="must">꼭 필요해요</i>}{s.auto[f.key] && val && <Auto />}</span>
          {cf.help && <small>{cf.help}</small>}
          {cf.media ? <MediaAttach value={s.files[f.key] ?? []} kinds={['photo', 'video', 'sound']} title="고장 모습을 보여 주세요" onChange={(fn) => set((c) => ({ files: { ...c.files, [f.key]: fn(c.files[f.key] ?? []) } }))} />
            : cf.type === 'file' ? <Dropzone f={f} files={s.files[f.key]} error={show} onTouch={() => touch(f.key)} setFiles={(l) => set((c) => ({ files: { ...c.files, [f.key]: l } }))} />
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
      const now = new Date()
      const provided = fields.filter((f) => filled(f, s.vals, s.files))
      const fileNames = (f) => (s.files[f.key] ?? []).map((x) => x.file.name).join(', ')
      const valueOf = (f) => (confOf(f.key).type === 'file' ? fileNames(f) : String(s.vals[f.key] ?? ''))
      const details = provided.map((f) => `- ${f.label}: ${confOf(f.key).type === 'file' ? (s.files[f.key] ?? []).map((x) => `[attachment: ${x.file.name}]`).join(' ') : s.vals[f.key]}`).join('\n')
      const c = s.contact
      const contactLine = [c.country && `국가: ${c.country}`, c.company && `회사: ${c.company}`, c.email && `이메일: ${c.email}`, c.phone && `전화: ${c.phone}`].filter(Boolean).join(' / ')
      const threadRef = newThreadRef() // 추가정보 요청에 회신할 때 같은 문의로 이어진다
      const subject = s.subject.trim()
      const sent = await api.createInquiry({
        channel: 'WEB_FORM',
        customer_id: customer.customer_id, // 시연 프로필의 고객. 회사명·이메일로 추측하지 않는다.
        // 서버 Category 에 없는 유형(사용 방법 · 단종 호환 대체)은 비워서 보내고, 서버가 내용을 보고 분류한다
        category: s.type === 'USAGE' || s.type === LEGACY_TYPE ? null : s.type,
        product_code: p?.code ?? null,
        subject,
        body: `${s.type === LEGACY_TYPE ? '[단종·호환·대체 문의]\n' : ''}${s.body.trim()}${details ? `\n\nDetails:\n${details}` : ''}${contactLine ? `\n\nContact: ${contactLine}` : ''}`,
        provided_fields: Object.fromEntries(provided.map((f) => [f.key, valueOf(f)])),
        thread_ref: threadRef,
        language: c.lang || null,
      })
      rememberInquiry({ ticket_id: sent.ticket_id, thread_ref: threadRef, subject, notify_email: s.contact.email.trim(), category_code: s.type, product_code: p?.code })
      // 첨부는 문의번호가 나온 뒤 하나씩 올린다. 못 올린 파일은 접수 화면에 알린다 (문의 자체는 접수됐다)
      const toUpload = provided.flatMap((f) => (confOf(f.key).type === 'file' ? (s.files[f.key] ?? []).map((x) => x.file) : []))
      const uploaded = await Promise.all(toUpload.map((file) => api.uploadAttachment(sent.ticket_id, file).then(() => null, () => file.name)))
      const uploadFailed = uploaded.filter(Boolean)
      const t = {
        demoSubmit: true, notify_email: s.contact.email.trim(), ticket_id: sent.ticket_id, received_at_utc: (sent.received_at ?? now.toISOString()).slice(0, 19) + 'Z', channel: 'WEB_FORM', language: c.lang, body_language: c.lang, customer_tier: customer.tier,
        product_code: p?.code ?? '', product_name: p?.name ?? '(모델 미확인)', product_family: s.family, category_code: s.type === 'USAGE' ? '' : s.type,
        inquiry_subject: subject, inquiry_body: s.body.trim(), error_code_reported: '', fw_version_reported: '', priority: '',
        assigned_dept: route?.primary ?? 'GCS_L1', escalated: 'N', escalated_to: '', escalation_reason: '', required_info: fields.map((f) => f.key).join(';'),
        provided_info: provided.map((f) => f.key).join(';'), missing_info: '', missing_blocking_info: '', info_request_sent: 'N', info_request_message: '', status: 'NEW',
        first_response_at_utc: '', resolved_at_utc: '', first_response_hours: '', sla_first_response_target_h: sent.first_response_target_h ?? '', sla_resolution_target_h: sent.resolution_target_h ?? '', sla_elapsed_hours: '',
        sla_first_response_status: '', sla_resolution_status: '', final_action: '', final_reply: '', rma_no: '', reference_doc_id: '', reference_section: '',
        thread_from: draft?.fromTicket ?? '', upload_failed: uploadFailed,
      }
      onSubmitted(t)
      set({ submitting: false, done: t })
    } catch (e) {
      set({ submitting: false, error: '문의를 보내지 못했어요. 작성한 내용은 그대로 남아 있어요. 잠시 뒤 다시 시도해 주세요.' })
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

  if (s.done) return <Receipt s={s} fields={fields} route={route} onExit={onExit} onOpenMine={onOpenMine} />

  const tInfo = s.type ? typeInfo(s.type) : null
  const cat = CATEGORIES.find((c) => c.id === s.catId)
  const page = pages[Math.min(s.page, pages.length - 1)] ?? []
  const knownFields = s.snap ? fields.filter((f) => s.snap.has(f.key)) : []
  // 이미 알고 있는 값 중 목록에서 바로 고를 수 있는 것: 문의 유형, 제품 모델, 에러 코드·증상
  const changeType = (type) => setS((c) => enter2({ ...c, type, catId: typeInfo(type)?.cat ?? c.catId, editing: {} }))
  const picks = {}
  if (s.family) {
    const models = getFamily(s.family).models.map((c) => [c, `${getProduct(c).name} (${c})`])
    const cur = p ? p.code : s.vals.product_model ?? ''
    picks.product_model = {
      value: cur, options: p ? models : [[cur, cur], ...models],
      pick: (code) => setS((c) => enter2(applyModel({ ...c, model: code, vals: { ...c.vals, product_model: '' }, auto: { ...c.auto, product_model: false }, editing: {} }))),
    }
  }
  // 에러 코드·증상은 여러 개 고를 수 있다. 목록에서 더하거나 직접 적어 더하고, 고른 것은 하나씩 뺄 수 있다.
  const pool = s.family ? new Map(issuePool(s.family, p?.code).map((x) => [x.code || x.symptom, x.code ? `${x.code} · ${x.symptom}` : x.symptom])) : new Map()
  const setCodes = (codes) => set((c) => ({ codes, vals: { ...c.vals, error_code: codes.join(', ') }, auto: { ...c.auto, error_code: false }, customCode: null }))
  const addCode = (v) => { const x = v.trim(); if (x && !s.codes.includes(x)) setCodes([...s.codes, x]); else set({ customCode: null }) }

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
          {s.type && !s.family && <FamilyStep title="어떤 제품에 대한 문의인가요?" emoji="📝" s={{ family: s.hl }} pick={(f) => set({ family: f, hl: f, model: null })} pickModel={(fam, m) => setS((c) => enter2(applyModel({ ...c, family: fam, hl: fam, model: m })))} />}
          {s.type && s.family && !s.model && <ModelStep s={s} pick={(m) => setS((c) => enter2(applyModel({ ...c, model: m })))} />}
        </>
      )}

      {s.stage === 2 && (
        <>
          {pages.length > 1 && <div className="pnum" aria-label={`질문 ${s.page + 1} / ${pages.length}`}>질문 <b>{s.page + 1}</b> / {pages.length}</div>}
          <Title emoji="🔎" sub={route ? undefined : '이 문의는 내용을 보고 담당 부서가 유형을 정해요. 제품 모델만 알려 주세요.'}>필요한 정보를 알려 주세요</Title>
          {s.page === 0 && (knownFields.length > 0 || s.type) && (
            <div className="known"><b>✓ 이미 알고 있어요</b>
              {/* 화면 중간에서 문의서로 넘어오면 유형을 고르는 단계를 건너뛴다 — 정해진 유형을 여기서 보여 주고 고칠 수 있게 한다 */}
              {s.type && (
                <>
                  {/* 문의 유형은 고객용 4가지 중에서만 고른다. 세부 내용이 여러 개인 유형만 세부 내용을 한 줄 더 보여 준다 */}
                  <div className="krow"><span>문의 유형</span>
                    <select className="ksel" aria-label="문의 유형" value={typeInfo(s.type)?.cat ?? ''} onChange={(e) => changeType(CATEGORIES.find((c) => c.id === e.target.value).types[0].id)}>
                      {CATEGORIES.map((c) => <option key={c.id} value={c.id}>{c.label}</option>)}
                    </select></div>
                  {(CATEGORIES.find((c) => c.id === typeInfo(s.type)?.cat)?.types.length ?? 0) > 1 && (
                    <div className="krow"><span>세부 내용</span>
                      <select className="ksel" aria-label="세부 내용" value={s.type} onChange={(e) => changeType(e.target.value)}>
                        {CATEGORIES.find((c) => c.id === typeInfo(s.type).cat).types.map((t) => <option key={t.id} value={t.id}>{t.label}</option>)}
                      </select></div>
                  )}
                </>
              )}
              {knownFields.map((f) => (
                <div key={f.key} data-field={f.key}>
                  {f.key === 'error_code' ? (
                    <div className="kcodes">
                      <div className="krow"><span>{f.label}{s.auto.error_code && <Auto />}{s.codes.length > 0 && <em className="ccount">{s.codes.length}개 선택</em>}</span>
                        <select className="ksel" aria-label={`${f.label} 추가`} value="" onChange={(e) => (e.target.value === CUSTOM ? set({ customCode: '' }) : addCode(e.target.value))}>
                          <option value="">추가하기</option>
                          {[...pool].filter(([v]) => !s.codes.includes(v)).map(([v, label]) => <option key={v} value={v}>{label}</option>)}
                          <option value={CUSTOM}>직접 적기</option>
                        </select></div>
                      {s.codes.length > 0 && (
                        <ul className="cchips" aria-label="고른 에러 코드·증상">{s.codes.map((c) => (
                          <li key={c}><span>{pool.get(c) ?? c}</span><button type="button" aria-label={`${c} 빼기`} onClick={() => setCodes(s.codes.filter((x) => x !== c))}>×</button></li>))}</ul>
                      )}
                      {s.customCode !== null && (
                        <div className="ccustom"><input className="qin" autoFocus value={s.customCode} placeholder="예: E.OC, 또는 &quot;가속할 때 멈춰요&quot;" aria-label="에러 코드·증상 직접 입력"
                          onChange={(e) => set({ customCode: e.target.value })} onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); addCode(s.customCode) } }} />
                          <button type="button" className="pbtn" onClick={() => addCode(s.customCode)}>추가</button>
                          <button type="button" className="gbtn" onClick={() => set({ customCode: null })}>취소</button></div>
                      )}
                    </div>
                  ) : s.editing[f.key] ? (
                    <>{renderField(f)}
                      <div className="kdone"><button type="button" className="pbtn" onClick={() => set({ editing: { ...s.editing, [f.key]: false } })}>수정 완료</button></div></>
                  ) : (
                    picks[f.key] ? (
                      // 모델·에러 코드는 목록에서 바로 고친다. 목록에 없으면 "직접 적기"로 입력칸을 연다.
                      <div className="krow"><span>{f.label}{s.auto[f.key] && <Auto />}</span>
                        <select className="ksel" aria-label={f.label} value={picks[f.key].value} onChange={(e) => (e.target.value === CUSTOM ? set({ editing: { ...s.editing, [f.key]: true } }) : picks[f.key].pick(e.target.value))}>
                          {picks[f.key].options.map(([v, label]) => <option key={v} value={v}>{label}</option>)}
                          <option value={CUSTOM}>목록에 없어요 · 직접 적기</option>
                        </select></div>
                    ) : (
                    <div className="krow"><span>{f.label}{s.auto[f.key] && <Auto />}</span>
                      <em>{confOf(f.key).type === 'file' ? `${(s.files[f.key] ?? []).length}개 파일` : s.vals[f.key]}</em>
                      <button type="button" onClick={() => set({ editing: { ...s.editing, [f.key]: true } })}>수정</button></div>
                    )
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
          <Title emoji="✍️">문의 내용을 적어 주세요</Title>
          <div className={`fld${s.attempted && !s.subject.trim() ? ' err' : ''}`} data-field="__subject"><label><span>문의 제목{s.subjectAuto && s.subject && <Auto />}</span>
            <input className="qin" value={s.subject} placeholder="한 줄로 요약해 주세요" onChange={(e) => set({ subject: e.target.value, subjectAuto: false })} /></label>
            {s.attempted && !s.subject.trim() && <p className="ferr" role="alert">문의 제목을 입력해 주세요</p>}</div>
          <div className={`fld${s.attempted && !s.body.trim() ? ' err' : ''}`} data-field="__body"><label><span>상세 내용{s.bodyAuto && s.body && <Auto />}</span>
            <textarea className="qin" rows={6} value={s.body} placeholder={EXAMPLES[s.type] ?? ''} onChange={(e) => set({ body: e.target.value, bodyAuto: false })} /></label>
            {s.attempted && !s.body.trim() && <p className="ferr" role="alert">상세 내용을 입력해 주세요</p>}</div>
          <div className="cust"><b>연락처</b>
            {[['country', '국가', 'text'], ['company', '회사', 'text'], ['email', '이메일', 'text'], ['phone', '전화번호 (선택)', 'tel']].map(([k, l, t]) => (
              <div className={`fld${k === 'email' && ((s.attempted && !s.contact.email.trim()) || ((s.attempted || s.touched.__email) && emailBad)) ? ' err' : ''}`} key={k} data-field={k === 'email' ? '__email' : k}><label><span>{l}{k !== 'phone' && !s.contactEdited[k] && s.contact[k] && <Auto />}</span>
                <input className="qin" type={t} placeholder={k === 'phone' ? '예: +82 10-1234-5678' : undefined} value={s.contact[k]} onChange={(e) => set({ contact: { ...s.contact, [k]: e.target.value }, contactEdited: { ...s.contactEdited, [k]: true } })} onBlur={k === 'email' ? () => touch('__email') : undefined} aria-invalid={k === 'email' && emailBad ? true : undefined} /></label>
                {k === 'email' && s.attempted && !s.contact.email.trim() && <p className="ferr" role="alert">이메일을 입력해 주세요</p>}
                {k === 'email' && (s.attempted || s.touched.__email) && emailBad && <p className="ferr" role="alert">잘못된 형식입니다. 예: name@company.com</p>}</div>
            ))}
            <div className="fld"><label><span>답변 언어{!s.contactEdited.lang && <Auto />}</span>
              <select className="qin" value={s.contact.lang} onChange={(e) => set({ contact: { ...s.contact, lang: e.target.value }, contactEdited: { ...s.contactEdited, lang: true } })}>
                {LANGUAGES.map(([c, n]) => <option key={c} value={c} lang={c}>{n}</option>)}</select></label></div>
          </div>
          <div className="qnav"><button type="button" className="gbtn" onClick={back}>이전</button><button type="button" className="pbtn" onClick={() => (emailBad ? set({ attempted: true, touched: { ...s.touched, __email: true }, focusKey: '__email' }) : set({ stage: 4 }))}>다음</button></div>
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
            <p>{[s.contact.company, s.contact.country].filter(Boolean).join(' · ') || '(회사·국가 미입력)'}<br />{s.contact.email}{s.contact.phone && ` · ${s.contact.phone}`}<br />답변 언어: {LANGUAGES.find(([c]) => c === s.contact.lang)?.[1]}</p></div>
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
