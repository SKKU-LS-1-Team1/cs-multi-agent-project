// 문의하기 (자동 채움) (CSA-39 · 조수빈). 챗봇이 채운 칸을 확인하고 빈 필수 칸을 채워 보낸다.
// 칸 이름은 코드 대신 쉬운 말(labels.ts)로 보여 주고, 빈 칸은 보내기를 누른 뒤에 글로 알려 준다 (색만으로 알리지 않는다).
// 보내면 접수 번호와 '내 문의'로 가는 길을 보여 준다.
import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { api, type InquiryForm as FormDraft } from "../../api/client";
import { getCountry, getLang } from "../../lib/lang";
import { newThreadRef, rememberInquiry } from "../../lib/myInquiries";
import { CATEGORY_KO, FIELD_HINT, fieldLabel } from "./labels";

type Props = { draft: FormDraft; onDone: () => void };

export default function InquiryForm({ draft, onDone }: Props) {
  const [fields, setFields] = useState<Record<string, string>>(draft.fields);
  const [subject, setSubject] = useState(draft.subject);
  const [body, setBody] = useState(draft.body);
  const [tried, setTried] = useState(false); // 보내기를 한 번 눌렀는지 — 그 뒤부터 빈 칸을 알린다
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sent, setSent] = useState<string | null>(null); // 접수 번호
  const required = [...new Set([...Object.keys(draft.fields), ...draft.missing_required])];
  const empty = required.filter((k) => !fields[k]?.trim());
  const filled = required.length - empty.length;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setTried(true);
    if (empty.length > 0) {
      document.getElementById(`f-${empty[0]}`)?.focus();
      return;
    }
    setSending(true); setError(null);
    try {
      const threadRef = newThreadRef(); // 추가정보 요청에 회신할 때 같은 문의로 이어진다
      const ticket = await api.createInquiry({
        channel: "WEB_FORM",
        category: draft.category,
        product_code: draft.product_code,
        subject: subject.trim() || draft.subject,
        body,
        provided_fields: fields,
        thread_ref: threadRef,
        language: getLang(), // 온보딩에서 고른 언어 — 상담원 답변을 이 언어로 보낸다
        country: getCountry(), // 감지에 성공한 지원 국가만
      });
      rememberInquiry({ ticket_id: ticket.ticket_id, thread_ref: threadRef, subject: subject.trim() || draft.subject });
      setSent(ticket.ticket_id);
    } catch {
      setError("문의를 보내지 못했어요. 입력한 내용은 그대로 있으니 잠시 뒤 다시 보내 주세요.");
    } finally {
      setSending(false);
    }
  };

  if (sent) {
    return (
      <section className="cs-card cs-done" aria-live="polite">
        <div className="cs-done-ic" aria-hidden="true">✓</div>
        <h2>문의가 접수됐어요</h2>
        <p>접수 번호 <b>{sent}</b></p>
        <p className="cs-muted">담당자가 확인한 뒤 답변을 드려요. 진행 상황과 답변은 ‘내 문의’에서 볼 수 있어요.</p>
        <div className="cs-actions">
          <Link to="/my" className="cs-btn">내 문의 보기</Link>
          <button type="button" className="cs-btn is-ghost" onClick={onDone}>계속 둘러보기</button>
        </div>
      </section>
    );
  }

  return (
    <form className="cs-card cs-form" onSubmit={submit} noValidate>
      <h2>문의하기</h2>
      <p className="cs-muted">상담 내용을 바탕으로 미리 채워 두었어요. 확인하고 빈 칸만 채워 보내 주세요.</p>
      <div className="cs-tags">
        {draft.category && <span>유형 · {CATEGORY_KO[draft.category] ?? draft.category}</span>}
        <span>제품 · {draft.product_code ?? "아직 모름"}</span>
      </div>

      {required.length > 0 && (
        <fieldset>
          <legend>필요한 정보 <small>{filled}/{required.length} 입력됨</small></legend>
          {required.map((k) => {
            const missing = tried && !fields[k]?.trim();
            return (
              <div key={k} className={`cs-field${missing ? " is-err" : ""}`}>
                <label htmlFor={`f-${k}`}>{fieldLabel(k)} <em>필수</em></label>
                <input
                  id={`f-${k}`}
                  value={fields[k] ?? ""}
                  onChange={(e) => setFields({ ...fields, [k]: e.target.value })}
                  aria-invalid={missing}
                  aria-describedby={missing ? `e-${k}` : FIELD_HINT[k] ? `h-${k}` : undefined}
                />
                {missing ? <small id={`e-${k}`} className="cs-err">이 칸을 채워 주세요.</small>
                  : FIELD_HINT[k] && <small id={`h-${k}`}>{FIELD_HINT[k]}</small>}
              </div>
            );
          })}
        </fieldset>
      )}

      <div className="cs-field">
        <label htmlFor="f-subject">제목</label>
        <input id="f-subject" value={subject} onChange={(e) => setSubject(e.target.value)} />
      </div>
      <div className="cs-field">
        <label htmlFor="f-body">문의 내용</label>
        <textarea id="f-body" value={body} onChange={(e) => setBody(e.target.value)} rows={7} />
        <small>상담 대화가 들어가 있어요. 더 알려 줄 내용이 있으면 덧붙여 주세요.</small>
      </div>

      {tried && empty.length > 0 && <p className="cs-err" role="alert">필수 정보 {empty.length}개가 비어 있어요.</p>}
      {error && <p className="cs-err" role="alert">{error}</p>}
      <div className="cs-actions">
        <button type="submit" className="cs-btn" disabled={sending}>{sending ? "보내는 중…" : "문의 보내기"}</button>
        <button type="button" className="cs-btn is-ghost" onClick={onDone} disabled={sending}>취소</button>
      </div>
    </form>
  );
}
