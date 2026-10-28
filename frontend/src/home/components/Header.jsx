import logo from '../assets/ls-logo.png'
import LangMenu from './LangMenu.jsx'

export default function Header({ lang, onLang, onBack, onHome, onFaq, onMine, onNew }) {
  return (
    <header className="hd">
      <div className="hd-l">
      {onBack && (
        <button type="button" className="hd-back" onClick={onBack} aria-label="국가·언어 선택으로 돌아가기" title="국가·언어 선택으로 돌아가기">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M15 5l-7 7 7 7" /></svg>
        </button>
      )}
      <div className="logo" onClick={onHome} role="link" tabIndex={0} onKeyDown={(e) => e.key === 'Enter' && onHome?.()} style={{ cursor: onHome ? 'pointer' : undefined }}>
        <img src={logo} alt="LS" height="22" />
        <span className="vbar" />
        <span className="lt">고객상담</span>
      </div>
      </div>
      <nav className="nav">
        <a href="#" onClick={(e) => { e.preventDefault(); onFaq?.() }}>자주 묻는 질문</a>
        <a href="#" onClick={(e) => { e.preventDefault(); onMine?.() }}>내 문의</a>
        <LangMenu lang={lang} onChange={onLang} />
        <button type="button" className="btn m fill primary" onClick={() => onNew?.()}>문의 남기기</button>
      </nav>
    </header>
  )
}
