// 챗봇 답변 글을 읽기 좋게 그린다: 문단 · 목록(- , 1.) · **굵게** · 근거 [문서 · 절].
// 서버(chatbot/agent.py _chat_text)가 이것만 남겨 보낸다. 그 밖의 글자는 그대로 보여 준다.
import { Fragment } from 'react'

const INLINE = /(\*\*[^*\n]+\*\*|\[[A-Z][A-Z0-9]*-[^\]\n]+\])/g

function inline(text) {
  return text.split(INLINE).map((part, i) => {
    if (/^\*\*[^*\n]+\*\*$/.test(part)) return <strong key={i}>{part.slice(2, -2)}</strong>
    if (/^\[[A-Z][A-Z0-9]*-/.test(part)) return <span key={i} className="cite">{part.slice(1, -1)}</span>
    return <Fragment key={i}>{part}</Fragment>
  })
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
  return (
    <div className="ct">
      {parse(text).map((b, i) => {
        if (b.kind === 'p') return <p key={i}>{b.items.map((l, j) => <Fragment key={j}>{j > 0 && <br />}{inline(l)}</Fragment>)}</p>
        const List = b.kind === 'ol' ? 'ol' : 'ul'
        return <List key={i} start={b.start}>{b.items.map((l, j) => <li key={j}>{inline(l)}</li>)}</List>
      })}
    </div>
  )
}
