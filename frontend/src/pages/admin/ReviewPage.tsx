// 추천 답변 검토·승인·수정·반려 + 수정 사유 입력 (CSA-41 · 김도연)
import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { api, type ReviewAction, type Ticket } from "../../api/client";
import EvidencePanel from "./EvidencePanel";

const REASONS = [
  ["FACT_ERROR", "사실 오류"],
  ["WEAK_EVIDENCE", "근거 부족"],
  ["TONE", "표현·어조"],
  ["ROUTING_ERROR", "분류·담당 오류"],
] as const;

export default function ReviewPage() {
  const { ticketId = "" } = useParams();
  const [ticket, setTicket] = useState<Ticket | null>(null);
  const [text, setText] = useState("");
  const [feedback, setFeedback] = useState("");
  const [reason, setReason] = useState<string | null>(null);

  useEffect(() => {
    api.ticket(ticketId).then((t) => { setTicket(t); setText(t.draft?.text ?? t.info_request ?? ""); });
  }, [ticketId]);
  if (!ticket) return null;

  const act = async (action: ReviewAction) => {
    const original = ticket.draft?.text ?? ticket.info_request ?? "";
    const edited = text !== original;
    const t = await api.act(ticketId, {
      action: action === "approve" && edited ? "edit_approve" : action,
      edited_text: edited ? text : null,
      feedback: feedback || null,
      feedback_reason: reason,
    });
    setTicket(t);
    setText(t.draft?.text ?? t.info_request ?? "");
  };

  return (
    <div style={{ display: "grid", gridTemplateColumns: "1fr 360px", gap: 16, padding: 16 }}>
      <section>
        <h2>{ticket.ticket_id} · {ticket.category} · {ticket.priority} · {ticket.assigned_dept}</h2>
        <p>상태: {ticket.status}</p>
        <textarea value={text} onChange={(e) => setText(e.target.value)} rows={12} style={{ width: "100%" }} />
        <div style={{ display: "flex", gap: 8, margin: "8px 0" }}>
          {REASONS.map(([k, label]) => (
            <button key={k} onClick={() => setReason(k)} disabled={reason === k}>{label}</button>
          ))}
        </div>
        <input placeholder="AI에게 피드백 한 줄" value={feedback} onChange={(e) => setFeedback(e.target.value)} style={{ width: "100%" }} />
        <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
          <button onClick={() => act("approve")}>승인 및 발송</button>
          <button onClick={() => act("rewrite")}>AI 재작성 요청</button>
          <button onClick={() => act("info_request")}>추가정보 요청문 작성</button>
          <button onClick={() => act("escalate")}>전문부서 이관</button>
          <button onClick={() => act("reject")}>반려</button>
        </div>
      </section>
      <EvidencePanel evidence={ticket.evidence} checks={ticket.checks} />
    </div>
  );
}
