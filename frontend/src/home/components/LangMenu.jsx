import { useEffect, useRef, useState } from 'react'
import { LANGUAGES } from '../lib/onboarding.js'

// 헤더 언어 변경: 지구본 + 현재 언어 코드(EN). 누르면 15개 언어 목록이 열린다.
export default function LangMenu({ lang, onChange }) {
  const [open, setOpen] = useState(false)
  const root = useRef(null)
  const btn = useRef(null)
  const cur = LANGUAGES.find(([c]) => c === lang) ?? LANGUAGES[0]

  useEffect(() => {
    if (!open) return
    const out = (e) => { if (!root.current?.contains(e.target)) setOpen(false) }
    document.addEventListener('mousedown', out)
    root.current?.querySelector('[aria-selected=true]')?.focus()
    return () => document.removeEventListener('mousedown', out)
  }, [open])

  const pick = (code) => { onChange(code); setOpen(false); btn.current?.focus() }
  const onKey = (e) => {
    if (e.key === 'Escape') { setOpen(false); btn.current?.focus(); return }
    const items = [...root.current.querySelectorAll('[role=option]')]
    const i = items.indexOf(document.activeElement)
    const go = (j) => { e.preventDefault(); items[(j + items.length) % items.length]?.focus() }
    if (e.key === 'ArrowDown') go(i + 1)
    else if (e.key === 'ArrowUp') go(i - 1)
    else if (e.key === 'Home') go(0)
    else if (e.key === 'End') go(items.length - 1)
  }

  return (
    <div className="lm" ref={root} onKeyDown={open ? onKey : undefined}>
      <button ref={btn} type="button" className="lm-btn" aria-haspopup="listbox" aria-expanded={open}
        aria-label={`언어 변경 (현재: ${cur[1]})`} onClick={() => setOpen((v) => !v)}>
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
          <circle cx="12" cy="12" r="9" /><path d="M3 12h18M12 3c3 3.2 3 14.8 0 18M12 3c-3 3.2-3 14.8 0 18" />
        </svg>
        <b>{lang.toUpperCase()}</b>
      </button>
      {open && (
        <ul className="lm-list" role="listbox" aria-label="언어">
          {LANGUAGES.map(([code, name]) => (
            <li key={code} role="option" aria-selected={code === lang} tabIndex={-1} lang={code}
              className={code === lang ? 'is-on' : ''} onClick={() => pick(code)}
              onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); pick(code) } }}>
              <span className="lm-ck" aria-hidden="true">{code === lang ? '✓' : ''}</span>
              <span>{name}</span>
              <small>{code.toUpperCase()}</small>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
