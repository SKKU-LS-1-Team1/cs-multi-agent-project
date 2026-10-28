import { useMemo, useState } from 'react'
import {
  CHANNEL, CHANNEL_SHORT, ESC_REASON, FILTERS, FINAL_ACTION, STATUS, STEPS, attachmentsOf, dept, fieldLabel, fmtTime, pauseRule, split, tickets, titleOf,
} from '../lib/inquiry.js'

function Long({ text, lines = 5 }) {
  const [open, setOpen] = useState(false)
  const long = text.length > 220 || text.split('\n').length > lines
  return (
    <div className="long">
      <p className={long && !open ? 'clamp' : ''}>{text}</p>
      {long && <button type="button" className="link" onClick={() => setOpen(!open)}>{open ? '접기' : '전체 보기'}</button>}
    </div>
  )
}

function Progress({ t }) {
  const st = STATUS[t.status]
  return (
    <div className="prog3" key={t.ticket_id + t.status}>
      <ol>
        {STEPS.map((s) => {
          const state = s.n < st.stage || (s.n === 3 && st.stage === 3) ? 'done' : s.n === st.stage ? 'now' : 'later'
          return (
            <li key={s.n} className={state} aria-current={state === 'now' ? 'step' : undefined}>
              <span className="c">{state === 'done' ? '✓' : s.n}</span>
              <span className="ic" aria-hidden="true">{s.icon}</span>
              <b>{s.label}</b>
            </li>
          )
        })}
      </ol>
      {t.status === 'ESCALATED' && <div className={`stat ${st.kind}`}><span aria-hidden="true">{st.emoji}</span><b>{st.label}</b></div>}
    </div>
  )
}

function Times({ t }) {
  const rows = [
    t.received_at_utc && ['1 접수', fmtTime(t.received_at_utc)],
    t.first_response_at_utc && ['2 첫 응답', fmtTime(t.first_response_at_utc)],
    t.resolved_at_utc && ['3 처리 완료', fmtTime(t.resolved_at_utc)],
  ].filter(Boolean)
  if (!rows.length) return null
  return <ul className="times">{rows.map(([k, v]) => <li key={k}><span>{k}</span><b>{v}</b></li>)}</ul>
}

function Sla({ t }) {
  if (t.demoSubmit) return null
  const fr = Number(t.sla_first_response_target_h), rs = Number(t.sla_resolution_target_h)
  const MET = { MET: '목표 안에 응답했어요', BREACHED: '목표보다 늦게 응답했어요' }
  return (
    <div className="blk"><h4>⏱️ 응답 시간 안내</h4>
      <ul className="kv">
        <li><span>응답 목표</span><b>첫 응답 {fr}시간 · 처리 {rs}시간</b></li>
        {t.first_response_hours && <li><span>실제 첫 응답</span><b>{t.first_response_hours}시간 ({MET[t.sla_first_response_status] ?? t.sla_first_response_status})</b></li>}
        <li><span>확정 처리 예정일</span><b>기록 없음</b></li>
      </ul>
      <p className="hintline">응답 목표는 접수 시점의 기준일 뿐, 처리 완료일을 약속하는 게 아니에요.</p>
      {t.status === 'WAITING_CUSTOMER' && <p className="pause">⏸️ 추가 정보를 보내 주실 때까지는 처리 시간 계산이 멈출 수 있어요. (정책: {pauseRule})</p>}
    </div>
  )
}

function Sheet({ kind, t, onClose, onSend }) {
  const miss = split(t.missing_info)
  const [vals, setVals] = useState({})
  const [text, setText] = useState(kind === 'again' ? titleOf(t) : '')
  const [done, setDone] = useState(false)
  const [copied, setCopied] = useState(false)
  const lines = kind === 'info'
    ? [`[추가 정보 보내기 초안] 문의번호 ${t.ticket_id}`, ...miss.map((k) => `${fieldLabel(k)}: ${vals[k] || '(미입력)'}`)]
    : kind === 'more' ? [`[추가 내용 초안] 문의번호 ${t.ticket_id}`, text || '(미입력)']
      : [`[같은 문제로 다시 문의 — 새 문의 초안] 이전 문의번호: ${t.ticket_id}`, `제품: ${t.product_name} (${t.product_code})`, `내용: ${text || '(미입력)'}`]
  const title = { info: '📨 추가 정보 보내기', more: '✍️ 추가 내용 남기기', again: '🔁 같은 문제로 다시 문의' }[kind]
  const ok = kind === 'info' ? miss.some((k) => vals[k]?.trim()) : text.trim().length > 0
  return (
    <div className="sheet" role="dialog" aria-label={title}>
      <div className="sh-h"><b>{title}</b><button type="button" onClick={onClose} aria-label="닫기">✕</button></div>
      {!done ? (
        <>
          {kind === 'again' && <p className="hintline">이 문의({t.ticket_id})의 번호와 제품 정보를 이어받지만, <strong>새로운 문의</strong>로 접수돼요.<br />제품: {t.product_name} ({t.product_code})</p>}
          {kind === 'info' && (
            <>
              {split(t.provided_info).length > 0 && <p className="hintline">이미 보내 주신 {split(t.provided_info).map(fieldLabel).join(', ')}은(는) 다시 쓰지 않아도 돼요.</p>}
              {miss.map((k) => (
                <label key={k}><span>{fieldLabel(k)}{split(t.missing_blocking_info).includes(k) && <i>꼭 필요해요</i>}</span>
                  <input value={vals[k] ?? ''} onChange={(e) => setVals({ ...vals, [k]: e.target.value })} /></label>
              ))}
            </>
          )}
          {kind !== 'info' && <textarea className="qin" rows={4} value={text} onChange={(e) => setText(e.target.value)} placeholder={kind === 'more' ? '추가로 알려 주실 내용을 적어 주세요' : '문의 내용을 적어 주세요'} aria-label="내용" />}
          <div className="qnav"><button type="button" className="gbtn" onClick={onClose}>닫기</button>
            <button type="button" className="pbtn" disabled={!ok} onClick={() => setDone(true)}>{kind === 'info' ? '추가 정보 보내기' : kind === 'more' ? '추가 내용 남기기' : '다시 문의하기'}</button></div>
        </>
      ) : (
        <>
          <div className="statusb"><b>⚠️ 아직 보내지 않았어요</b><p>접수·발송 기능이 연결되어 있지 않아서 저장도 전송도 되지 않았어요. 문의 상태와 기록도 바뀌지 않았어요. 정리한 내용만 AI 상담으로 보내거나 복사할 수 있어요.</p></div>
          <ul className="sumlist">{lines.map((l) => <li key={l}>{l}</li>)}</ul>
          <div className="qnav"><button type="button" className="gbtn" onClick={() => setDone(false)}>수정</button>
            <button type="button" className="gbtn" onClick={async () => { try { await navigator.clipboard.writeText(lines.join('\n')); setCopied(true) } catch { setCopied(false) } }}>{copied ? '복사했어요 ✓' : '내용 복사'}</button>
            <button type="button" className="pbtn" onClick={() => onSend(lines.join('\n'))}>AI 상담으로 내용 보내기</button></div>
        </>
      )}
    </div>
  )
}

function Detail({ t, onBack, onSend, onAgain }) {
  const st = STATUS[t.status]
  const ch = CHANNEL[t.channel]
  const miss = split(t.missing_info), blocking = split(t.missing_blocking_info), prov = split(t.provided_info)
  const [sheet, setSheet] = useState(null)
  const att = attachmentsOf(t)
  const done = st.kind === 'done'
  const phone = t.channel === 'PHONE'

  return (
    <div className="inqd">
      <div className="fhead"><button type="button" className="backbtn" onClick={onBack}>← 내 문의</button></div>
      <p className="inq-id">문의번호 {t.ticket_id}</p>
      <h2 className="inq-title">{titleOf(t)}</h2>


      <Progress t={t} />
      <Times t={t} />

      {st.kind === 'need' ? (
        <div className="needb">
          <b>✋ 추가 정보 필요</b>
          <ul>{miss.map((k) => <li key={k}>{fieldLabel(k)}{blocking.includes(k) && <i>꼭 필요해요</i>}</li>)}</ul>
          {prov.length > 0 && <p className="done-info">✓ 이미 보내 주신 {prov.map(fieldLabel).join(', ')}은(는) 다시 쓰지 않아도 돼요.</p>}
          <button type="button" className="pbtn" onClick={() => setSheet('info')}>추가 정보 보내기</button>
        </div>
      ) : (
        <div className="qnav inq-act">
          {done ? <button type="button" className="pbtn" onClick={() => onAgain(t)}>같은 문제로 다시 문의</button>
            : <button type="button" className="pbtn" onClick={() => setSheet('more')}>추가 내용 남기기</button>}
        </div>
      )}

      {sheet && <Sheet kind={sheet} t={t} onClose={() => setSheet(null)} onSend={onSend} key={sheet} />}

      <div className="blk"><h4>📋 접수한 내용</h4>
        <ul className="kv">
          <li><span>제품 · 모델</span><b>{t.product_name} · {t.product_code}</b></li>
          <li><span>접수 채널</span><b>{ch.emoji} {ch.label}</b></li>
          {t.error_code_reported && <li><span>에러 코드</span><b>{t.error_code_reported}</b></li>}
        </ul>
        {phone && <p className="phone-note">📞 전화로 접수한 <strong>상담 메모</strong>예요. 통화 녹음이나 전체 대화 내용은 기록에 없어요.</p>}
        <Long text={t.inquiry_body} />
        {att.length > 0 && <p className="atts">{att.map((a) => <span key={a}>📎 {a}<em> (파일 없음 · 이름만 기록됐어요)</em></span>)}</p>}
      </div>

      <div className="blk"><h4>🏢 담당 부서</h4>
        <ul className="kv">
          <li><span>담당</span><b>{dept(t.assigned_dept)}</b></li>
          {t.escalated === 'Y' && <li><span>전문 부서 확인</span><b>{dept(t.escalated_to)}{t.escalation_reason ? ` · ${ESC_REASON[t.escalation_reason] ?? t.escalation_reason}` : ''}</b></li>}
        </ul>
      </div>

      {t.final_reply && <div className="blk"><h4>💬 답변</h4><Long text={t.final_reply} /></div>}

      {done && (t.final_action || t.rma_no || t.reference_doc_id || t.resolved_at_utc) && (
        <div className="blk res"><h4>✅ 처리 결과</h4>
          <ul className="kv">
            {t.final_action && <li><span>조치</span><b>{FINAL_ACTION[t.final_action] ?? t.final_action}</b></li>}
            {t.rma_no && <li><span>RMA 번호</span><b>{t.rma_no}</b></li>}
            {t.reference_doc_id && <li><span>참고 문서</span><b>{t.reference_doc_id}{t.reference_section ? ` §${t.reference_section}` : ''}</b></li>}
            {t.resolved_at_utc && <li><span>처리 완료 시각</span><b>{fmtTime(t.resolved_at_utc)}</b></li>}
          </ul>
        </div>
      )}

      <Sla t={t} />

    </div>
  )
}

export default function Inquiries({ onNew, onSend, onAgain, extra = [], initialOpen = null }) {
  const [filter, setFilter] = useState('all')
  const [openId, setOpenId] = useState(initialOpen)
  const all = useMemo(() => [...tickets].sort((a, b) => b.received_at_utc.localeCompare(a.received_at_utc)), [])
  const list = [...[...extra].reverse(), ...all]
  const fn = FILTERS.find((f) => f[0] === filter)[2]
  const shown = list.filter(fn)
  const sel = list.find((x) => x.ticket_id === openId)

  if (sel) return <div className="flow inq"><Detail t={sel} onBack={() => setOpenId(null)} onSend={onSend} onAgain={onAgain} /></div>

  return (
    <div className="flow inq">
      <h2 className="inq-h">내 문의</h2>
      {list.length === 0 ? (
        <div className="done-box"><div className="big" aria-hidden="true">📭</div><h2>아직 남긴 문의가 없어요</h2>
          <button type="button" className="pbtn" onClick={onNew}>문의 남기기</button></div>
      ) : (
        <>
          <div className="itabs" role="tablist">
            {FILTERS.map(([id, label, f]) => (
              <button type="button" role="tab" aria-selected={filter === id} key={id} className={filter === id ? 'on' : ''} onClick={() => setFilter(id)}>
                {label} <em>{list.filter(f).length}</em>
              </button>
            ))}
          </div>
          <ul className="inq-list">
            {shown.map((t) => (
              <li key={t.ticket_id}>
                <button type="button" className="irow2" onClick={() => setOpenId(t.ticket_id)}>
                  <b>{titleOf(t)}</b>
                  <span className="im">{t.received_at_utc ? t.received_at_utc.slice(0, 10) : ''} · {CHANNEL_SHORT[t.channel]}</span>
                  {STATUS[t.status].kind === 'need' && <em className="needtag">추가 정보 필요</em>}
                </button>
              </li>
            ))}
            {shown.length === 0 && <li className="faqp-empty">이 분류에는 문의가 없어요.</li>}
          </ul>
        </>
      )}
    </div>
  )
}
