// 내 문의 내역 (CSA-39 · 조수빈 / API 연결 CSA-61). 상태와 상담원이 보낸 회신을 보여 주고,
// 추가정보 요청을 받았으면 같은 문의로 회신을 보낸다 (thread_ref). 10초마다 새로 읽는다.
// 상태는 단계(접수 → 검토 → 답변)로 보여 주고, 고객이 할 일이 있는 문의(답장 필요)를 맨 위에 둔다.
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, type CustomerInquiry, type CustomerStatus } from "../../api/client";
import { myInquiries } from "../../lib/myInquiries";
import { STATUS_LABEL } from "./labels";

const REFRESH_MS = 10_000;
const STEPS = ["접수", "검토", "답변"];
const STEP_OF: Record<CustomerStatus, number> = { RECEIVED: 0, IN_PROGRESS: 1, WAITING_CUSTOMER: 1, ANSWERED: 2, CLOSED: 2 };
// 날짜는 고객 브라우저의 언어·지역 형식으로
const when = (iso: string) => new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(new Date(iso));

export default function MyInquiries() {
  const [rows, setRows] = useState<CustomerInquiry[] | null>(null);
  const [error, setError] = useState(false);

  const load = async () => {
    try {
      const found = await Promise.all(myInquiries().map((m) => api.customerInquiry(m.ticket_id).catch(() => null)));
      const list = found.filter((x): x is CustomerInquiry => x !== null);
      list.sort((a, b) => Number(b.status === "WAITING_CUSTOMER") - Number(a.status === "WAITING_CUSTOMER"));
      setRows(list);
      setError(false);
    } catch {
      setError(true);
    }
  };

  useEffect(() => {
    load();
    const timer = setInterval(load, REFRESH_MS);
    return () => clearInterval(timer);
  }, []);

  return (
    <section className="cs-page">
      <h2>내 문의</h2>
      <p className="cs-muted">이 브라우저에서 보낸 문의예요. 답변이 오면 여기에 바로 보여요.</p>
      {error && <p className="cs-err" role="alert">문의 내역을 불러오지 못했어요. 잠시 뒤 자동으로 다시 시도해요.</p>}
      {rows === null && !error && <p className="cs-muted">불러오는 중이에요…</p>}
      {rows?.length === 0 && (
        <div className="cs-card cs-empty">
          <p>아직 보낸 문의가 없어요.</p>
          <p className="cs-muted">AI 상담에서 해결이 안 되면 문의서로 바로 넘어가요.</p>
          <Link to="/" className="cs-btn">제품 · 상담으로 가기</Link>
        </div>
      )}
      {rows?.map((r) => <InquiryRow key={r.ticket_id} row={r} onReplied={load} />)}
    </section>
  );
}

function InquiryRow({ row, onReplied }: { row: CustomerInquiry; onReplied: () => void }) {
  const [reply, setReply] = useState("");
  const [sending, setSending] = useState(false);
  const [failed, setFailed] = useState(false);
  const threadRef = myInquiries().find((m) => m.ticket_id === row.ticket_id)?.thread_ref;
  const step = STEP_OF[row.status];
  const waiting = row.status === "WAITING_CUSTOMER";

  const send = async () => {
    if (!reply.trim() || !threadRef) return;
    setSending(true); setFailed(false);
    try {
      await api.createInquiry({ channel: "WEB_FORM", subject: row.subject, body: reply, thread_ref: threadRef });
      setReply("");
      onReplied();
    } catch {
      setFailed(true);
    } finally {
      setSending(false);
    }
  };

  return (
    <article className={`cs-card cs-inq${waiting ? " is-wait" : ""}`}>
      <header>
        <b>{row.subject || row.body.slice(0, 60)}</b>
        <span className={`cs-badge s-${row.status}`}>{STATUS_LABEL[row.status]}</span>
      </header>
      <small className="cs-muted">접수 번호 {row.ticket_id}{row.received_at ? ` · ${when(row.received_at)}` : ""}</small>
      <ol className="cs-steps" aria-label={`진행 단계: ${STATUS_LABEL[row.status]}`}>
        {STEPS.map((s, i) => <li key={s} className={i <= step ? "is-on" : ""} aria-current={i === step ? "step" : undefined}>{s}</li>)}
      </ol>
      {row.message && (
        <div className="cs-reply">
          <small>{waiting ? "담당자가 추가 정보를 요청했어요" : "담당자 답변"}</small>
          <p>{row.message}</p>
        </div>
      )}
      {waiting && threadRef && (
        <div className="cs-field">
          <label htmlFor={`r-${row.ticket_id}`}>답장</label>
          <textarea id={`r-${row.ticket_id}`} value={reply} onChange={(e) => setReply(e.target.value)} rows={3} placeholder="요청받은 정보를 적어 주세요" />
          {failed && <small className="cs-err" role="alert">보내지 못했어요. 다시 눌러 주세요.</small>}
          <div className="cs-actions">
            <button type="button" className="cs-btn" onClick={send} disabled={sending || !reply.trim()}>
              {sending ? "보내는 중…" : "답장 보내기"}
            </button>
          </div>
        </div>
      )}
    </article>
  );
}
