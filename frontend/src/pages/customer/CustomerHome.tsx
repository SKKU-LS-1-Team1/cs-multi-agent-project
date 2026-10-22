// 고객 화면: 좌측 제품 대시보드 + 우측 챗봇 (기획서 5.1). 챗봇 응답의 이동 지시로 대시보드가 바뀐다.
import { useState } from "react";
import type { InquiryForm as FormDraft, Navigation } from "../../api/client";
import ProductTree from "./ProductTree";
import ProductDetail from "./ProductDetail";
import ChatPanel from "./ChatPanel";
import InquiryForm from "./InquiryForm";

export default function CustomerHome() {
  const [productCode, setProductCode] = useState<string | null>(null);
  const [tab, setTab] = useState("info");
  const [anchor, setAnchor] = useState<string | null>(null);
  const [form, setForm] = useState<FormDraft | null>(null);

  const onNavigate = (nav: Navigation) => {
    if (nav.product_code) setProductCode(nav.product_code);
    if (nav.tab && nav.tab !== "tree") setTab(nav.tab);
    setAnchor(nav.anchor);
  };

  return (
    <div style={{ display: "grid", gridTemplateColumns: "260px 1fr 360px", height: "calc(100vh - 50px)" }}>
      <ProductTree selected={productCode} onSelect={(c) => { setProductCode(c); setForm(null); }} />
      <main style={{ padding: 16, overflow: "auto" }}>
        {form ? (
          <InquiryForm draft={form} onDone={() => setForm(null)} />
        ) : productCode ? (
          <ProductDetail code={productCode} tab={tab} anchor={anchor} onTab={setTab} />
        ) : (
          <p>왼쪽에서 제품을 고르거나 오른쪽 챗봇에 물어보세요.</p>
        )}
      </main>
      <ChatPanel viewingProduct={productCode} onNavigate={onNavigate} onHandoff={setForm} onPickProduct={(c) => { setProductCode(c); setTab("info"); setAnchor(null); setForm(null); }} />
    </div>
  );
}
