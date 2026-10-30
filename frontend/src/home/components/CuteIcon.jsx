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
  // 증상 단계 첨부용 (사진·영상·소리·QR)
  photo: (
    <>
      <rect x="16" y="8" width="16" height="10" rx="4" fill="#3562A6" />
      <rect x="4" y="13" width="40" height="29" rx="8" fill="#3562A6" />
      <path d="M4 21c0-4.4 3.6-8 8-8h6v29h-6c-4.4 0-8-3.6-8-8z" fill="#0A1E5A" opacity=".18" />
      <circle cx="24" cy="28" r="9.5" fill="#fff" />
      <circle cx="24" cy="28" r="5.8" fill="#6F93D8" />
      <circle cx="37" cy="20.5" r="2" fill="#fff" />
    </>
  ),
  video: (
    <>
      <rect x="4" y="12" width="30" height="24" rx="8" fill="#3562A6" />
      <path d="M4 20c0-4.4 3.6-8 8-8h5v24h-5c-4.4 0-8-3.6-8-8z" fill="#0A1E5A" opacity=".18" />
      <path d="M36 21l7.2-4.7a1.5 1.5 0 012.3 1.3v12.8a1.5 1.5 0 01-2.3 1.3L36 27z" fill="#6F93D8" />
      <path d="M17 18.5v11l9-5.5z" fill="#fff" stroke="#fff" strokeWidth="2.4" strokeLinejoin="round" />
    </>
  ),
  sound: (
    <>
      <rect x="16.5" y="5" width="15" height="25" rx="7.5" fill="#3562A6" />
      <path d="M16.5 12.5a7.5 7.5 0 017.5-7.5v25a7.5 7.5 0 01-7.5-7.5z" fill="#0A1E5A" opacity=".18" />
      <rect x="21" y="10" width="3.2" height="9" rx="1.6" fill="#fff" opacity=".7" />
      <path d="M10.5 23v1a13.5 13.5 0 0027 0v-1" stroke="#6F93D8" strokeWidth="3.8" strokeLinecap="round" fill="none" />
      <path d="M24 37.5V43M17.5 43h13" stroke="#6F93D8" strokeWidth="3.8" strokeLinecap="round" fill="none" />
    </>
  ),
  qr: (
    <>
      <rect x="5" y="5" width="16" height="16" rx="4.5" fill="#3562A6" />
      <rect x="10" y="10" width="6" height="6" rx="1.8" fill="#fff" />
      <rect x="27" y="5" width="16" height="16" rx="4.5" fill="#3562A6" />
      <rect x="32" y="10" width="6" height="6" rx="1.8" fill="#fff" />
      <rect x="5" y="27" width="16" height="16" rx="4.5" fill="#3562A6" />
      <rect x="10" y="32" width="6" height="6" rx="1.8" fill="#fff" />
      <rect x="27" y="27" width="7.5" height="7.5" rx="2.2" fill="#6F93D8" />
      <rect x="36" y="27" width="7" height="7.5" rx="2.2" fill="#3562A6" />
      <rect x="27" y="36" width="7.5" height="7" rx="2.2" fill="#3562A6" />
      <rect x="36" y="36" width="7" height="7" rx="2.2" fill="#6F93D8" />
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
