import { Fragment, useEffect, useRef, useState } from 'react'
import { DOC_LABEL, DOC_ORDER } from '../lib/guide.js'

let cache
const loadDocs = () => (cache ??= import('../data/docs.json').then((m) => m.default))

const Inline = ({ text }) =>
  text.split(/(\*\*.*?\*\*)/g).map((p, i) => (p.startsWith('**') ? <strong key={i}>{p.slice(2, -2)}</strong> : <Fragment key={i}>{p}</Fragment>))

export const fmtSize = (n) => (n < 1024 ? `${n} B` : `${(n / 1024).toFixed(1)} KB`)

function Block({ b, mark }) {
  const isMark = (t) => !!mark && (t === mark || t.startsWith(`${mark}:`))
  switch (b.t) {
    case 'p': return <p><Inline text={b.text} /></p>
    case 'quote': return <blockquote><Inline text={b.text} /></blockquote>
    case 'ul': return <ul>{b.items.map((x) => <li key={x} className={isMark(x) ? 'mark' : undefined}><Inline text={x} /></li>)}</ul>
    case 'ol': return <ol>{b.items.map((x) => <li key={x}><Inline text={x} /></li>)}</ol>
    case 'check': return <ul className="chk-l">{b.items.map((x) => <li key={x}>☐ <Inline text={x} /></li>)}</ul>
    case 'table': return (
      <div className="tw"><table>
        <thead><tr>{b.head.map((h) => <th key={h}>{h}</th>)}</tr></thead>
        <tbody>{b.rows.map((r, i) => <tr key={i} className={isMark(r[0]) ? 'mark' : undefined}>{r.map((c, j) => <td key={j}><Inline text={c} /></td>)}</tr>)}</tbody>
      </table></div>
    )
    default: return null
  }
}

// ref: { doc: 'IG', sec: '3', n } — n 이 바뀔 때마다 다시 그 위치로 이동하고 강조한다.
export default function DocPanel({ code, target, download = false }) {
  const [docs, setDocs] = useState(null)
  const [active, setActive] = useState(null)
  const box = useRef(null)
  const tabsRef = useRef(null)

  useEffect(() => { loadDocs().then(setDocs) }, [])
  const mine = docs?.[code]
  const types = mine ? [...DOC_ORDER.filter((t) => mine[t]), ...['POL-WARRANTY', 'POL-RETURN', 'POL-ORDER', 'POL-SERVICE'].filter((t) => mine[t])] : []
  const cur = active && mine?.[active] ? active : target?.doc && mine?.[target.doc] ? target.doc : types[0]

  useEffect(() => { if (target?.doc && mine?.[target.doc]) setActive(target.doc) }, [target?.doc, target?.n, code, !!mine]) // eslint-disable-line

  useEffect(() => {
    if (!mine || !target || cur !== target.doc || !box.current) return
    if (!target.sec) { box.current.scrollTo({ top: 0 }); return }
    const el = box.current.querySelector(`[data-sec="${target.sec}"]`)
    const hitRow = target.mark && el?.querySelector('.mark')
    const to = hitRow ?? el
    if (to) box.current.scrollTo({ top: Math.max(0, to.getBoundingClientRect().top - box.current.getBoundingClientRect().top + box.current.scrollTop - (hitRow ? 120 : 12)), behavior: 'smooth' })
  }, [target?.n, target?.sec, cur, !!mine]) // eslint-disable-line

  useEffect(() => { tabsRef.current?.querySelector('.on')?.scrollIntoView({ inline: 'nearest', block: 'nearest' }) }, [cur, !!mine]) // eslint-disable-line

  if (!code) return <div className="doc-empty">제품과 목적을 고르면 원문이 여기에 나와요. 📄</div>
  if (!mine) return <div className="doc-empty">원문을 불러오는 중이에요…</div>
  const doc = mine[cur]
  const hit = (num) => target?.doc === cur && target?.sec && (num === target.sec || num.startsWith(`${target.sec}.`))

  return (
    <div className="doc">
      <div className="doc-tabs" role="tablist" ref={tabsRef}>
        {types.map((t) => (
          <button type="button" role="tab" aria-selected={t === cur} key={t} className={t === cur ? 'on' : ''} onClick={() => setActive(t)}>
            {DOC_LABEL[t] ?? t}<small>{t.replace('POL-', '')}</small>
          </button>
        ))}
      </div>
      <div className="doc-body" ref={box}>
        <div className="doc-id">
          <span>{doc.id} · Rev. {doc.revision} · 자료 원문(영어)</span>
          {download && doc.file && (
            <a className="dl" href={`${import.meta.env.BASE_URL}${doc.file}`} download>⬇️ 원본 다운로드 <small>{doc.fmt} · {fmtSize(doc.bytes)}</small></a>
          )}
        </div>
        {doc.sections.filter((s) => s.num !== '0' || s.blocks.length).map((s, i) => (
          <section key={`${s.num}-${i}-${hit(s.num) ? target.n : ''}`} data-sec={s.num} className={`dsec${hit(s.num) ? ' hl' : ''}`}>
            {s.title && s.num !== '0' && (s.level === 2 ? <h4>{s.num}. {s.title}</h4> : <h5>{s.num} {s.title}</h5>)}
            {s.blocks.map((b, j) => <Block key={j} b={b} mark={hit(s.num) ? target.mark : undefined} />)}
          </section>
        ))}
      </div>
    </div>
  )
}
