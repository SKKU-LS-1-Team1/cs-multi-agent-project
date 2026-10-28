import { useEffect, useRef, useState } from 'react'
import logo from '../assets/ls-electric-logo.png'
import {
  LANGUAGES, RTL, countryName, detectCountry, initialLang, loadChoice, saveChoice,
} from '../lib/onboarding.js'
import { t } from '../lib/i18n.js'
import FlagIcon from './FlagIcon.jsx'

// 국가(country)와 언어(lang)는 별도 상태다. 언어를 바꿔도 국가는 바뀌지 않는다.
export default function Onboarding({ onDone }) {
  const [country, setCountry] = useState({ status: 'loading', code: null })
  const [{ lang, source }, setLangState] = useState(() => initialLang({ choice: loadChoice(), country: null }))
  const sourceRef = useRef(source)
  sourceRef.current = source

  useEffect(() => {
    let alive = true
    detectCountry().then((r) => {
      if (!alive) return
      setCountry(r)
      // 사용자가 이미 고른 언어는 덮어쓰지 않는다. (저장된 선택 포함)
      if (sourceRef.current !== 'user') setLangState(initialLang({ choice: null, country: r.status === 'ok' ? r.code : null }))
    })
    return () => { alive = false }
  }, [])

  // 문서 언어·방향 반영 (아랍어는 RTL)
  useEffect(() => {
    document.documentElement.lang = lang
    document.documentElement.dir = RTL.has(lang) ? 'rtl' : 'ltr'
    return () => { document.documentElement.lang = 'ko'; document.documentElement.dir = 'ltr' }
  }, [lang])

  const choose = (code) => { saveChoice(code); setLangState({ lang: code, source: 'user' }) }

  // 라디오 그룹 키보드: 방향키 · Home/End. RTL 에서는 좌우가 반대로 움직인다.
  const onKey = (e) => {
    const i = LANGUAGES.findIndex(([c]) => c === lang)
    const rtl = RTL.has(lang)
    const next = { ArrowRight: rtl ? -1 : 1, ArrowDown: 1, ArrowLeft: rtl ? 1 : -1, ArrowUp: -1 }[e.key]
    let j = null
    if (next) j = (i + next + LANGUAGES.length) % LANGUAGES.length
    else if (e.key === 'Home') j = 0
    else if (e.key === 'End') j = LANGUAGES.length - 1
    if (j === null) return
    e.preventDefault()
    choose(LANGUAGES[j][0])
    e.currentTarget.querySelectorAll('[role=radio]')[j]?.focus()
  }

  const ok = country.status === 'ok'
  const label = country.status === 'loading' ? t(lang, 'detecting') : ok ? countryName(country.code) : t(lang, 'unknown')
  const aria = `${t(lang, 'country')}: ${label}`

  return (
    <main className="ob" dir={RTL.has(lang) ? 'rtl' : 'ltr'} lang={lang}>
      <header className="ob-brand">
        <img src={logo} alt="LS ELECTRIC" className="ob-logo" />
        <p>{t(lang, 'tagline')}</p>
      </header>

      <section className="ob-card" aria-labelledby="ob-h">
        <h1 id="ob-h">{t(lang, 'title')}</h1>
        <p className="ob-sub">{t(lang, 'sub')}</p>

        <div className="ob-country" role="status" aria-live="polite" aria-label={aria}>
          <span className={`ob-badge${country.status === 'loading' ? ' is-loading' : ''}`} aria-hidden="true">
            {country.status === 'loading' ? null : <FlagIcon code={ok ? country.code : null} size={52} />}
          </span>
          <span className="ob-cname">
            <small>{t(lang, 'country')}</small>
            <b className={ok ? '' : 'is-weak'}>{label}</b>
          </span>
        </div>

        <div className="ob-lh" id="ob-lang">{t(lang, 'language')}</div>
        <div className="ob-langs" role="radiogroup" aria-labelledby="ob-lang" onKeyDown={onKey}>
          {LANGUAGES.map(([code, name]) => {
            const on = code === lang
            return (
              <button key={code} type="button" role="radio" aria-checked={on} tabIndex={on ? 0 : -1}
                className={`ob-lang${on ? ' is-on' : ''}`} lang={code} onClick={() => choose(code)}>
                <span className="ob-check" aria-hidden="true">{on ? '✓' : ''}</span>
                <span>{name}</span>
              </button>
            )
          })}
        </div>

        <button type="button" className="ob-go" onClick={() => onDone(lang)}>{t(lang, 'start')}</button>
      </section>
    </main>
  )
}
