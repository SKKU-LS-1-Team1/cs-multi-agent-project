// 지식·해결 사례: 해결 사례(CSV 800건) / 기술문서. 완료 티켓(담당자가 기록한 처리 결과)은 티켓 관리의 탭에서 보여 준다.
import { useRef } from "react";
import { Button } from "@admin/components/ui/button";
import { Card } from "@admin/components/ui/card";
import { Input } from "@admin/components/ui/input";
import DocContent from "@admin/components/admin/DocContent";
import { Empty, Facts, Mono, PageHeader, Tag, UnderlineTabs, useGo } from "@admin/components/admin/common";
import { documentCatalog } from "@admin/data/knowledge-data";
import { cases, completedTickets, sourceInquiry, translated, type CaseRow } from "@admin/lib/logic";
import { openModal, setUi, ui, useStore } from "@admin/lib/store";
import { cn } from "@admin/lib/utils";

const TABS = ["해결 사례", "기술문서"] as const;

export default function Knowledge() {
  useStore();
  const docs = ui.knowledgeTab === "기술문서";
  return (
    <>
      <PageHeader title="지식·해결 사례" actions={<small className="text-muted-foreground">{docs ? documentCatalog.length : cases.length}건</small>}>
        <UnderlineTabs tabs={TABS.map((v) => [v, v] as const)} value={(docs ? "기술문서" : "해결 사례") as (typeof TABS)[number]} onChange={(v) => setUi({ knowledgeTab: v, knowledge: 0 })} />
      </PageHeader>
      <Catalog docs={docs} />
    </>
  );
}

function ListButton({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return <button onClick={onClick} className={cn("grid gap-1 rounded-xl bg-card p-3.5 text-left shadow-card transition-all hover:-translate-y-0.5 hover:shadow-float", active && "ring-2 ring-inset ring-[#003377]/45")}>{children}</button>;
}

function Catalog({ docs }: { docs: boolean }) {
  const q = ui.kquery.toLowerCase();
  const records: any[] = docs ? documentCatalog : cases;
  const filtered = records.filter((c) => JSON.stringify(docs ? [c.doc_id, c.title, c.product_code] : [c.id, c.title, c.product, c.cause, c.raw.error_code]).toLowerCase().includes(q));
  const chosen = filtered.find((c) => records.indexOf(c) === ui.knowledge) || filtered[0];
  return (
    <>
      <div className="flex items-center gap-3 px-10 pb-4"><Input className="h-10 w-80 rounded-full bg-card px-4 shadow-card" aria-label="지식 검색" placeholder="제품·오류 코드·증상 검색" value={ui.kquery} onChange={(e) => setUi({ kquery: e.target.value })} /></div>
      <div className="grid h-[calc(100dvh-16.5rem)] min-h-96 grid-cols-[340px_minmax(0,1fr)] gap-4 px-10 pb-6">
        <div className="grid min-h-0 content-start gap-2 overflow-y-auto pr-2">
          {filtered.slice(0, 80).map((c) => (
            <ListButton key={docs ? c.doc_id : c.id} active={c === chosen} onClick={() => setUi({ knowledge: records.indexOf(c) })}>
              <Mono className="text-xs text-info">{docs ? c.doc_id : c.id}</Mono><strong className="text-sm leading-snug">{c.title}</strong>
              <small className="text-muted-foreground">{docs ? <Mono>{c.product_code}</Mono> : <>{c.product} · <Mono>{c.raw.error_code || c.raw.category_code}</Mono></>}</small>
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

const Section = ({ title, children }: { title: string; children: React.ReactNode }) => <section className="grid gap-2 border-t pt-4"><h2 className="font-semibold">{title}</h2>{children}</section>;
function Fold({ title, children }: { title: string; children: React.ReactNode }) {
  return <details className="rounded-xl bg-muted px-4 py-3 text-sm"><summary className="cursor-pointer font-medium">{title}</summary><div className="mt-3">{children}</div></details>;
}
function CaseDetail({ c }: { c: CaseRow }) {
  const r = c.raw;
  return (
    <Card className="gap-5 p-6">
      <div className="flex items-center justify-between"><span className="text-sm text-info"><Mono>{c.id}</Mono> · {r.error_code ? <Mono>{r.error_code}</Mono> : "오류 코드 없음"}</span><Tag tone="green">처리 완료</Tag></div>
      <h1 className="text-2xl font-bold">{c.title}</h1>
      <div className="text-sm text-muted-foreground">{c.product} · FW {r.fw_version_at_issue || "미기록"} · 원본 {c.ticketId}</div>
      <section className="grid gap-3 rounded-xl bg-accent/70 p-4"><h2 className="font-semibold">해결 요약</h2>
        <Facts rows={[["확인된 원인", <strong key="c">{c.cause}</strong>], ["수행 조치", c.action], ["확인 결과", <span key="r" className="text-success">{c.result}</span>]]} /></section>
      <Section title="증상과 발생 조건">
        <p>{c.symptom}</p>
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

/** 티켓 관리의 "완료 티켓" 탭: 담당자가 처리 결과를 기록해 완료한 티켓. */
export function CompletedTickets() {
  const go = useGo();
  const q = ui.kquery.toLowerCase(), all = completedTickets();
  const records = all.filter((r) => JSON.stringify([r.ticket.id, r.ticket.title, r.ticket.product, r.resolution]).toLowerCase().includes(q) && (ui.completedFilter !== "검증된 해결" || r.verified));
  const chosen = records.find((r) => r.ticket.id === ui.completedTicket) || records[0];
  const list = useRef(null);
  if (!all.length)
    return (
      <div className="px-10 pb-12">
        <div className="grid justify-items-center gap-3 rounded-2xl bg-card px-6 py-16 text-center shadow-card">
          <strong className="font-medium">아직 완료 처리한 티켓이 없습니다.</strong>
          <p className="max-w-md text-sm text-muted-foreground">티켓 상세에서 "처리 결과 기록 및 완료"를 하면 원인·조치·결과가 여기에 쌓여, 비슷한 문의의 근거로 쓸 수 있습니다.</p>
          <Button variant="outline" onClick={() => go.list({ filter: "내 담당" })}>내 티켓 보기</Button>
        </div>
      </div>
    );
  return (
    <>
      <div className="flex items-center gap-3 px-10 pb-4">
        <Input className="h-10 w-80 rounded-full bg-card px-4 shadow-card" aria-label="지식 검색" placeholder="티켓·제품·원인·조치 검색" value={ui.kquery} onChange={(e) => setUi({ kquery: e.target.value })} />
        {["전체 기록", "검증된 해결"].map((v) => <Button key={v} size="sm" variant={ui.completedFilter === v ? "default" : "outline"} onClick={() => setUi({ completedFilter: v })}>{v}</Button>)}
      </div>
      <div className="grid h-[calc(100dvh-16.5rem)] min-h-96 grid-cols-[340px_minmax(0,1fr)] gap-4 px-10 pb-6">
        <div ref={list} className="grid min-h-0 content-start gap-2 overflow-y-auto pr-2">
          {records.map((r) => (
            <ListButton key={r.ticket.id} active={r === chosen} onClick={() => setUi({ completedTicket: r.ticket.id })}>
              <Mono className="text-xs text-info">{r.ticket.id}</Mono><strong className="text-sm">{r.ticket.title}</strong><small className="text-muted-foreground">{r.ticket.product}</small>
              <Tag tone={r.verified ? "green" : ""} className="w-fit">{r.superseded ? "재검토 중" : r.verified ? "담당자 해결 확인" : r.resolution.outcome === "provided" ? "정보 제공 완료" : r.resolution.outcome ? "해결 미확인" : "처리 결과 미기록"}</Tag>
            </ListButton>
          ))}
          {!records.length && <Empty>해당하는 처리 기록이 없습니다.</Empty>}
        </div>
        <div className="min-h-0 overflow-y-auto pb-2 pr-1">
        {chosen ? (
          <Card className="gap-5 p-6">
            <div className="flex items-center justify-between"><Mono className="text-sm text-info">{chosen.ticket.id}</Mono><Tag tone={chosen.verified ? "green" : ""}>{chosen.superseded ? "재검토 중 · 이전 완료 기록" : chosen.verified ? "담당자 해결 확인" : "일반 응대 이력"}</Tag></div>
            <h1 className="text-2xl font-bold">{chosen.ticket.title}</h1>
            <div className="text-sm text-muted-foreground">{chosen.ticket.product} · {chosen.resolution.confirmedBy || "확인자 미기록"} · {chosen.time ? new Date(chosen.time).toLocaleDateString("ko-KR") : "완료일 미기록"}</div>
            <Section title="문의와 처리 결과"><p>{sourceInquiry(chosen.ticket)}</p>
              <Facts rows={[["원인·판단", chosen.resolution.cause || "미기록"], ["수행 조치", chosen.resolution.action || "미기록"], ["결과", chosen.resolution.result || "미기록"], ["확인 근거", chosen.resolution.verification || "미기록"]]} /></Section>
            <Section title="참고 근거">{(chosen.resolution.references || []).length ? <ul className="list-disc pl-5 text-sm">{chosen.resolution.references.map((x: any) => <li key={x.id}>{x.label}</li>)}</ul> : <p className="text-sm text-muted-foreground">참고 근거 미기록</p>}</Section>
            <div className="rounded-lg bg-secondary px-4 py-3 text-sm text-muted-foreground">{chosen.superseded ? "후속 문의로 재검토 중인 이전 기록입니다. 현재 해결 근거로 사용하지 않습니다." : chosen.verified ? "담당자가 실제 조치 결과와 확인 근거를 기록한 사례입니다. 현재 문의의 조건과 비교해 활용하세요." : "응대 이력입니다. 실제 고장 해결이 확인된 사례와 구분합니다."}</div>
            <Button className="w-fit" variant="outline" onClick={() => go.ticket(chosen.ticket.id)}>원본 티켓 열기</Button>
          </Card>
        ) : <Card className="p-12 text-center text-muted-foreground">완료 처리 결과를 기록하면 여기에서 조회할 수 있습니다.</Card>}
        </div>
      </div>
    </>
  );
}
