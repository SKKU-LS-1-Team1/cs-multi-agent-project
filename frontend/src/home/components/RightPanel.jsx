import ChatPanel from './ChatPanel.jsx'

// 오른쪽 AI 상담. 화면이 어떻든 너비와 구성은 같다 — 긴 대화는 패널 안에서 줄바꿈·스크롤로 처리한다.
export default function RightPanel(chat) {
  return (
    <aside className="rp">
      <div className="rp-pane"><ChatPanel {...chat} /></div>
    </aside>
  )
}
