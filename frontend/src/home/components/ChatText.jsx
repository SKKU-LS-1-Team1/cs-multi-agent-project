// 챗봇 답변 글을 읽기 좋게 그린다: 문단 · 목록(- , 1.) · **굵게** · 근거 [문서 · 절].
// 서버(chatbot/agent.py _chat_text)가 이것만 남겨 보낸다. 그 밖의 글자는 그대로 보여 준다.
// 근거는 본문 줄 끝에서 떼어 답변 아래 '참고' 줄에 한 번씩만 모은다 — 본문이 끊기지 않게.
import { Fragment } from 'react'

const BOLD = /(\*\*[^*\n]+\*\*)/g
const CITE = /[ \t]*\[([A-Z][A-Z0-9]*-[^\]\n]+)\]/g

function inline(text) {
  return text.split(BOLD).map((part, i) => {
    if (/^\*\*[^*\n]+\*\*$/.test(part)) return <strong key={i}>{part.slice(2, -2)}</strong>
    return <Fragment key={i}>{part}</Fragment>
  })
}

// 목록 항목 "가속 중 발생 시: …" 의 짧은 머리말은 따로 굵게 — 항목끼리 훑어보기 쉽게
function item(text) {
  const m = /^([^:*\n]{1,24}?)[:：]\s+(.+)$/.exec(text)
  if (!m) return inline(text)
  return <><b className="ct-k">{m[1]}:</b> {inline(m[2])}</>
}

// 같은 문서의 절은 칩 하나로: "TG-… · 2", "TG-… · 3.1" → "TG-… · 2, 3.1"
function groupCites(labels) {
  const docs = new Map()
  for (const l of labels) {
    const [doc, ...rest] = l.split(' · ')
    const sec = rest.join(' · ')
    if (!docs.has(doc)) docs.set(doc, [])
    if (sec && !docs.get(doc).includes(sec)) docs.get(doc).push(sec)
  }
  return [...docs].map(([doc, secs]) => (secs.length ? `${doc} · ${secs.join(', ')}` : doc))
}

// 같은 종류의 줄을 묶는다. 빈 줄은 문단을 나누지만, 목록 항목 사이의 빈 줄은 같은 목록으로 본다.
function parse(text) {
  const out = []
  let gap = false
  for (const raw of text.split('\n')) {
    const line = raw.trim()
    if (!line) { gap = true; continue }
    const m = /^[-•]\s+(.*)/.exec(line) || /^(\d+)[.)]\s+(.*)/.exec(line)
    const kind = !m ? 'p' : m.length === 3 ? 'ol' : 'ul'
    const item = m ? m[m.length - 1] : line
    const last = out[out.length - 1]
    if (last && last.kind === kind && (kind !== 'p' || !gap)) last.items.push(item)
    else out.push({ kind, items: [item], start: kind === 'ol' ? Number(m[1]) : undefined })
    gap = false
  }
  return out
}

export default function ChatText({ text }) {
  const cites = groupCites(Array.from(text.matchAll(CITE), (m) => m[1].trim()))
  const blocks = parse(text.replace(CITE, ''))
  return (
    <div className="ct">
      {blocks.map((b, i) => {
        if (b.kind === 'p') {
          // 목록 바로 앞의 "…:" 한 줄은 목록의 머리말로 조금 진하게
          const lead = b.items.length === 1 && /[:：]$/.test(b.items[0]) && blocks[i + 1] && blocks[i + 1].kind !== 'p'
          return <p key={i} className={lead ? 'ct-lead' : undefined}>{b.items.map((l, j) => <Fragment key={j}>{j > 0 && <br />}{inline(l)}</Fragment>)}</p>
        }
        const List = b.kind === 'ol' ? 'ol' : 'ul'
        return <List key={i} start={b.start}>{b.items.map((l, j) => <li key={j}>{item(l)}</li>)}</List>
      })}
      {cites.length > 0 && (
        <div className="ct-src">
          <span>참고</span>
          {cites.map((c) => <span key={c} className="cite" title={c}>{c}</span>)}
        </div>
      )}
    </div>
  )
}
