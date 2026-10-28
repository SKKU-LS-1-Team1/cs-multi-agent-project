// 귀엽고 둥근 투톤 아이콘 (48x48). 색은 LS Blue 계열 + 역할색(red).
const PATHS = {
  alert: (
    <>
      <path d="M24 7c1.5 0 2.9.8 3.7 2.2L41.6 33c1.6 2.8-.4 6.3-3.7 6.3H10.1c-3.3 0-5.3-3.5-3.7-6.3L20.3 9.2C21.1 7.8 22.5 7 24 7z" fill="#F04452" />
      <rect x="22.2" y="17" width="3.6" height="12" rx="1.8" fill="#fff" />
      <circle cx="24" cy="33.2" r="2.2" fill="#fff" />
    </>
  ),
  gear: (
    <>
      <g fill="#3562A6">
        <rect x="21" y="5" width="6" height="9" rx="3" />
        <rect x="21" y="34" width="6" height="9" rx="3" />
        <rect x="5" y="21" width="9" height="6" rx="3" />
        <rect x="34" y="21" width="9" height="6" rx="3" />
        <rect x="21" y="5" width="6" height="9" rx="3" transform="rotate(45 24 24)" />
        <rect x="21" y="34" width="6" height="9" rx="3" transform="rotate(45 24 24)" />
        <rect x="5" y="21" width="9" height="6" rx="3" transform="rotate(45 24 24)" />
        <rect x="34" y="21" width="9" height="6" rx="3" transform="rotate(45 24 24)" />
      </g>
      <circle cx="24" cy="24" r="14" fill="#3562A6" />
      <path d="M12 20a13 13 0 0116-7.5" stroke="#7FA0DC" strokeWidth="3.5" strokeLinecap="round" fill="none" opacity=".7" />
      <circle cx="24" cy="24" r="6.5" fill="#fff" />
      <circle cx="24" cy="24" r="3.2" fill="#DFE6F1" />
    </>
  ),
  doc: (
    <>
      <rect x="9" y="6" width="30" height="36" rx="7" fill="#3562A6" />
      <path d="M9 14c0-4 3-8 7-8h8v36h-8c-4 0-7-3-7-7z" fill="#0A1E5A" opacity=".18" />
      <rect x="17" y="15" width="16" height="3.6" rx="1.8" fill="#fff" />
      <rect x="17" y="22.5" width="16" height="3.6" rx="1.8" fill="#fff" opacity=".85" />
      <rect x="17" y="30" width="10" height="3.6" rx="1.8" fill="#fff" opacity=".7" />
    </>
  ),
  shield: (
    <>
      <path d="M24 5l15 5.5v11c0 9-6 15.5-15 19.5C15 37 9 30.5 9 21.5v-11z" fill="#3562A6" />
      <path d="M24 5v36C15 37 9 30.5 9 21.5v-11z" fill="#6F93D8" opacity=".55" />
      <path d="M16.5 23.5l5 5 10-11" stroke="#fff" strokeWidth="4" strokeLinecap="round" strokeLinejoin="round" fill="none" />
    </>
  ),
  bot: (
    <>
      <path d="M24 6c10.5 0 18 6.8 18 15.5S34.5 37 24 37c-1.8 0-3.5-.2-5.1-.6L10 42l1.7-8.2C8.2 31.4 6 27.8 6 21.5 6 12.8 13.5 6 24 6z" fill="#3562A6" />
      <circle cx="16.5" cy="21.5" r="2.6" fill="#fff" />
      <circle cx="24" cy="21.5" r="2.6" fill="#fff" />
      <circle cx="31.5" cy="21.5" r="2.6" fill="#fff" />
    </>
  ),
}

export default function CuteIcon({ name, size = 28 }) {
  return (
    <svg className="cute" width={size} height={size} viewBox="0 0 48 48" aria-hidden="true">
      {PATHS[name]}
    </svg>
  )
}
