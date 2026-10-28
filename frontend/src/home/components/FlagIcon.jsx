// 둥글고 단순한 투톤 국기 (48x48). CuteIcon 과 같은 결로, 실제 국기를 단순화해 원 안에 그린다.
const star = (cx, cy, r, fill) => {
  const pts = Array.from({ length: 10 }, (_, i) => {
    const a = (Math.PI / 5) * i - Math.PI / 2
    const rr = i % 2 ? r * 0.4 : r
    return `${(cx + rr * Math.cos(a)).toFixed(2)},${(cy + rr * Math.sin(a)).toFixed(2)}`
  }).join(' ')
  return <polygon points={pts} fill={fill} />
}
const H = (cols, ws) => { let y = 0; return cols.map((c, i) => { const h = ws[i]; const el = <rect key={i} x="0" y={y} width="48" height={h} fill={c} />; y += h; return el }) }
const V = (cols, ws) => { let x = 0; return cols.map((c, i) => { const w = ws[i]; const el = <rect key={i} x={x} y="0" width={w} height="48" fill={c} />; x += w; return el }) }

const FLAGS = {
  TH: <>{H(['#E4283C', '#fff', '#2A3F8F', '#fff', '#E4283C'], [8, 6, 20, 6, 8])}</>,
  JP: <><rect width="48" height="48" fill="#fff" /><circle cx="24" cy="24" r="10" fill="#E8344A" /></>,
  BR: <><rect width="48" height="48" fill="#1FA85A" /><path d="M24 7L43 24 24 41 5 24z" fill="#FFD23F" /><circle cx="24" cy="24" r="8" fill="#2A3F8F" /><path d="M16.5 22.5c5-1.5 10.5-.5 15 2" stroke="#fff" strokeWidth="1.6" fill="none" /></>,
  FR: <>{V(['#2A4FA8', '#fff', '#E8344A'], [16, 16, 16])}</>,
  GB: <><rect width="48" height="48" fill="#2A3F8F" /><path d="M0 0L48 48M48 0L0 48" stroke="#fff" strokeWidth="8" /><path d="M0 0L48 48M48 0L0 48" stroke="#E8344A" strokeWidth="3" /><rect x="19" width="10" height="48" fill="#fff" /><rect y="19" width="48" height="10" fill="#fff" /><rect x="21.2" width="5.6" height="48" fill="#E8344A" /><rect y="21.2" width="48" height="5.6" fill="#E8344A" /></>,
  SA: <><rect width="48" height="48" fill="#1B8F57" /><rect x="11" y="17" width="26" height="4" rx="2" fill="#fff" /><rect x="11" y="25" width="26" height="3" rx="1.5" fill="#fff" opacity=".85" /><rect x="14" y="33" width="20" height="3" rx="1.5" fill="#fff" /></>,
  IN: <>{H(['#FF9933', '#fff', '#1FA85A'], [16, 16, 16])}<circle cx="24" cy="24" r="5" fill="none" stroke="#2A3F8F" strokeWidth="2" /></>,
  RU: <>{H(['#fff', '#2A4FA8', '#E8344A'], [16, 16, 16])}</>,
  AE: <>{H(['#1FA85A', '#fff', '#2B2B2B'], [16, 16, 16])}<rect width="14" height="48" fill="#E8344A" /></>,
  AU: <><rect width="48" height="48" fill="#2A3F8F" /><rect width="22" height="22" fill="#2A3F8F" /><path d="M0 0L22 22M22 0L0 22" stroke="#fff" strokeWidth="3.5" /><rect x="8.5" width="5" height="22" fill="#fff" /><rect y="8.5" width="22" height="5" fill="#fff" /><rect x="9.8" width="2.4" height="22" fill="#E8344A" /><rect y="9.8" width="22" height="2.4" fill="#E8344A" />{star(12, 36, 5, '#fff')}{star(34, 14, 3, '#fff')}{star(38, 30, 3, '#fff')}{star(30, 40, 3, '#fff')}</>,
  IT: <>{V(['#1FA85A', '#fff', '#E8344A'], [16, 16, 16])}</>,
  US: <>{H(['#E8344A', '#fff', '#E8344A', '#fff', '#E8344A', '#fff', '#E8344A'], [7, 6, 7, 7, 7, 6, 8])}<rect width="26" height="27" fill="#2A3F8F" />{[[7, 7], [14, 7], [21, 7], [10.5, 14], [17.5, 14], [7, 21], [14, 21], [21, 21]].map(([x, y], i) => <circle key={i} cx={x} cy={y} r="1.6" fill="#fff" />)}</>,
  DE: <>{H(['#2B2B2B', '#E8344A', '#FFC93C'], [16, 16, 16])}</>,
  ID: <>{H(['#E8344A', '#fff'], [24, 24])}</>,
  MX: <>{V(['#1FA85A', '#fff', '#E8344A'], [16, 16, 16])}<circle cx="24" cy="24" r="4.5" fill="#B9854A" /></>,
  ES: <>{H(['#E8344A', '#FFC93C', '#E8344A'], [12, 24, 12])}</>,
  CN: <><rect width="48" height="48" fill="#E8344A" />{star(15, 16, 8, '#FFD23F')}{star(28, 8, 2.6, '#FFD23F')}{star(33, 14, 2.6, '#FFD23F')}{star(33, 21, 2.6, '#FFD23F')}{star(28, 27, 2.6, '#FFD23F')}</>,
  VN: <><rect width="48" height="48" fill="#E8344A" />{star(24, 25, 13, '#FFD23F')}</>,
  TR: <><rect width="48" height="48" fill="#E8344A" /><circle cx="20" cy="24" r="10" fill="#fff" /><circle cx="23" cy="24" r="8" fill="#E8344A" />{star(30, 24, 4.5, '#fff')}</>,
  PL: <>{H(['#fff', '#E8344A'], [24, 24])}</>,
}

// code 가 없거나 지원 국가가 아니면 둥근 지구 아이콘
const GLOBE = (
  <>
    <circle cx="24" cy="24" r="24" fill="#3562A6" />
    <path d="M10 18c4-5 9-4 11-1s-2 6-5 7-7 2-6-6zM27 28c3-2 7 0 8 3s-3 8-6 7-5-8-2-10zM28 8c4-1 8 1 10 4-4 1-8 1-10-4z" fill="#BECDE3" />
    <ellipse cx="17" cy="12" rx="9" ry="5" fill="#fff" opacity=".18" />
  </>
)

export default function FlagIcon({ code, size = 52, label }) {
  const id = `flag-${code || 'globe'}`
  const flag = code && FLAGS[code]
  return (
    <svg className="cute" width={size} height={size} viewBox="0 0 48 48" role={label ? 'img' : undefined} aria-label={label} aria-hidden={label ? undefined : true}>
      <defs><clipPath id={id}><circle cx="24" cy="24" r="24" /></clipPath></defs>
      {flag ? (
        <g clipPath={`url(#${id})`}>{flag}<ellipse cx="17" cy="11" rx="12" ry="6" fill="#fff" opacity=".2" /></g>
      ) : GLOBE}
      <circle cx="24" cy="24" r="23.5" fill="none" stroke="rgba(2,32,71,.12)" />
    </svg>
  )
}
