import CuteIcon from './CuteIcon.jsx'
import ContextCard from './ContextCard.jsx'
import ChatText from './ChatText.jsx'
import { useEffect, useRef, useState } from 'react'

const CHIPS = ['화면에 E.OC가 떠요', '보증 기간이 남았나요?', '설치 설명서가 필요해요']

const Svg = ({ size, w = 2, children }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={w} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    {children}
  </svg>
)

// messages: [{ id, role: 'user' | 'assistant', content }] — 챗봇 API 의 transcript 형식과 맞춤
export default function ChatPanel({ messages, onSend, onReset, focusKey = 0, cards = [], activeKey, onActivate, onRemoveCard, onInquire }) {
  const [text, setText] = useState('')
  const [confirm, setConfirm] = useState(false) // 대화 초기화 확인창
  const bodyRef = useRef(null)
  const inputRef = useRef(null)

  useEffect(() => {
    bodyRef.current?.scrollTo({ top: bodyRef.current.scrollHeight })
  }, [messages])

  // 해결 화면에서 이어 올 때: 입력창에 커서를 두어 바로 물어볼 수 있게 한다 (처음 그릴 때는 건드리지 않는다)
  useEffect(() => { if (focusKey) inputRef.current?.focus({ preventScroll: true }) }, [focusKey])

  const submit = (e) => {
    e.preventDefault()
    const v = text.trim()
    if (!v) return
    onSend(v)
    setText('')
  }

  return (
    <div className="chat">
      <div className="ch">
        <span className="av" aria-hidden="true"><CuteIcon name="bot" size={30} /></span>
        <div className="ch-t">
          <b>AI 상담</b>
          <small>문의서에 자동 입력돼요.</small>
        </div>
        {onReset && (
          <button type="button" className="ch-reset" disabled={messages.length === 0} aria-haspopup="dialog" aria-expanded={confirm} onClick={() => setConfirm(true)}>대화 초기화</button>
        )}
      </div>

      {confirm && (
        <div className="ch-pop" role="alertdialog" aria-labelledby="ch-pop-t" onKeyDown={(e) => e.key === 'Escape' && setConfirm(false)}>
          <b id="ch-pop-t">대화를 초기화할까요?</b>
          <p>대화가 지워져요. 보고 있는 제품은 유지돼요.</p>
          <div>
            <button type="button" className="ch-cancel" autoFocus onClick={() => setConfirm(false)}>취소</button>
            <button type="button" className="ch-ok" onClick={() => { onReset(); setText(''); setConfirm(false) }}>초기화</button>
          </div>
        </div>
      )}

      {cards.length > 0 && (
        <div className="cc-stack">
          {cards.map((c) => <ContextCard key={c.key} lines={c.lines} topics={c.topics} active={c.key === activeKey} onActivate={() => onActivate?.(c.key)} onRemove={() => onRemoveCard?.(c.key)} />)}
        </div>
      )}

      <div className="cb-body" ref={bodyRef}>
        <div className="bub">안녕하세요! 궁금한 걸 편하게 적어 주세요. 아래에서 골라도 돼요.</div>
        {messages.length === 0 && (
          <div className="chips">
            {CHIPS.map((c) => (
              <button type="button" key={c} className="chip" onClick={() => onSend(c)}>{c}</button>
            ))}
          </div>
        )}
        {messages.map((m) => (
          <div key={m.id} className={`${m.role === 'user' ? 'bub me' : 'bub'}${m.flash ? ' flash' : ''}`} style={m.role === 'user' ? { whiteSpace: 'pre-line' } : undefined}>
            {m.role === 'user' ? m.content : <ChatText text={m.content} />}
            {m.contact && (
              <div className="bub-contact"><small>담당 기술팀</small><b>{m.contact.dept}</b><a href={`mailto:${m.contact.email}`}>{m.contact.email}</a><small>시연용 주소예요</small></div>
            )}
          </div>
        ))}
        {/* 펌웨어 답변(기술팀 연락처 안내) 바로 뒤에는 문의서로 보내지 않는다 */}
        {messages.length > 0 && onInquire && messages.at(-1).kind !== 'fw' && <button type="button" className="chatgo" onClick={onInquire}>이 내용으로 문의 남기기</button>}
      </div>

      <form className="cin" onSubmit={submit}>
        <div className="box">
          <input ref={inputRef} value={text} onChange={(e) => setText(e.target.value)} placeholder="메시지를 입력하세요" aria-label="메시지" />
          <button type="submit" className="send" aria-label="보내기">
            <Svg size={18} w={2.4}><path d="M12 19V5M6 11l6-6 6 6" stroke="#fff" /></Svg>
          </button>
        </div>
      </form>
    </div>
  )
}
