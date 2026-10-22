// 우측 챗봇 창 + 대시보드 이동 연동 (CSA-38 · 조수빈)
// POST /api/chat (CSA-32) 응답의 화면 이동 지시(navigation)를 대시보드에 넘기고, 문의 전환(handoff)이면 문의서를 연다.
//  - 보고 있는 제품(viewingProduct)을 매 요청에 실어 다음 대화의 맥락으로 쓴다
//  - 제품을 모르고 제품군만 알면 navigation.candidates 를 "제품 선택" 버튼으로 보여 준다
//  - 답변 아래에 참고 문서(evidence)와, 챗봇이 더 물어본 항목(ask_fields)을 보여 준다
//  - [해결 안 됐어요]는 바로 문의 전환(unresolved)
import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";
import { api, type Evidence, type InquiryForm, type Navigation } from "../../api/client";
import "./chat-panel.css";

type Props = {
  viewingProduct: string | null;
  onNavigate: (nav: Navigation) => void;
  onHandoff: (form: InquiryForm) => void;
  onPickProduct?: (code: string) => void;
};
type Message = {
  id: string;
  role: "user" | "assistant";
  text: string;
  evidence?: Evidence[];
  askFields?: string[];
  candidates?: string[];
  form?: InquiryForm; // 문의 전환 — 문의서 다시 열기
  retry?: { text: string; unresolved: boolean }; // 실패 — 같은 말을 다시 보내기
};

const UNRESOLVED_TEXT = "해결이 안 됐어요";
const WELCOME = "안녕하세요! 궁금한 걸 편하게 적어 주세요. 아래에서 골라도 돼요.";
const QUICK = ["화면에 E.OC가 떠요", "보증 기간이 남았나요?", "설치 설명서가 필요해요"];
const STORE = "cs-chat-v1"; // 새로고침해도 같은 대화로 이어가려고 세션 ID와 화면 기록을 브라우저에 둔다

// 챗봇이 더 물어보는 항목 이름 (기준표 info_field_codebook 의 항목 → 쉬운 말)
const FIELD_KO: Record<string, string> = {
  product_model: "제품 모델명", serial_no: "시리얼 번호", error_code: "에러 코드·증상", operating_condition: "고장 당시 운전 조건",
  photos: "제품·명판 사진", site_condition: "설치 환경", wiring_diagram: "배선도", application: "사용 용도", purchase_doc: "PO·송장 번호",
  install_date: "설치·시운전 날짜", failure_description: "고장 내용", po_number: "PO 번호", quantity: "수량", required_date: "희망 납기일",
  incoterms: "인도 조건", document_type: "필요한 문서", target_standard: "필요한 규격·인증", target_country: "사용 국가", current_fw: "현재 펌웨어",
  tool_version: "툴 버전", return_reason: "반품 사유", packaging_condition: "포장 상태", logs: "이벤트·트립 기록",
};

type Saved = { sessionId: string; messages: Message[] };
function load(): Saved {
  try {
    const raw = sessionStorage.getItem(STORE);
    if (raw) return JSON.parse(raw) as Saved;
  } catch { /* 저장소를 못 쓰면 새 대화로 시작 */ }
  return { sessionId: crypto.randomUUID(), messages: [] };
}

export default function ChatPanel({ viewingProduct, onNavigate, onHandoff, onPickProduct }: Props) {
  const saved = useMemo(load, []);
  const [sessionId] = useState(saved.sessionId);
  const [messages, setMessages] = useState<Message[]>(saved.messages);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [names, setNames] = useState<Record<string, string>>({});
  const bodyRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    try { sessionStorage.setItem(STORE, JSON.stringify({ sessionId, messages })); } catch { /* 무시 */ }
    bodyRef.current?.scrollTo({ top: bodyRef.current.scrollHeight, behavior: "smooth" });
  }, [sessionId, messages]);

  // "제품 선택" 버튼에 제품 이름을 보여 주려고 트리를 한 번 읽는다 (실패하면 코드로 보여 준다)
  useEffect(() => {
    api.productTree()
      .then((tree) => setNames(Object.fromEntries(tree.flatMap((d) => d.families.flatMap((f) => f.products.map((p) => [p.code, p.name]))))))
      .catch(() => undefined);
  }, []);

  const push = (m: Omit<Message, "id">) => setMessages((list) => [...list, { ...m, id: crypto.randomUUID() }]);

  const send = async (raw: string, unresolved = false, isRetry = false) => {
    const text = (unresolved ? raw.trim() || UNRESOLVED_TEXT : raw).trim();
    if (!text || busy) return;
    setInput("");
    if (isRetry) setMessages((list) => list.filter((m) => !m.retry));
    else push({ role: "user", text });
    setBusy(true);
    try {
      const reply = await api.chat({ session_id: sessionId, message: text, viewing_product: viewingProduct, unresolved });
      push({
        role: "assistant", text: reply.answer, evidence: reply.evidence, askFields: reply.ask_fields,
        candidates: reply.navigation.candidates, form: reply.handoff && reply.form ? reply.form : undefined,
      });
      onNavigate(reply.navigation);
      if (reply.handoff && reply.form) onHandoff(reply.form);
    } catch (e) {
      const rate = e instanceof Error && e.message.startsWith("429");
      push({
        role: "assistant",
        text: rate ? "요청이 많아서 잠깐 쉬고 있어요. 잠시 뒤에 다시 보내 주세요." : "답변을 가져오지 못했어요. 입력한 내용은 그대로예요. 다시 시도해 주세요.",
        retry: { text, unresolved },
      });
    } finally {
      setBusy(false);
    }
  };

  const onKey = (e: KeyboardEvent<HTMLInputElement>) => {
    // 한글 입력 중(조합 중) Enter 는 글자 확정이라 보내지 않는다
    if (e.key === "Enter" && !e.nativeEvent.isComposing) { e.preventDefault(); void send(input); }
  };

  return (
    <aside className="cp" aria-label="AI 상담">
      <header className="cp-head">
        <span className="cp-av" aria-hidden="true">⚡</span>
        <div><b>AI 상담</b><small>{viewingProduct ? `보고 있는 제품 · ${names[viewingProduct] ?? viewingProduct}` : "보통 바로 답해요"}</small></div>
      </header>

      <div className="cp-body" ref={bodyRef} aria-live="polite">
        <div className="cp-bub">{WELCOME}</div>
        {messages.length === 0 && (
          <div className="cp-chips">{QUICK.map((q) => <button key={q} type="button" onClick={() => void send(q)} disabled={busy}>{q}</button>)}</div>
        )}
        {messages.map((m) => (
          <div key={m.id} className={`cp-msg ${m.role}`}>
            <div className="cp-bub">{m.text}</div>
            {m.candidates && m.candidates.length > 0 && (
              <div className="cp-cands"><small>어떤 제품인가요?</small>
                {m.candidates.map((c) => <button key={c} type="button" onClick={() => onPickProduct?.(c)}>{names[c] ?? c}</button>)}</div>
            )}
            {m.evidence && m.evidence.length > 0 && (
              <div className="cp-ev"><small>📄 참고한 문서</small>
                {m.evidence.map((e, i) => <span key={`${e.doc_id}-${e.section}-${i}`}>{e.doc_id}{e.section ? ` §${e.section}` : ""}</span>)}</div>
            )}
            {m.askFields && m.askFields.length > 0 && (
              <p className="cp-ask">💡 알려 주시면 더 정확해요: {m.askFields.map((f) => FIELD_KO[f] ?? f).join(", ")}</p>
            )}
            {m.form && <button type="button" className="cp-go" onClick={() => onHandoff(m.form as InquiryForm)}>📝 문의서 열기</button>}
            {m.retry && <button type="button" className="cp-go" disabled={busy} onClick={() => void send(m.retry?.text ?? "", m.retry?.unresolved, true)}>다시 시도</button>}
          </div>
        ))}
        {busy && <div className="cp-msg assistant"><div className="cp-bub cp-typing" role="status" aria-label="답변을 쓰는 중"><i /><i /><i /></div></div>}
      </div>

      <div className="cp-in">
        {messages.some((m) => m.role === "assistant") && (
          <button type="button" className="cp-unres" onClick={() => void send(input, true)} disabled={busy}>해결 안 됐어요</button>
        )}
        <div className="cp-box">
          <input value={input} onChange={(e) => setInput(e.target.value)} onKeyDown={onKey} placeholder="메시지를 입력하세요" aria-label="메시지" disabled={busy} />
          <button type="button" aria-label="보내기" onClick={() => void send(input)} disabled={busy || !input.trim()}>↑</button>
        </div>
        <p>대화한 내용은 문의서에 자동으로 들어가요.</p>
      </div>
    </aside>
  );
}
