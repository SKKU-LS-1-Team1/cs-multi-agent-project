// 우측 챗봇 창 + 대시보드 이동 연동 (CSA-38 · 조수빈)
// POST /api/chat (CSA-32) 응답의 화면 이동 지시(navigation)를 대시보드에 넘기고, 문의 전환(handoff)이면 문의서를 연다.
//  - 보고 있는 제품(viewingProduct)을 매 요청에 실어 다음 대화의 맥락으로 쓴다
//  - 제품을 모르고 제품군만 알면 navigation.candidates 를 "제품 선택" 버튼으로 보여 준다
//  - 답변 아래에 참고 문서(evidence)와, 챗봇이 더 물어본 항목(ask_fields)을 보여 준다
//  - [해결 안 됐어요]는 바로 문의 전환(unresolved)
import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";
import { api, type Evidence, type InquiryForm, type Navigation } from "../../api/client";
import ContextCard from "./ContextCard";
import { fieldLabel } from "./labels";
import { familyName } from "./productFamilies";
import "./chat-panel.css";

// 상세 화면 탭 이름 (ProductDetail 과 같다) — 상담 중인 제품 카드의 "보고 있는 화면"
const TAB_KO: Record<string, string> = { info: "제품 정보", install: "설치 가이드", faults: "자주 발생하는 고장", firmware: "펌웨어", faq: "FAQ", docs: "문서 자료실" };

type Props = {
  viewingProduct: string | null;
  tab?: string; // 지금 보고 있는 상세 탭
  onReset?: () => void; // 대화 초기화 때 화면 쪽에 남은 챗봇 임시 정보(문의서 초안)를 비운다
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
const WELCOME = "안녕하세요! 궁금한 걸 편한 언어로 적어 주세요. 아래에서 골라도 돼요.";
const QUICK = ["화면에 E.OC가 떠요", "보증 기간이 남았나요?", "설치 설명서가 필요해요"];
const STORE = "cs-chat-v1"; // 새로고침해도 같은 대화로 이어가려고 세션 ID와 화면 기록을 브라우저에 둔다

type Saved = { sessionId: string; messages: Message[] };
function load(): Saved {
  try {
    const raw = sessionStorage.getItem(STORE);
    if (raw) return JSON.parse(raw) as Saved;
  } catch { /* 저장소를 못 쓰면 새 대화로 시작 */ }
  return { sessionId: crypto.randomUUID(), messages: [] };
}

export default function ChatPanel({ viewingProduct, tab, onNavigate, onHandoff, onPickProduct, onReset }: Props) {
  const saved = useMemo(load, []);
  const [sessionId, setSessionId] = useState(saved.sessionId);
  const [messages, setMessages] = useState<Message[]>(saved.messages);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [names, setNames] = useState<Record<string, string>>({});
  const [families, setFamilies] = useState<Record<string, string>>({}); // 제품 코드 → 제품군 이름
  const [confirm, setConfirm] = useState(false); // 대화 초기화 확인창
  const bodyRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    try { sessionStorage.setItem(STORE, JSON.stringify({ sessionId, messages })); } catch { /* 무시 */ }
    bodyRef.current?.scrollTo({ top: bodyRef.current.scrollHeight, behavior: "smooth" });
  }, [sessionId, messages]);

  // "제품 선택" 버튼에 제품 이름을 보여 주려고 트리를 한 번 읽는다 (실패하면 코드로 보여 준다)
  useEffect(() => {
    api.productTree()
      .then((tree) => {
        const products = tree.flatMap((d) => d.families.flatMap((f) => f.products.map((p) => ({ code: p.code, name: p.name, family: familyName(f.family, f.label) }))));
        setNames(Object.fromEntries(products.map((p) => [p.code, p.name])));
        setFamilies(Object.fromEntries(products.map((p) => [p.code, p.family])));
      })
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

  // 대화 내역·입력·서버 쪽 대화 맥락(세션)을 비운다. 화면에서 고른 제품·탭과 이미 낸 문의는 그대로 둔다.
  const reset = () => {
    setSessionId(crypto.randomUUID()); // 새 세션이라 서버에 쌓인 이전 대화가 이어지지 않는다
    setMessages([]);
    setInput("");
    setConfirm(false);
    onReset?.();
  };

  const onKey = (e: KeyboardEvent<HTMLInputElement>) => {
    // 한글 입력 중(조합 중) Enter 는 글자 확정이라 보내지 않는다
    if (e.key === "Enter" && !e.nativeEvent.isComposing) { e.preventDefault(); void send(input); }
  };

  return (
    <aside className="cp" aria-label="AI 상담">
      <header className="cp-head">
        <svg className="cp-av" width="30" height="30" viewBox="0 0 48 48" aria-hidden="true">
          <path d="M24 6c10.5 0 18 6.8 18 15.5S34.5 37 24 37c-1.8 0-3.5-.2-5.1-.6L10 42l1.7-8.2C8.2 31.4 6 27.8 6 21.5 6 12.8 13.5 6 24 6z" fill="#3562A6" />
          <circle cx="16.5" cy="21.5" r="2.6" fill="#fff" /><circle cx="24" cy="21.5" r="2.6" fill="#fff" /><circle cx="31.5" cy="21.5" r="2.6" fill="#fff" />
        </svg>
        <div className="cp-ht"><b>AI 상담</b><small>대화한 내용은 문의서에 자동으로 들어가요.</small></div>
        <button type="button" className="cp-reset" disabled={messages.length === 0} aria-haspopup="dialog" aria-expanded={confirm} onClick={() => setConfirm(true)}>대화 초기화</button>
      </header>

      {confirm && (
        <div className="cp-pop" role="alertdialog" aria-labelledby="cp-pop-t" onKeyDown={(e) => e.key === "Escape" && setConfirm(false)}>
          <b id="cp-pop-t">대화를 초기화할까요?</b>
          <p>대화가 지워져요. 보고 있는 제품은 유지돼요.</p>
          <div>
            <button type="button" className="cp-cancel" autoFocus onClick={() => setConfirm(false)}>취소</button>
            <button type="button" className="cp-ok" onClick={reset}>초기화</button>
          </div>
        </div>
      )}

      {viewingProduct && (
        <ContextCard family={families[viewingProduct] ?? null} name={names[viewingProduct] ?? viewingProduct} code={viewingProduct} screen={tab ? TAB_KO[tab] ?? null : null} />
      )}

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
              <p className="cp-ask">💡 알려 주시면 더 정확해요: {m.askFields.map(fieldLabel).join(", ")}</p>
            )}
            {m.form && <button type="button" className="cp-go" onClick={() => onHandoff(m.form as InquiryForm)}>문의서 열기</button>}
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
          <input value={input} onChange={(e) => setInput(e.target.value)} onKeyDown={onKey} placeholder="궁금한 점을 적어 주세요" aria-label="메시지" disabled={busy} />
          <button type="button" aria-label="보내기" onClick={() => void send(input)} disabled={busy || !input.trim()}>↑</button>
        </div>
      </div>
    </aside>
  );
}
