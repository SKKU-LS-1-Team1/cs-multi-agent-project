// 고객 화면: 좌측 제품 대시보드 + 우측 챗봇 (기획서 5.1). 챗봇 응답의 이동 지시로 대시보드가 바뀐다.
// 왼쪽 제품 목록은 처음엔 접혀 있고(얇은 막대) 눌러서 펼친다. 첫 화면은 본문의 제품 사진 고르기.
// 화면 폭에 맞춰 바뀐다 (shell.css): 넓으면 목록 · 본문 · 챗봇, 좁으면(휴대폰) 목록을 빼고
// 본문만 두고 챗봇은 오른쪽 아래 버튼으로 여는 서랍.
import { useState } from "react";
import type { InquiryForm as FormDraft, Navigation } from "../../api/client";
import ProductTree from "./ProductTree";
import ProductPicker from "./ProductPicker";
import ProductDetail from "./ProductDetail";
import ChatPanel from "./ChatPanel";
import InquiryForm from "./InquiryForm";

export default function CustomerHome() {
  const [productCode, setProductCode] = useState<string | null>(null);
  const [tab, setTab] = useState("info");
  const [anchor, setAnchor] = useState<string | null>(null);
  const [form, setForm] = useState<FormDraft | null>(null);
  const [chatOpen, setChatOpen] = useState(false); // 좁은 화면에서만 쓴다
  const [treeOpen, setTreeOpen] = useState(false);
  const [focus, setFocus] = useState<{ family: string; n: number } | null>(null);

  const onNavigate = (nav: Navigation) => {
    if (nav.product_code) setProductCode(nav.product_code);
    if (nav.tab && nav.tab !== "tree") setTab(nav.tab);
    setAnchor(nav.anchor);
  };
  const pick = (c: string) => { setProductCode(c); setTab("info"); setAnchor(null); setForm(null); };
  // 문의서가 열리면 서랍을 닫아 문의서가 보이게 한다
  const openForm = (f: FormDraft) => { setForm(f); setChatOpen(false); };
  // 목록에서 제품군 이름을 누르면 본문 캐러셀을 그 제품군으로 돌린다. 제품 상세를 보고 있었으면
  // 고르기 화면으로 돌아간다. 문의서를 쓰는 중이면 그대로 둔다 (쓰던 내용을 잃지 않게).
  const focusFamily = (family: string) => {
    if (form) return;
    setProductCode(null); setAnchor(null);
    setFocus((f) => ({ family, n: (f?.n ?? 0) + 1 }));
  };

  return (
    <div className={`cs-home${chatOpen ? " is-chat" : ""}${treeOpen ? " is-tree" : ""}`}>
      <div className="cs-side">
        <button type="button" className="cs-side-btn" aria-controls="cs-tree" aria-expanded={treeOpen} onClick={() => setTreeOpen((o) => !o)}>
          <span aria-hidden="true">{treeOpen ? "«" : "☰"}</span>
          <span>{treeOpen ? "목록 접기" : "제품 목록"}</span>
        </button>
        {treeOpen && <ProductTree id="cs-tree" selected={productCode} onSelect={(c) => { setProductCode(c); setForm(null); }} onFamily={focusFamily} />}
      </div>
      <main className="cs-main">
        {form ? (
          <InquiryForm draft={form} onDone={() => setForm(null)} />
        ) : productCode ? (
          <>
            <button type="button" className="cs-back" onClick={() => { setProductCode(null); setAnchor(null); }}>← 다른 제품 보기</button>
            <ProductDetail code={productCode} tab={tab} anchor={anchor} onTab={setTab} />
          </>
        ) : (
          <ProductPicker selected={productCode} focus={focus} onSelect={(c) => { setProductCode(c); setForm(null); }} />
        )}
      </main>
      <div className="cs-chat" id="cs-chat">
        <button type="button" className="cs-chat-close" onClick={() => setChatOpen(false)} aria-label="상담 창 닫기">✕</button>
        <ChatPanel viewingProduct={productCode} tab={tab} onReset={() => setForm(null)} onNavigate={onNavigate} onHandoff={openForm} onPickProduct={(c) => { pick(c); setChatOpen(false); }} />
      </div>
      <button type="button" className="cs-fab" aria-controls="cs-chat" aria-expanded={chatOpen} onClick={() => setChatOpen(true)}>
        <span aria-hidden="true">💬</span> AI 상담
      </button>
    </div>
  );
}
