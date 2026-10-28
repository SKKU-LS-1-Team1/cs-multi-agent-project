import CuteIcon from './CuteIcon.jsx'

export const TOPICS = [
  { id: 'stopped', label: '제품이 멈췄어요', icon: 'alert', wide: true },
  { id: 'install', label: '설치 · 사용 방법', icon: 'gear' },
  { id: 'info', label: '제품 정보 · 자료', icon: 'doc' },
  { id: 'warranty', label: '보증 · 주문 · 견적', icon: 'shield' },
]

export default function Hero({ onSelect }) {
  const [wide, ...rest] = TOPICS
  return (
    <section className="hero">
      <h1>어떤 도움이 필요하세요?</h1>
      <button type="button" className="gwide" onClick={() => onSelect(wide)}>
        <CuteIcon name={wide.icon} />
        {wide.label}
      </button>
      <div className="gtiles">
        {rest.map((t) => (
          <button type="button" key={t.id} className="gt" onClick={() => onSelect(t)}>
            <CuteIcon name={t.icon} />
            {t.label}
          </button>
        ))}
      </div>
    </section>
  )
}
