import { useState } from 'react'

const TABS = ['전체', '고장', '설치', '보증 · 반품', '문서']
const ITEMS = [
  { q: '고장을 알릴 때 무엇을 보내야 하나요?', tab: '고장', a: '제품 이름, 명판의 시리얼 번호, 화면에 뜬 글자, 멈췄을 때의 상황을 알려주세요. 사진이나 트립 기록이 있으면 더 빨리 도와드릴 수 있어요.' },
  { q: '보증 기간은 얼마인가요?', tab: '보증 · 반품' },
  { q: '제품을 반품하려면 어떻게 하나요?', tab: '보증 · 반품' },
  { q: '최신 펌웨어는 무엇인가요?', tab: '설치' },
  { q: '설치 설명서는 어디서 받나요?', tab: '문서' },
]

export default function FaqPage() {
  const [tab, setTab] = useState('전체')
  const [open, setOpen] = useState(ITEMS[0].q)
  const items = tab === '전체' ? ITEMS : ITEMS.filter((i) => i.tab === tab)

  return (
    <section className="faqp">
      <h2>자주 묻는 질문</h2>
      <div className="faqp-tabs" role="tablist">
        {TABS.map((t) => (
          <button type="button" role="tab" aria-selected={t === tab} key={t} className={t === tab ? 'on' : ''} onClick={() => setTab(t)}>{t}</button>
        ))}
      </div>
      <ul className="faqp-list">
        {items.map((i) => (
          <li key={i.q}>
            <button type="button" aria-expanded={open === i.q} onClick={() => setOpen(open === i.q ? null : i.q)}>
              <span>{i.q}</span>
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" style={{ transform: open === i.q ? 'rotate(180deg)' : undefined }}><path d="M6 9l6 6 6-6" /></svg>
            </button>
            {open === i.q && <p>{i.a ?? '답변을 준비하고 있어요.'}</p>}
          </li>
        ))}
        {items.length === 0 && <li className="faqp-empty">이 분류의 질문이 아직 없어요.</li>}
      </ul>
    </section>
  )
}
