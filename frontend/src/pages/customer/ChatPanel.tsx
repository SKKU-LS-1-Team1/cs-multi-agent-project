// 우측 챗봇 창 + 대시보드 이동 연동 (CSA-38 · 조수빈)
import { useMemo, useState } from "react";
import { api, type InquiryForm, type Navigation } from "../../api/client";

type Props = {
  viewingProduct: string | null;
  onNavigate: (nav: Navigation) => void;
  onHandoff: (form: InquiryForm) => void;
};
type Message = { role: "user" | "assistant"; text: string };
const UNRESOLVED_TEXT = "해결이 안 됐어요";

export default function ChatPanel({ viewingProduct, onNavigate, onHandoff }: Props) {
  const sessionId = useMemo(() => crypto.randomUUID(), []);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");

  const send = async (unresolved = false) => {
    const text = unresolved ? input.trim() || UNRESOLVED_TEXT : input;
    if (!text.trim()) return;
    setInput("");
    setMessages((m) => [...m, { role: "user", text }]);
    const reply = await api.chat({ session_id: sessionId, message: text, viewing_product: viewingProduct, unresolved });
    setMessages((m) => [...m, { role: "assistant", text: reply.answer }]);
    onNavigate(reply.navigation);
    if (reply.handoff && reply.form) onHandoff(reply.form);
  };

  return (
    <aside style={{ borderLeft: "1px solid #ddd", display: "flex", flexDirection: "column", padding: 12 }}>
      <div style={{ flex: 1, overflow: "auto" }}>
        {messages.map((m, i) => (
          <p key={i} style={{ textAlign: m.role === "user" ? "right" : "left" }}>{m.text}</p>
        ))}
      </div>
      <div style={{ display: "flex", gap: 8 }}>
        <input value={input} onChange={(e) => setInput(e.target.value)} onKeyDown={(e) => e.key === "Enter" && send()} style={{ flex: 1 }} />
        <button onClick={() => send()}>보내기</button>
        {messages.length > 0 && <button onClick={() => send(true)}>해결 안 됐어요</button>}
      </div>
    </aside>
  );
}
