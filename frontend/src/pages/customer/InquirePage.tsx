// 문의 남기기 — 메뉴에서 직접 들어오는 화면 (/inquire) (CSA-39 · 조수빈).
// 챗봇을 거치지 않고 문의할 때: 유형 → 제품을 고르면 그 유형·제품군의 필수 항목(기준표 required_info.csv)으로
// 문의서를 만들어 InquiryForm 에 넘긴다. 문의서 자체(입력·제출)는 챗봇에서 넘어올 때와 같은 화면이다.
import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import type { InquiryForm as FormDraft } from "../../api/client";
import { REQUIRED_INFO } from "../../lib/requiredInfo";
import InquiryForm from "./InquiryForm";
import { CATEGORY_KO } from "./labels";
import { familyName } from "./productFamilies";
import { useProductTree } from "./useProductTree";
import "./inquire.css";

// 고객이 알아보기 쉬운 순서와 설명
const TYPES: { id: string; sub: string }[] = [
  { id: "DEFECT", sub: "제품이 멈췄거나 이상해요" },
  { id: "INSTALL", sub: "설치나 시운전이 궁금해요" },
  { id: "TECH_SPEC", sub: "제품 사양이 궁금해요" },
  { id: "MANUAL", sub: "설명서나 데이터시트가 필요해요" },
  { id: "COMPLIANCE", sub: "인증서나 규격이 필요해요" },
  { id: "FW_UPDATE", sub: "펌웨어 업데이트가 필요해요" },
  { id: "WARRANTY", sub: "보증 적용을 확인하고 싶어요" },
  { id: "RETURN", sub: "교환이나 반품을 하고 싶어요" },
  { id: "ORDER_LEAD", sub: "주문이나 납기를 확인하고 싶어요" },
  { id: "QUOTE", sub: "견적을 받고 싶어요" },
];

// 제품군을 모르거나 기준표에 없으면 제품 모델만 필수로 묻는다 (기준표에 없는 조합에 항목을 지어내지 않는다)
const FALLBACK = ["product_model"];

export default function InquirePage() {
  const nav = useNavigate();
  const { tree, loading, error, reload } = useProductTree();
  const [type, setType] = useState<string | null>(null);
  const [family, setFamily] = useState<string | null | undefined>(undefined); // undefined: 아직 안 고름, null: 모름
  const [product, setProduct] = useState<string | null | undefined>(undefined);

  const families = useMemo(() => tree.flatMap((d) => d.families.map((f) => ({ ...f, division: d.label }))), [tree]);
  const chosen = families.find((f) => f.family === family);

  const draft: FormDraft | null = useMemo(() => {
    if (!type || family === undefined || (family && product === undefined)) return null;
    const keys = (family && REQUIRED_INFO[family]?.[type]?.map((f) => f.key)) || FALLBACK;
    return { category: type, product_code: product ?? null, fields: {}, missing_required: keys, subject: "", body: "" };
  }, [type, family, product]);

  if (draft) {
    return (
      <section className="cs-page iq-page">
        <button type="button" className="cs-back" onClick={() => (product !== undefined ? setProduct(undefined) : setFamily(undefined))}>← 이전</button>
        <InquiryForm draft={draft} onDone={() => nav("/")} />
      </section>
    );
  }

  return (
    <section className="cs-page iq-page">
      {!type ? (
        <>
          <h2>어떤 문의를 남기실래요?</h2>
          <p className="cs-muted">가장 가까운 것을 골라 주세요. 고르면 필요한 정보를 알려 드려요.</p>
          <ul className="iq-list">
            {TYPES.map((t) => (
              <li key={t.id}>
                <button type="button" className="iq-opt" onClick={() => setType(t.id)}>
                  <span><b>{CATEGORY_KO[t.id]}</b><small>{t.sub}</small></span>
                  <span aria-hidden="true">›</span>
                </button>
              </li>
            ))}
          </ul>
        </>
      ) : family === undefined ? (
        <>
          <button type="button" className="cs-back" onClick={() => setType(null)}>← 이전</button>
          <h2>어떤 제품인가요?</h2>
          <p className="cs-muted">{CATEGORY_KO[type]} · 제품군을 골라 주세요.</p>
          {loading && <p className="cs-muted" role="status">제품 목록을 불러오는 중이에요…</p>}
          {error && (
            <p className="cs-err" role="alert">
              제품 목록을 불러오지 못했어요. <button type="button" className="iq-link" onClick={reload}>다시 시도</button>
            </p>
          )}
          {tree.map((d) => (
            <div key={d.division} className="iq-group">
              <h3>{d.label}</h3>
              <ul className="iq-chips">
                {d.families.map((f) => (
                  <li key={f.family}><button type="button" className="iq-chip" onClick={() => setFamily(f.family)}>{familyName(f.family, f.label)}</button></li>
                ))}
              </ul>
            </div>
          ))}
          <div className="cs-actions">
            <button type="button" className="cs-btn is-ghost" onClick={() => setFamily(null)}>제품을 잘 모르겠어요</button>
          </div>
        </>
      ) : (
        <>
          <button type="button" className="cs-back" onClick={() => setFamily(undefined)}>← 이전</button>
          <h2>어떤 모델인가요?</h2>
          <p className="cs-muted">{chosen ? familyName(chosen.family, chosen.label) : ""} · 모델을 골라 주세요.</p>
          <ul className="iq-list">
            {chosen?.products.map((p) => (
              <li key={p.code}>
                <button type="button" className="iq-opt" onClick={() => setProduct(p.code)}>
                  <span><b>{p.name}</b><small>{p.code}</small></span>
                  <span aria-hidden="true">›</span>
                </button>
              </li>
            ))}
            <li>
              <button type="button" className="iq-opt is-ghost" onClick={() => setProduct(null)}>
                <span><b>모델을 잘 모르겠어요</b><small>{chosen ? familyName(chosen.family, chosen.label) : ""}로 문의할게요</small></span>
                <span aria-hidden="true">›</span>
              </button>
            </li>
          </ul>
        </>
      )}
    </section>
  );
}
