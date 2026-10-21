// 내 문의 내역 (CSA-39 · 조수빈 / API 연결 CSA-61). 상태와 상담원이 보낸 회신을 보여 주고,
// 추가정보 요청을 받았으면 같은 문의로 회신을 보낸다 (thread_ref). 10초마다 새로 읽는다.
import { useEffect, useState } from "react";
import { api, type CustomerInquiry, type CustomerStatus } from "../../api/client";
import { myInquiries } from "../../lib/myInquiries";

const STATUS_LABEL: Record<CustomerStatus, string> = {
  RECEIVED: "접수",
  IN_PROGRESS: "검토 중",
  WAITING_CUSTOMER: "추가 정보 요청",
  ANSWERED: "답변 완료",
  CLOSED: "종료",
};
const REFRESH_MS = 10_000;

export default function MyInquiries() {
  const [rows, setRows] = useState<CustomerInquiry[]>([]);
  const [error, setError] = useState<string | null>(null);

  const load = async () => {
    try {
      const found = await Promise.all(myInquiries().map((m) => api.customerInquiry(m.ticket_id).catch(() => null)));
      setRows(found.filter((x): x is CustomerInquiry => x !== null));
      setError(null);
    } catch (e) {
      setError(String(e));
    }
  };

  useEffect(() => {
    load();
    const timer = setInterval(load, REFRESH_MS);
    return () => clearInterval(timer);
  }, []);

  return (
    <section style={{ padding: 16 }}>
      <h2>내 문의 내역</h2>
      {error && <p style={{ color: "red" }}>{error}</p>}
      {!rows.length && <p>아직 낸 문의가 없습니다.</p>}
      {rows.map((r) => (
        <InquiryRow key={r.ticket_id} row={r} onReplied={load} />
      ))}
    </section>
  );
}

function InquiryRow({ row, onReplied }: { row: CustomerInquiry; onReplied: () => void }) {
  const [reply, setReply] = useState("");
  const [sending, setSending] = useState(false);
  const threadRef = myInquiries().find((m) => m.ticket_id === row.ticket_id)?.thread_ref;

  const send = async () => {
    if (!reply.trim() || !threadRef) return;
    setSending(true);
    try {
      await api.createInquiry({ channel: "WEB_FORM", subject: row.subject, body: reply, thread_ref: threadRef });
      setReply("");
      onReplied();
    } finally {
      setSending(false);
    }
  };

  return (
    <article style={{ border: "1px solid #ddd", borderRadius: 6, padding: 12, marginBottom: 12 }}>
      <header style={{ display: "flex", justifyContent: "space-between" }}>
        <b>{row.subject || row.body.slice(0, 40)}</b>
        <span>{STATUS_LABEL[row.status]}</span>
      </header>
      <small>
        {row.ticket_id}
        {row.received_at ? ` · ${new Date(row.received_at).toLocaleString()}` : ""}
      </small>
      {row.message && <p style={{ whiteSpace: "pre-wrap", background: "#f6f8fa", padding: 8 }}>{row.message}</p>}
      {row.status === "WAITING_CUSTOMER" && threadRef && (
        <div style={{ display: "flex", gap: 8 }}>
          <textarea value={reply} onChange={(e) => setReply(e.target.value)} rows={3} style={{ flex: 1 }} />
          <button onClick={send} disabled={sending || !reply.trim()}>
            {sending ? "보내는 중…" : "추가 정보 보내기"}
          </button>
        </div>
      )}
    </article>
  );
}
