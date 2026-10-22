// 제품 상세 탭: 정보 · 설치 · 고장 · 펌웨어 · FAQ · 문서 (CSA-37 · 조수빈)
// 내용은 GET /api/products/{code} (CSA-60). 탭은 내용이 있는 것만 온다.
// 챗봇의 화면 이동 지시(tab · anchor)를 받아 해당 탭을 열고 anchor 항목을 강조한다:
//   faults[].error_code · info.specs[].attribute · install.sections[].section · docs[].doc_id ·
//   firmware.latest · lead_time(info.ordering) · policy(faq.policies)
import { useEffect, useRef, useState, type ReactNode } from "react";
import { api, type ProductDetail as Detail } from "../../api/client";
import DocViewer from "./DocViewer";
import MarkdownText from "./MarkdownText";
import "./product-detail.css";

type Tab = Detail["tabs"][number];
type Props = { code: string; tab: string; anchor: string | null; onTab: (t: string) => void };
// 근거 원문: 문서(docId) · 절(section). 설치·FAQ 정책은 응답에 이미 들어 있는 문서를 쓴다.
type Source = { docId: string; section: string | null };

const TAB_LABELS: Record<string, string> = {
  info: "📊 제품 정보", install: "🛠️ 설치 가이드", faults: "⚠️ 자주 발생하는 고장",
  firmware: "🔄 펌웨어", faq: "❓ FAQ", docs: "📄 문서 자료실",
};

function Row({ hit, children }: { hit?: boolean; children: ReactNode }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => { if (hit) ref.current?.scrollIntoView({ block: "center", behavior: "smooth" }); }, [hit]);
  return <div ref={ref} className={`pd-row${hit ? " is-hit" : ""}`}>{children}</div>;
}

export default function ProductDetail({ code, tab, anchor, onTab }: Props) {
  const [product, setProduct] = useState<Detail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [source, setSource] = useState<Source | null>(null);
  const [openFault, setOpenFault] = useState<string | null>(null);
  const [openSec, setOpenSec] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    setProduct(null); setError(null); setSource(null); setOpenFault(null); setOpenSec(null);
    api.product(code)
      .then((p) => { if (alive) setProduct(p); })
      .catch((e: unknown) => { if (alive) setError(e instanceof Error ? e.message : String(e)); });
    return () => { alive = false; };
  }, [code]);
  useEffect(() => { setSource(null); }, [tab]);
  // 챗봇이 가리킨 고장 · 설치 절은 처음부터 펼쳐 둔다
  useEffect(() => {
    if (!product || !anchor) return;
    if (tab === "faults") setOpenFault(product.faults.find((f) => f.error_code === anchor)?.fault_id ?? null);
    if (tab === "install") setOpenSec(product.install?.sections.find((s) => s.section === anchor)?.section ?? null);
  }, [product, tab, anchor]);

  if (error) return <p className="pd pd-note" role="alert">제품 정보를 불러오지 못했어요. ({error})</p>;
  if (!product) return <p className="pd pd-note">제품 정보를 불러오는 중이에요…</p>;

  const active: Tab = (product.tabs as string[]).includes(tab) ? (tab as Tab) : product.tabs[0];
  const view = (docId: string | null | undefined, section: string | null = null): ReactNode =>
    docId ? <button type="button" className="pd-src" onClick={() => setSource({ docId, section })}>📄 {docId}{section ? ` §${section}` : ""} 원문 보기</button> : null;

  return (
    <section className="pd" aria-label={`${product.name} 상세`}>
      <header className="pd-head">
        <small>{product.division_label} · {product.family_label}</small>
        <h2>{product.name}</h2>
        <p>{product.description}</p>
        <div className="pd-meta">
          <span>{product.code}</span>
          {product.lifecycle_status && <span className="pd-badge">{product.lifecycle_status}</span>}
        </div>
      </header>

      <div className="pd-tabs" role="tablist">
        {product.tabs.map((t) => (
          <button key={t} type="button" role="tab" aria-selected={t === active} className={t === active ? "is-on" : ""} onClick={() => onTab(t)}>
            {TAB_LABELS[t] ?? t}
          </button>
        ))}
      </div>

      {active === "info" && (
        <div className="pd-pane">
          <div className="pd-facts">
            <Row hit={anchor === "lead_time"}>
              <h3>📦 납기 · 최소 주문 · 보증</h3>
              <dl>
                <div><dt>표준 납기(공장 출고)</dt><dd>{product.info.ordering.std_lead_time_weeks}주</dd></div>
                <div><dt>최소 주문 수량</dt><dd>{product.info.ordering.moq}개</dd></div>
                <div><dt>보증</dt><dd>{product.info.ordering.warranty_months}개월</dd></div>
              </dl>
            </Row>
            <Row>
              <h3>📐 외형 · 환경</h3>
              <dl>
                {product.info.physical.weight_kg && <div><dt>무게</dt><dd>{product.info.physical.weight_kg} kg</dd></div>}
                {product.info.physical.dimensions_mm && <div><dt>크기(mm)</dt><dd>{product.info.physical.dimensions_mm}</dd></div>}
                {product.info.physical.ip_rating && <div><dt>보호 등급</dt><dd>{product.info.physical.ip_rating}</dd></div>}
                {product.info.physical.operating_temp && <div><dt>사용 온도</dt><dd>{product.info.physical.operating_temp}</dd></div>}
              </dl>
            </Row>
          </div>
          {(product.info.standards.length > 0 || product.info.certifications.length > 0) && (
            <div className="pd-chips">
              {product.info.standards.map((s) => <span key={s}>표준 · {s}</span>)}
              {product.info.certifications.map((c) => <span key={c}>인증 · {c}</span>)}
            </div>
          )}
          <h3>📊 주요 사양</h3>
          <p className="pd-hint">항목을 누르면 근거 원문을 볼 수 있어요.</p>
          {product.info.specs.map((s) => (
            <Row key={s.attribute} hit={anchor === s.attribute}>
              <button type="button" className="pd-spec" onClick={() => setSource({ docId: s.doc_id, section: s.section })}>
                <span>{s.attribute}</span><b>{s.value}</b><small>{s.doc_id} §{s.section}</small>
              </button>
            </Row>
          ))}
          {product.info.specs.length === 0 && <p className="pd-note">등록된 주요 사양이 없어요.</p>}
        </div>
      )}

      {active === "install" && product.install && (
        <div className="pd-pane">
          <p className="pd-hint">{product.install.title} (Rev. {product.install.revision})</p>
          {product.install.sections.map((s) => (
            <Row key={s.section} hit={anchor === s.section}>
              <button type="button" className="pd-acc" aria-expanded={openSec === s.section} onClick={() => setOpenSec(openSec === s.section ? null : s.section)}>
                <span>{s.section}. {s.title}</span><i aria-hidden="true">{openSec === s.section ? "▲" : "▼"}</i>
              </button>
              {openSec === s.section && <div className="pd-accbody"><MarkdownText text={s.text} />{view(product.install?.doc_id, s.section)}</div>}
            </Row>
          ))}
        </div>
      )}

      {active === "faults" && (
        <div className="pd-pane">
          {product.faults.map((f) => (
            <Row key={f.fault_id} hit={!!anchor && anchor === f.error_code}>
              <button type="button" className="pd-acc" aria-expanded={openFault === f.fault_id} onClick={() => setOpenFault(openFault === f.fault_id ? null : f.fault_id)}>
                <span>{f.error_code && <em className="pd-code">{f.error_code}</em>}{f.symptom}</span><i aria-hidden="true">{openFault === f.fault_id ? "▲" : "▼"}</i>
              </button>
              {openFault === f.fault_id && (
                <div className="pd-accbody">
                  <dl className="pd-steps">
                    <div><dt>원인</dt><dd>{f.root_cause}</dd></div>
                    <div><dt>확인 방법</dt><dd>{f.diagnosis}</dd></div>
                    <div><dt>조치</dt><dd>{f.action}</dd></div>
                  </dl>
                  <div className="pd-flags">
                    {f.needs_onsite && <span>🧑‍🔧 현장 방문 필요</span>}
                    {f.needs_rma && <span>📦 RMA 필요</span>}
                    {f.fw_fix_version && <span>🔄 펌웨어 {f.fw_fix_version}에서 수정</span>}
                  </div>
                  {view(f.doc_id, f.section)}
                </div>
              )}
            </Row>
          ))}
          {product.faults.length === 0 && <p className="pd-note">등록된 고장 정보가 없어요.</p>}
        </div>
      )}

      {active === "firmware" && product.firmware && (
        <div className="pd-pane">
          <Row hit={anchor === product.firmware.latest}><h3>🔄 최신 펌웨어 {product.firmware.latest}</h3></Row>
          <p className="pd-hint">아래는 변경 이력이에요. 펌웨어 설치 파일은 제공되지 않아요.</p>
          {product.firmware.releases.map((r) => (
            <Row key={r.version} hit={anchor === r.version}>
              <div className="pd-rel">
                <div><b>v{r.version}</b>{r.latest && <em className="pd-new">최신</em>}<small>{r.release_date}</small></div>
                <ul>{r.changes.map((c) => <li key={c}>{c}</li>)}</ul>
                {view(r.doc_id)}
              </div>
            </Row>
          ))}
        </div>
      )}

      {active === "faq" && product.faq && (
        <div className="pd-pane">
          {product.faq.items.map((q) => (
            <Row key={q.section}>
              <button type="button" className="pd-acc" aria-expanded={openSec === `q${q.section}`} onClick={() => setOpenSec(openSec === `q${q.section}` ? null : `q${q.section}`)}>
                <span>{q.question}</span><i aria-hidden="true">{openSec === `q${q.section}` ? "▲" : "▼"}</i>
              </button>
              {openSec === `q${q.section}` && <div className="pd-accbody"><MarkdownText text={q.answer} />{view(product.faq?.doc_id, q.section)}</div>}
            </Row>
          ))}
          {product.faq.policies.length > 0 && (
            <>
              <Row hit={anchor === "policy"}><h3>📋 보증 · 반품 · 주문 · 서비스 정책</h3></Row>
              {product.faq.policies.map((p) => (
                <Row key={p.doc_id}>
                  <button type="button" className="pd-acc" aria-expanded={openSec === p.doc_id} onClick={() => setOpenSec(openSec === p.doc_id ? null : p.doc_id)}>
                    <span>{p.title} <small>Rev. {p.revision}</small></span><i aria-hidden="true">{openSec === p.doc_id ? "▲" : "▼"}</i>
                  </button>
                  {openSec === p.doc_id && <div className="pd-accbody">{view(p.doc_id)}</div>}
                </Row>
              ))}
            </>
          )}
        </div>
      )}

      {active === "docs" && (
        <div className="pd-pane">
          {product.docs.map((d) => (
            <Row key={d.doc_id} hit={anchor === d.doc_id}>
              <button type="button" className="pd-doccard" onClick={() => setSource({ docId: d.doc_id, section: null })}>
                <span className="pd-type">{d.doc_type}</span><b>{d.title}</b><small>{d.doc_id} · Rev. {d.revision}</small>
              </button>
            </Row>
          ))}
          <p className="pd-hint">원본 파일 다운로드는 아직 제공되지 않아요. 원문은 화면에서 볼 수 있어요.</p>
        </div>
      )}

      {source && <DocViewer key={`${source.docId}#${source.section}`} code={product.code} docId={source.docId} section={source.section} onClose={() => setSource(null)} />}
    </section>
  );
}
