// 지식·해결 사례: 해결 사례(CSV 800건) / 기술문서. 완료 문의(담당자가 기록한 처리 결과)은 문의 관리의 탭에서 보여 준다.
import { useEffect, useState } from "react";
import { api, type CompletedPage } from "../../api/client";
import { loadTicketDetail, watchTicketDetail } from "@admin/lib/api-sync";
import type { Ticket } from "@admin/lib/types";
import { Button } from "@admin/components/ui/button";
import { Card } from "@admin/components/ui/card";
import { Input } from "@admin/components/ui/input";
import DocContent from "@admin/components/admin/DocContent";
import { Empty, Facts, Mono, PageHeader, Tag, UnderlineTabs, useGo } from "@admin/components/admin/common";
import { documentCatalog } from "@admin/data/knowledge-data";
import { CASE_GROUPS, FAMILY_KO, groupOfCategory } from "@admin/lib/customers";
import { cases, sourceInquiry, translated, type CaseRow } from "@admin/lib/logic";
import { openModal, setUi, ui, useStore } from "@admin/lib/store";
import { cn } from "@admin/lib/utils";

const TABS = ["해결 사례", "기술문서"] as const;
const DOC_TYPE_KO: Record<string, string> = { DS: "데이터시트", IG: "설치 가이드", TG: "문제 해결", MG: "유지보수", RN: "릴리스 노트", FAQ: "FAQ", POL: "정책" };
/** 기술문서의 제품군: 제품군이 없는 문서(정책 등)는 "공통"으로 묶는다. */
const docFamily = (d: any): string => d.family || "COMMON";
const caseGroup = (c: CaseRow): string => groupOfCategory(c.raw.category_code);
const FAMILY_CHIPS: [string, string][] = [...Object.entries(FAMILY_KO), ["COMMON", "공통·정책"]];

export default function Knowledge() {
  useStore();
  const docs = ui.knowledgeTab === "기술문서";
  return (
    <>
      <PageHeader title="지식·해결 사례" actions={<small className="text-muted-foreground">{docs ? documentCatalog.filter((d: any) => !ui.docFamily || docFamily(d) === ui.docFamily).length : cases.filter((c) => (!ui.caseGroup || caseGroup(c) === ui.caseGroup) && (!ui.caseFamily || c.raw.product_family === ui.caseFamily)).length}건</small>}>
        <UnderlineTabs tabs={TABS.map((v) => [v, v] as const)} value={(docs ? "기술문서" : "해결 사례") as (typeof TABS)[number]} onChange={(v) => setUi({ knowledgeTab: v, knowledge: 0 })} />
      </PageHeader>
      <Catalog docs={docs} />
    </>
  );
}

function ListButton({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return <button onClick={onClick} className={cn("grid rounded-xl bg-card px-5 py-5 text-left shadow-card transition-all hover:-translate-y-0.5 hover:shadow-float [&>*:first-child]:mb-3 [&>*:last-child]:mt-2 [&>strong]:text-[15px] [&>strong]:font-semibold [&>strong]:leading-snug", active && "ring-2 ring-inset ring-[#003377]/45")}>{children}</button>;
}

function Catalog({ docs }: { docs: boolean }) {
  const q = ui.kquery.toLowerCase();
  const records: any[] = docs ? documentCatalog : cases;
  const filtered = records.filter((c) => (docs ? !ui.docFamily || docFamily(c) === ui.docFamily : (!ui.caseGroup || caseGroup(c) === ui.caseGroup) && (!ui.caseFamily || c.raw.product_family === ui.caseFamily)) && JSON.stringify(docs ? [c.doc_id, c.title, c.product_code] : [c.id, c.title, c.product, c.cause, c.raw.error_code]).toLowerCase().includes(q));
  const chosen = filtered.find((c) => records.indexOf(c) === ui.knowledge) || filtered[0];
  return (
    <>
      <div className="flex items-center gap-3 px-10 pb-4"><Input className="h-10 w-80 rounded-full bg-card px-4 shadow-card" aria-label="지식 검색" placeholder="제품·오류 코드 검색" value={ui.kquery} onChange={(e) => setUi({ kquery: e.target.value })} /></div>
      {!docs && (
        <div role="group" aria-label="분류" className="flex flex-wrap items-center gap-2 px-10 pb-4">
          <Button size="sm" variant={!ui.caseGroup ? "default" : "outline"} onClick={() => setUi({ caseGroup: "", caseFamily: "", knowledge: 0 })}>전체 <span className="tabular-nums opacity-70">{cases.length}</span></Button>
          {CASE_GROUPS.map(([code, label]) => (
            <Button key={code} size="sm" variant={ui.caseGroup === code ? "default" : "outline"} onClick={() => setUi({ caseGroup: code, caseFamily: "", knowledge: 0 })}>{label} <span className="tabular-nums opacity-70">{cases.filter((c) => caseGroup(c) === code).length}</span></Button>
          ))}
        </div>
      )}
      {!docs && ui.caseGroup && ( // 문의 유형을 먼저 고르면 그 아래에 제품군 칩이 나온다
        <div role="group" aria-label="제품군" className="flex flex-wrap items-center gap-2 px-10 pb-4">
          {(() => {
            const inGroup = cases.filter((c) => !ui.caseGroup || caseGroup(c) === ui.caseGroup);
            return <>
              <Button size="sm" variant={!ui.caseFamily ? "default" : "outline"} onClick={() => setUi({ caseFamily: "", knowledge: 0 })}>전체 <span className="tabular-nums opacity-70">{inGroup.length}</span></Button>
              {Object.entries(FAMILY_KO).map(([code, label]) => {
                const n = inGroup.filter((c) => c.raw.product_family === code).length;
                return n > 0 && <Button key={code} size="sm" variant={ui.caseFamily === code ? "default" : "outline"} onClick={() => setUi({ caseFamily: code, knowledge: 0 })}>{label} <span className="tabular-nums opacity-70">{n}</span></Button>;
              })}
            </>;
          })()}
        </div>
      )}
      {docs && (
        <div role="group" aria-label="제품군" className="flex flex-wrap items-center gap-2 px-10 pb-4">
          <Button size="sm" variant={!ui.docFamily ? "default" : "outline"} onClick={() => setUi({ docFamily: "", knowledge: 0 })}>전체 <span className="tabular-nums opacity-70">{documentCatalog.length}</span></Button>
          {FAMILY_CHIPS.map(([code, label]) => {
            const n = documentCatalog.filter((d: any) => docFamily(d) === code).length;
            return n > 0 && <Button key={code} size="sm" variant={ui.docFamily === code ? "default" : "outline"} onClick={() => setUi({ docFamily: code, knowledge: 0 })}>{label} <span className="tabular-nums opacity-70">{n}</span></Button>;
          })}
        </div>
      )}
      <div className={cn("grid min-h-96 grid-cols-[340px_minmax(0,1fr)] gap-4 px-10 pb-6", docs || !ui.caseGroup ? "h-[calc(100dvh-21rem)]" : "h-[calc(100dvh-25rem)]")}>
        <div className="grid min-h-0 content-start gap-3 overflow-y-auto pr-2">
          {filtered.slice(0, 80).map((c) => (
            <ListButton key={docs ? c.doc_id : c.id} active={c === chosen} onClick={() => setUi({ knowledge: records.indexOf(c) })}>
              <Mono className="text-xs text-info">{docs ? c.doc_id : c.id}</Mono><strong className="text-sm leading-snug">{c.title}</strong>
              <small className="text-muted-foreground">{docs ? <><Tag className="mr-1.5">{DOC_TYPE_KO[c.doc_type] || c.doc_type}</Tag><Mono>{c.product_code}</Mono></> : <><Tag className="mr-1.5">{CASE_GROUPS.find(([k]) => k === caseGroup(c))?.[1] || "기타"}</Tag>{c.product} · <Mono>{c.raw.error_code || c.raw.category_code}</Mono></>}</small>
            </ListButton>
          ))}
          {!filtered.length && <Empty>검색 결과가 없습니다.</Empty>}
          {filtered.length > 80 && <small className="px-1 text-muted-foreground">80건 표시 · 검색으로 범위를 좁혀 주세요.</small>}
        </div>
        <div className="min-h-0 overflow-y-auto pb-2 pr-1">
        {chosen ? docs ? (
          <Card className="gap-4 p-6"><div className="text-xs text-info"><Mono>{chosen.doc_id}</Mono> · Rev {chosen.revision}</div><h1 className="text-2xl font-bold">{chosen.title}</h1><DocContent text={chosen.content} /></Card>
        ) : <CaseDetail c={chosen} /> : <Card className="p-12 text-center text-muted-foreground">검색 조건에 맞는 자료가 없습니다.</Card>}
        </div>
      </div>
    </>
  );
}

const Section = ({ title, children }: { title: string; children: React.ReactNode }) => <section className="grid gap-3.5 border-t pt-5"><h2 className="font-semibold">{title}</h2>{children}</section>;
function Fold({ title, children }: { title: string; children: React.ReactNode }) {
  return <details className="rounded-xl bg-muted px-4 py-3 text-sm"><summary className="cursor-pointer font-medium">{title}</summary><div className="mt-3">{children}</div></details>;
}
function CaseDetail({ c }: { c: CaseRow }) {
  const r = c.raw;
  return (
    <Card className="gap-5 p-6">
      <div className="flex items-center justify-between"><span className="text-sm text-info"><Mono>{c.id}</Mono> · {r.error_code ? <Mono>{r.error_code}</Mono> : "오류 코드 없음"}</span><Tag tone="green">처리 완료</Tag></div>
      <h1 className="text-2xl font-bold">{c.title}</h1>
      <dl className="flex flex-wrap items-center gap-y-1 text-sm [&>div+div]:ml-5 [&>div+div]:border-l [&>div+div]:pl-5 [&>div]:flex [&>div]:items-center [&>div]:gap-2">
        <div><dt className="text-muted-foreground">제품</dt><dd className="font-semibold">{c.product}</dd></div>
        <div><dt className="text-muted-foreground">펌웨어</dt><dd className="font-semibold">{r.fw_version_at_issue || "미기록"}</dd></div>
        <div><dt className="text-muted-foreground">원본 문의</dt><dd><Mono className="font-semibold">{c.ticketId}</Mono></dd></div>
      </dl>
      <section className="grid gap-3 rounded-xl bg-accent/70 p-4"><h2 className="font-semibold">해결 요약</h2>
        <Facts className="gap-y-4 [&_dt]:font-bold [&_dt]:text-foreground" rows={[["확인된 원인", <strong key="c">{c.cause}</strong>], ["수행 조치", c.action], ["확인 결과", <span key="r" className="text-success">{c.result}</span>]]} /></section>
      <Section title="증상과 발생 조건">
        <div className="rounded-2xl bg-muted/60 px-5 py-4 text-base leading-[1.8]">{c.symptom}</div>
        {c.symptom !== r.symptom && <Fold title="증상 원문"><p>{r.symptom}</p></Fold>}
      </Section>
      <Fold title="진단 과정과 가설 검증">
        <Facts rows={[["초기 가설", translated(r.initial_hypothesis)], ["가설 검증", <Tag key="h" tone={r.hypothesis_correct === "N" ? "amber" : "green"}>{r.hypothesis_correct === "N" ? "가설 배제" : r.hypothesis_correct === "Y" ? "가설 확인" : "미기록"}</Tag>], ["원인 분류", r.root_cause_type || "미기록"]]} />
      </Fold>
      <Fold title="진단·조치 상세">
        <Facts rows={[["진단 기록", translated(r.diagnosis_method)], ["교체 부품", r.replacement_part || "기록 없음"], ["현장 방문", r.onsite_visit === "Y" ? "현장 방문" : r.onsite_visit === "N" ? "방문 없음" : "미기록"], ["RMA", r.rma_no || "기록 없음"], ["펌웨어 조치", r.fw_fixed_version || "기록 없음"]]} />
      </Fold>
      <Fold title="처리 정보와 재발 방지">
        <Facts rows={[["해결 부서", translated(r.resolved_by_dept)], ["소요 시간", `${r.time_to_resolve_hours || "미기록"}시간`], ["재발 방지", translated(r.recurrence_prevention)]]} />
      </Fold>
      <Section title="근거 문서">
        <button className="w-fit text-info hover:underline" onClick={() => openModal("knowledge-document", { docId: r.reference_doc_id })}><Mono>{r.reference_doc_id}</Mono> · §{r.reference_section}</button>
        <Fold title="원본 처리 기록"><p>{r.case_summary}</p></Fold>
      </Section>
      <div className="rounded-lg bg-secondary px-4 py-3 text-sm text-muted-foreground">과거의 진단·조치 기록입니다. 현재 문의의 제품·발생 조건과 비교한 뒤 적용 여부를 판단합니다.</div>
    </Card>
  );
}

/** 문의 관리의 "완료 문의" 탭: 담당자가 처리 결과를 기록해 완료한 문의. */
export function CompletedTickets() {
  const go = useGo();
  const [page, setPage] = useState<CompletedPage>({ items: [], total: 0 });
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);
  const [detail, setDetail] = useState<Ticket | null>(null);
  const [detailError, setDetailError] = useState("");
  useEffect(() => { const timer = setInterval(() => setRetry((v) => v + 1), 30_000); return () => clearInterval(timer); }, []);
  const query = ui.kquery, verified = ui.completedFilter === "검증된 해결";
  useEffect(() => { setOffset(0); }, [query, verified]);
  useEffect(() => {
    let cancelled = false;
    setLoading(true); setError("");
    const timer = setTimeout(() => {
      api.completedPage(query, verified, offset, 50).then((result) => {
        if (cancelled) return;
        if (offset > 0 && offset >= result.total) { setOffset(0); return; }
        setPage(result); setLoading(false);
      }).catch(() => { if (!cancelled) { setError("완료 문의를 불러오지 못했습니다."); setLoading(false); } });
    }, 200);
    return () => { cancelled = true; clearTimeout(timer); };
  }, [query, verified, offset, retry, ui.completedTotal]);
  const records = page.items.map((r) => ({
    ticket: { id: r.ticket_id, title: r.subject || r.ticket_id, product: r.product_code || "제품 미확인" },
    resolution: { ...r.resolution, confirmedBy: r.resolution.confirmed_by } as Record<string, any>,
    time: r.resolution.confirmed_at || r.resolved_at, verified: r.verified, superseded: r.superseded,
  }));
  const chosen = records.find((r) => r.ticket.id === ui.completedTicket) || records[0];
  const chosenId = !loading && !error ? chosen?.ticket.id : undefined;
  useEffect(() => {
    setDetail(null); setDetailError("");
    if (!chosenId) return;
    let cancelled = false;
    const stop = watchTicketDetail(chosenId);
    loadTicketDetail(chosenId).then((t) => { if (!cancelled) setDetail(t); })
      .catch(() => { if (!cancelled) setDetailError("문의 상세를 불러오지 못했습니다."); });
    return () => { cancelled = true; stop(); };
  }, [chosenId]);
  return (
    <>
      <div className="flex items-center gap-3 px-10 pb-4">
        <Input className="h-10 w-80 rounded-full bg-card px-4 shadow-card" aria-label="지식 검색" placeholder="문의·제품·원인·조치 검색" value={ui.kquery} onChange={(e) => setUi({ kquery: e.target.value })} />
        {["전체 기록", "검증된 해결"].map((v) => <Button key={v} size="sm" variant={ui.completedFilter === v ? "default" : "outline"} onClick={() => setUi({ completedFilter: v })}>{v}</Button>)}
      </div>
      <div className="grid h-[calc(100dvh-16.5rem)] min-h-96 grid-cols-[340px_minmax(0,1fr)] gap-4 px-10 pb-6">
        <div className="grid min-h-0 content-start gap-3 overflow-y-auto pr-2">
          {!loading && !error && records.map((r) => (
            <ListButton key={r.ticket.id} active={r === chosen} onClick={() => setUi({ completedTicket: r.ticket.id })}>
              <Mono className="text-xs text-info">{r.ticket.id}</Mono><strong className="text-sm">{r.ticket.title}</strong><small className="text-muted-foreground">{r.ticket.product}</small>
              <Tag tone={r.verified ? "green" : ""} className="w-fit">{r.superseded ? "재검토 중" : r.verified ? "담당자 해결 확인" : r.resolution.outcome === "provided" ? "정보 제공 완료" : r.resolution.outcome ? "해결 미확인" : "처리 결과 미기록"}</Tag>
            </ListButton>
          ))}
          {loading ? <Empty>완료 문의를 불러오는 중입니다.</Empty> : error ? <div role="alert">{error}<Button variant="outline" onClick={() => setRetry((v) => v + 1)}>다시 시도</Button></div> : !records.length && <Empty>해당하는 처리 기록이 없습니다.</Empty>}
          <div className="flex items-center justify-between gap-2 py-2 text-sm">
            <Button variant="outline" disabled={loading || offset === 0} onClick={() => setOffset((v) => Math.max(0, v - 50))}>이전</Button>
            <span>{page.total}건 · {Math.floor(offset / 50) + 1}페이지</span>
            <Button variant="outline" disabled={loading || offset + 50 >= page.total} onClick={() => setOffset((v) => v + 50)}>다음</Button>
          </div>
        </div>
        <div className="min-h-0 overflow-y-auto pb-2 pr-1">
        {!loading && !error && chosen ? (
          <Card className="gap-5 p-6">
            <div className="flex items-center justify-between"><Mono className="text-sm text-info">{chosen.ticket.id}</Mono><Tag tone={chosen.verified ? "green" : ""}>{chosen.superseded ? "재검토 중 · 이전 완료 기록" : chosen.verified ? "담당자 해결 확인" : "일반 응대 이력"}</Tag></div>
            <h1 className="text-2xl font-bold">{chosen.ticket.title}</h1>
            <dl className="flex flex-wrap items-center gap-y-1 text-sm [&>div+div]:ml-5 [&>div+div]:border-l [&>div+div]:pl-5 [&>div]:flex [&>div]:items-center [&>div]:gap-2">
              <div><dt className="text-muted-foreground">제품</dt><dd className="font-semibold">{chosen.ticket.product}</dd></div>
              <div><dt className="text-muted-foreground">확인자</dt><dd className="font-semibold">{chosen.resolution.confirmedBy || "미기록"}</dd></div>
              <div><dt className="text-muted-foreground">완료일</dt><dd className="font-semibold">{chosen.time ? new Date(chosen.time).toLocaleDateString("ko-KR") : "미기록"}</dd></div>
            </dl>
            <Section title="문의와 처리 결과">
              <div className="mt-2 grid gap-2">
                <h3 className="text-sm font-semibold text-muted-foreground">고객 문의</h3>
                <blockquote className="rounded-xl bg-muted/60 px-4 py-3 text-[15px] leading-relaxed">{detail?.id === chosen.ticket.id ? sourceInquiry(detail) : detailError || "문의 원문을 불러오는 중입니다."}</blockquote>
                {detailError && <Button variant="outline" className="w-fit" onClick={() => setRetry((v) => v + 1)}>다시 시도</Button>}
              </div>
              <div className="mt-5 grid gap-3">
                <h3 className="text-sm font-semibold text-muted-foreground">처리 결과</h3>
                <Facts className="gap-y-5 [&_dt]:font-bold [&_dt]:text-foreground" rows={[["원인·판단", chosen.resolution.cause || "미기록"], ["수행 조치", chosen.resolution.action || "미기록"], ["결과", chosen.resolution.result || "미기록"], ["확인 근거", chosen.resolution.verification || "미기록"]]} />
              </div>
            </Section>
            <Section title="참고 근거">{(chosen.resolution.references || []).length ? <ul className="list-disc pl-5 text-sm">{chosen.resolution.references.map((x: any) => <li key={x.id}>{x.label}</li>)}</ul> : <p className="text-sm text-muted-foreground">참고 근거 미기록</p>}</Section>
            <div className="rounded-lg bg-secondary px-4 py-3 text-sm text-muted-foreground">{chosen.superseded ? "후속 문의로 재검토 중인 이전 기록입니다. 현재 해결 근거로 사용하지 않습니다." : chosen.verified ? "담당자가 실제 조치 결과와 확인 근거를 기록한 사례입니다. 현재 문의의 조건과 비교해 활용하세요." : "응대 이력입니다. 실제 고장 해결이 확인된 사례와 구분합니다."}</div>
            <Button className="w-fit" variant="outline" onClick={() => go.ticket(chosen.ticket.id)}>원본 문의 열기</Button>
          </Card>
        ) : <Card className="p-12 text-center text-muted-foreground">완료 처리 결과를 기록하면 여기에서 조회할 수 있습니다.</Card>}
        </div>
      </div>
    </>
  );
}
