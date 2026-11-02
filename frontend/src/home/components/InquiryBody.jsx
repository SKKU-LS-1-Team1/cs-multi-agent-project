import { useState } from 'react'
import CuteIcon from './CuteIcon.jsx'
import Attachments from './Attachments.jsx'
import { fieldLabel, fieldLabels } from '../lib/inquiry.js'

// 접수한 내용(문의 본문)을 읽기 쉽게 나눠 보여 준다.
// 문의서가 만든 본문 형식을 읽는다: 자유 서술(증상·이미 해 본 조치 줄 포함) → "Details:" 항목 목록 → "Contact:" 한 줄.
// 이 형식이 아닌 본문(전화 메모·이메일 등)은 그대로 보여 준다(onPlain).
const TRIED = /^(.*?)\s*\(확인:\s*(.*?)\)\s*(?:→\s*(.*))?$/

export function parseBody(text) {
  const [head, ...rest] = String(text ?? '').split(/\n\s*Details:\s*\n/)
  const detailsAndTail = rest.join('\n')
  const out = { notes: [], symptoms: [], tried: [], details: [], contact: [] }
  for (const raw of head.split('\n')) {
    const line = raw.trim()
    if (!line) continue
    if (line.startsWith('증상: ')) out.symptoms.push(line.slice(4))
    else if (line.startsWith('이미 해 본 조치: ')) {
      const m = line.slice(10).match(TRIED)
      out.tried.push(m ? { action: m[1], check: m[2], result: m[3] } : { action: line.slice(10) })
    } else out.notes.push(line)
  }
  for (const raw of detailsAndTail.split('\n')) {
    const line = raw.trim()
    if (!line) continue
    if (line.startsWith('Contact:')) {
      out.contact = line.slice(8).split(' / ').map((p) => { const i = p.indexOf(': '); return i < 0 ? { k: '', v: p.trim() } : { k: p.slice(0, i).trim(), v: p.slice(i + 2).trim() } })
    } else if (line.startsWith('- ')) {
      const i = line.indexOf(': ')
      out.details.push(i < 0 ? { k: '', v: line.slice(2) } : { k: line.slice(2, i), v: line.slice(i + 2) })
    } else out.notes.push(line)
  }
  return out
}

export const isStructured = (text) => /(^|\n)(증상: |이미 해 본 조치: )/.test(text) || /\n\s*Details:\s*\n/.test(text)

const kindOfName = (n) => (/\.(mp4|mov|avi|webm)$/i.test(n) ? 'video' : /\.(mp3|m4a|wav|aac|ogg)$/i.test(n) ? 'sound' : /\.(pdf|docx?|xlsx?|csv|txt|zip)$/i.test(n) ? 'doc' : 'photo')
const norm = (s) => String(s).toLowerCase().replace(/\s+/g, '')
const clean = (v) => String(v).replace(/\[attachment: ([^\]]+)\]/g, '첨부 $1')

// 처음 문의서에서 받는 항목(required) 전부를 한 표로 보여 준다. 필수 항목은 접수할 때 이미 다 받으므로 "안 보냄" 상태는 없다(값이 기록에 없으면 "제출했어요").
// 서버가 항목 목록을 주지 않으면(required 가 비어 있으면) 본문에 적힌 항목만 보여 준다.
function infoRows(b, { required, fallback, files }) {
  if (!required.length) return b.details.map((d) => ({ label: d.k, value: clean(d.v), state: 'value' }))
  const used = new Set()
  const rows = required.map((key) => {
    const names = fieldLabels(key).map(norm)
    const i = b.details.findIndex((d, n) => !used.has(n) && names.includes(norm(d.k)))
    if (i >= 0) used.add(i)
    const raw = i >= 0 ? clean(b.details[i].v) : ''
    // 가려진 값(**MASKED**)이나 첨부 개수 표시는 더 자세한 값이 있으면 그것을 쓴다
    const value = key === 'photos' && files.length ? `첨부 ${files.length}개` : (/MASKED/.test(raw) || !raw) && fallback[key] ? fallback[key] : raw || fallback[key]
    return { label: fieldLabel(key), value, state: value ? 'value' : 'sent' }
  })
  return [...rows, ...b.details.filter((_, n) => !used.has(n)).map((d) => ({ label: d.k, value: clean(d.v), state: 'value' }))]
}

// media: 서버에 올린 첨부([{ name, size, type, url }], Inquiries.jsx useAttachments). 있으면 사진을 썸네일로 보여 준다
export default function InquiryBody({ text, required = [], fallback = {}, files = [], contact = [], media = null }) {
  const b = parseBody(text)
  const rows = infoRows(b, { required, fallback, files })
  const [more, setMore] = useState(false)
  const shownContact = b.contact.length ? b.contact : contact
  const hasMore = rows.length > 0 || shownContact.length > 0 || files.length > 0
  return (
    <div className="ibody">
      {b.notes.length > 0 && (
        <section className="ib-sec"><h5>문의 내용</h5>
          <div className="ib-notes">{b.notes.map((n, i) => <p key={i}>{n}</p>)}</div></section>
      )}
      {b.symptoms.length > 0 && (
        <section className="ib-sec"><h5>증상 <em>{b.symptoms.length}</em></h5>
          <ul className="ib-list">{b.symptoms.map((s) => <li key={s}>{s}</li>)}</ul></section>
      )}
      {b.tried.length > 0 && (
        <section className="ib-sec"><h5>이미 해 본 조치 <em>{b.tried.length}</em></h5>
          <ol className="ib-tried">{b.tried.map((t, i) => (
            <li key={i}><b>{t.action}</b>{t.check && <small>확인: {t.check}</small>}{t.result && <i>{t.result}</i>}</li>))}</ol></section>
      )}
      {hasMore && <button type="button" className="link ib-more" aria-expanded={more} onClick={() => setMore(!more)}>{more ? '접기' : '자세히 보기'}</button>}
      {more && (
        <>
        {rows.length > 0 && (
          <section className="ib-sec"><h5>제출한 정보</h5>
            <dl className="ib-dl">{rows.map((x, i) => (
              <div key={i} className={`st-${x.state}`}><dt>{x.label}</dt>
                <dd>{x.state === 'value' ? x.value : '제출했어요'}</dd></div>))}</dl></section>
        )}
        {files.length > 0 && (
          <section className="ib-sec"><h5>첨부 자료 <em>{files.length}</em></h5>
            {media ? <Attachments items={media} /> : <ul className="ib-files">{files.map((n) => { const k = kindOfName(n); return (
              <li key={n}><span className="ibf-i"><CuteIcon name={k} size={22} /></span><b title={n}>{n}</b></li>) })}</ul>}</section>
        )}
        {shownContact.length > 0 && (
          <section className="ib-sec"><h5>연락처</h5>
            <dl className="ib-dl">{shownContact.map((d, i) => <div key={i}><dt>{d.k}</dt><dd>{d.v}</dd></div>)}</dl></section>
        )}
        </>
      )}
    </div>
  )
}
