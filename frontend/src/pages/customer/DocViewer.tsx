// 근거 원문 보기: 문서의 절을 제목·절 번호로 보여 주고 요청한 절을 강조한다 (페이지 번호는 쓰지 않는다 — Markdown 문서).
// doc 을 직접 주면 그대로 쓰고, docId 만 주면 /api/products/{code}/docs/{docId} 로 읽는다.
import { useEffect, useRef, useState } from "react";
import { api, type ProductDocument } from "../../api/client";
import MarkdownText from "./MarkdownText";

type Props = { code: string; docId?: string; doc?: ProductDocument; section?: string | null; onClose?: () => void };

const cache = new Map<string, ProductDocument>();

export default function DocViewer({ code, docId, doc: given, section = null, onClose }: Props) {
  const [doc, setDoc] = useState<ProductDocument | null>(given ?? null);
  const [error, setError] = useState<string | null>(null);
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (given) { setDoc(given); return; }
    if (!docId) return;
    const key = `${code}/${docId}`;
    const hit = cache.get(key);
    if (hit) { setDoc(hit); setError(null); return; }
    let alive = true;
    setDoc(null); setError(null);
    api.productDocument(code, docId)
      .then((d) => { cache.set(key, d); if (alive) setDoc(d); })
      .catch((e: unknown) => { if (alive) setError(e instanceof Error ? e.message : String(e)); });
    return () => { alive = false; };
  }, [code, docId, given]);

  useEffect(() => {
    if (!doc || !box.current) return;
    const el = section ? box.current.querySelector<HTMLElement>(`[data-section="${CSS.escape(section)}"]`) : null;
    (el ?? box.current).scrollIntoView({ block: el ? "center" : "nearest", behavior: "smooth" });
  }, [doc, section]);

  return (
    <div className="pd-doc" ref={box}>
      <div className="pd-doc-head">
        <span>📄 {doc ? `${doc.doc_id} · Rev. ${doc.revision}` : docId ?? given?.doc_id}</span>
        {onClose && <button type="button" onClick={onClose} aria-label="원문 닫기">닫기</button>}
      </div>
      {error && <p className="pd-note" role="alert">원문을 불러오지 못했어요. ({error})</p>}
      {!doc && !error && <p className="pd-note">원문을 불러오는 중이에요…</p>}
      {doc && <h4>{doc.title}</h4>}
      {doc?.sections.map((s) => (
        <section key={s.section} data-section={s.section} className={s.section === section ? "is-hit" : undefined}>
          <h5>{s.section} {s.title}</h5>
          <MarkdownText text={s.text} />
        </section>
      ))}
      {doc && doc.sections.length === 0 && <p className="pd-note">이 문서는 절 내용이 없어요.</p>}
    </div>
  );
}
