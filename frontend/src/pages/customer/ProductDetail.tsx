// 제품 상세 탭: 정보 · 설치 · 고장 · 펌웨어 · FAQ · 문서 (CSA-37 · 조수빈)
import { useEffect, useState } from "react";
import { api } from "../../api/client";

const TAB_LABELS: Record<string, string> = {
  info: "제품 정보", install: "설치 가이드", faults: "자주 발생하는 고장",
  firmware: "펌웨어", faq: "FAQ", docs: "문서 자료실",
};

type Props = { code: string; tab: string; anchor: string | null; onTab: (t: string) => void };

export default function ProductDetail({ code, tab, anchor, onTab }: Props) {
  const [product, setProduct] = useState<{ name: string; tabs: string[] } | null>(null);
  useEffect(() => { api.product(code).then(setProduct).catch(console.error); }, [code]);
  if (!product) return null;

  return (
    <section>
      <h2>{product.name}</h2>
      <div style={{ display: "flex", gap: 8 }}>
        {product.tabs.map((t) => (
          <button key={t} onClick={() => onTab(t)} disabled={t === tab}>{TAB_LABELS[t] ?? t}</button>
        ))}
      </div>
      {/* TODO(CSA-37): 탭별 내용 (사양표, 설치 절, 고장 코드표, 펌웨어 이력, FAQ, 문서 목록) */}
      <p>탭: {TAB_LABELS[tab] ?? tab}{anchor ? ` · 강조: ${anchor}` : ""}</p>
    </section>
  );
}
