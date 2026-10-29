// 업무 메일 (CSA-74): 앞단(문의서·챗봇)을 거치지 않고 메일로 온 문의를 담당자가 티켓으로 등록한다 (services/mailbox.py)
// 메일을 열면 AI 가 유형·제품·긴급도를 분석하고 규칙이 담당 부서·우선순위·SLA 를 정한다 (티켓은 아직 없음).
// 담당자가 유형·제품을 고치면 다시 분석해 부서가 다시 정해지고, "티켓으로 등록" 하면 문의 관리 목록에 들어간다.
import { useEffect, useState } from "react";
import { CheckCircle2, Loader2, RefreshCw } from "lucide-react";
import { toast } from "sonner";
import { api, type MailAnalysis, type MailItem } from "../../api/client";
import { CATEGORY_LABEL, DEPT_LABEL, syncFromApi } from "@admin/lib/api-sync";
import { signedIn } from "@admin/lib/logic";
import { Button } from "@admin/components/ui/button";
import { Card } from "@admin/components/ui/card";
import { AiMark, Empty, Facts, Field, Mono, NativeSelect, PageHeader, PriorityTag, Tag, TierTag, UnderlineTabs, useGo } from "@admin/components/admin/common";
import { cn } from "@admin/lib/utils";

type Tab = "pending" | "registered";
type Product = { code: string; name: string; family: string; familyLabel: string };

const ROUTE_LABEL: Record<string, string> = {
  draft: "근거 검색 후 답변 초안 작성",
  info_request: "고객에게 추가정보 요청 (필수 정보 부족)",
  human: "담당자 직접 검토 (안전 신호)",
};
const URGENCY_LABEL: Record<string, string> = {
  NONE: "일반", SAFETY: "안전", SITE_DOWN: "현장 정지", PROD_IMPACT: "생산 영향", COMMISSION: "시운전", DEADLINE: "회신 기한",
};
// 같은 메일을 다시 열면 바로 보이도록 (백엔드도 같은 값이면 캐시를 돌려준다)
const analyses = new Map<string, MailAnalysis>();

function ago(iso: string) {
  const min = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 60_000));
  if (min < 60) return `${min}분 전`;
  if (min < 60 * 24) return `${Math.floor(min / 60)}시간 전`;
  return `${Math.floor(min / 60 / 24)}일 전`;
}

export default function Mailbox() {
  const [mails, setMails] = useState<MailItem[] | null>(null);
  const [error, setError] = useState("");
  const [tab, setTab] = useState<Tab>("pending");
  const [selected, setSelected] = useState<string | null>(null);
  const [products, setProducts] = useState<Product[]>([]);
  const load = () => api.mails().then((m) => { setMails(m); setError(""); }).catch((e) => setError(String(e.message || e)));
  useEffect(() => { void load(); }, []);
  useEffect(() => {
    api.productTree()
      .then((tree) => setProducts(tree.flatMap((d) => d.families.flatMap((f) => f.products.map((p) => ({ ...p, family: f.family, familyLabel: f.label }))))))
      .catch(() => setProducts([]));
  }, []);

  const pending = (mails || []).filter((m) => !m.ticket_id);
  const registered = (mails || []).filter((m) => m.ticket_id);
  const shown = tab === "pending" ? pending : registered;
  const chosen = shown.find((m) => m.mail_id === selected) || shown[0];
  const onRegistered = (mailId: string, ticketId: string) =>
    setMails((list) => (list || []).map((m) => (m.mail_id === mailId ? { ...m, ticket_id: ticketId } : m)));

  return (
    <>
      <PageHeader title="업무 메일" actions={<>
        <small className="text-muted-foreground">미처리 {pending.length} · 등록됨 {registered.length}</small>
        <Button variant="outline" size="sm" onClick={() => void load()}><RefreshCw className="size-4" aria-hidden />새로고침</Button>
      </>}>
        <p className="-mt-2 text-sm text-muted-foreground">문의서·챗봇을 거치지 않고 메일로 바로 온 문의입니다. 메일을 열면 AI가 분석하고 담당 부서를 정합니다. 확인 후 티켓으로 등록하세요.</p>
        <UnderlineTabs<Tab> tabs={[["pending", <>미처리 <span className="text-muted-foreground">{pending.length}</span></>], ["registered", <>등록됨 <span className="text-muted-foreground">{registered.length}</span></>]]} value={tab} onChange={(v) => { setTab(v); setSelected(null); }} />
      </PageHeader>
      {error && <p className="mx-10 mb-4 rounded-xl bg-destructive/10 px-4 py-3 text-sm text-destructive">메일함을 불러오지 못했습니다: {error}</p>}
      <div className="grid h-[calc(100dvh-17.5rem)] min-h-96 grid-cols-[360px_minmax(0,1fr)] gap-4 px-10 pb-6">
        <div className="grid min-h-0 content-start gap-2 overflow-y-auto pr-2">
          {mails === null && !error && <Empty>메일을 불러오는 중입니다…</Empty>}
          {shown.map((m) => <MailRow key={m.mail_id} mail={m} active={m === chosen} onClick={() => setSelected(m.mail_id)} />)}
          {mails !== null && !shown.length && <Empty>{tab === "pending" ? "처리할 메일이 없습니다." : "아직 등록한 메일이 없습니다."}</Empty>}
        </div>
        <div className="min-h-0 overflow-y-auto pb-2 pr-1">
          {chosen ? <MailDetail key={chosen.mail_id} mail={chosen} products={products} onRegistered={onRegistered} />
            : <Card className="p-12 text-center text-muted-foreground">왼쪽에서 메일을 고르세요.</Card>}
        </div>
      </div>
    </>
  );
}

function MailRow({ mail, active, onClick }: { mail: MailItem; active: boolean; onClick: () => void }) {
  return (
    <button onClick={onClick} className={cn("grid gap-1 rounded-xl bg-card p-3.5 text-left shadow-card transition-all hover:-translate-y-0.5 hover:shadow-float", active && "ring-2 ring-inset ring-[#003377]/45")}>
      <span className="flex items-center justify-between gap-2 text-xs text-muted-foreground">
        <span className="truncate">{mail.sender}</span><span className="shrink-0 tabular-nums">{ago(mail.received_at)}</span>
      </span>
      <strong className="line-clamp-2 text-sm leading-snug">{mail.subject}</strong>
      <span className="flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
        <TierTag tier={mail.customer_tier} /><Mono>{(mail.language || "-").toUpperCase()}</Mono>
        {mail.ticket_id ? <Tag tone="green">티켓 <Mono>{mail.ticket_id}</Mono></Tag> : mail.analyzed || analyses.has(mail.mail_id) ? <Tag tone="blue">AI 분석됨</Tag> : null}
      </span>
    </button>
  );
}

function MailDetail({ mail, products, onRegistered }: { mail: MailItem; products: Product[]; onRegistered: (mailId: string, ticketId: string) => void }) {
  const go = useGo();
  const [analysis, setAnalysis] = useState<MailAnalysis | null>(analyses.get(mail.mail_id) || null);
  const [analyzing, setAnalyzing] = useState(false);
  const [failed, setFailed] = useState("");
  const [category, setCategory] = useState(analysis?.classification?.category || "");
  const [product, setProduct] = useState(analysis?.extraction?.product_code || "");
  const [registering, setRegistering] = useState(false);
  const [korean, setKorean] = useState(false);

  const run = async (review: { category?: string | null; product_code?: string | null } = {}) => {
    setAnalyzing(true); setFailed("");
    try {
      const result = await api.analyzeMail(mail.mail_id, review);
      analyses.set(mail.mail_id, result);
      setAnalysis(result);
      setCategory(result.classification?.category || review.category || "");
      setProduct(result.extraction?.product_code || "");
    } catch (e: any) {
      setFailed(String(e.message || e));
    } finally {
      setAnalyzing(false);
    }
  };
  useEffect(() => { if (!mail.ticket_id && !analysis) void run(); }, [mail.mail_id]); // eslint-disable-line react-hooks/exhaustive-deps

  const aiCategory = analysis?.classification?.category || "";
  const aiProduct = analysis?.extraction?.product_code || "";
  const dirty = !!analysis && (category !== aiCategory || product !== aiProduct);
  const rerun = () => run({
    category: category !== aiCategory || analysis?.category_by === "reviewer" ? category || null : null,
    product_code: product !== aiProduct || analysis?.product_by === "reviewer" ? product || null : null,
  });
  // 분석이 실패했으면 담당자가 고른 유형으로 등록할 수 있다 (등록하면 처리 흐름이 다시 분석한다)
  const canRegister = !mail.ticket_id && !analyzing && !registering && !!category && (!!analysis?.error || !dirty);
  const register = async () => {
    setRegistering(true);
    try {
      const ticket = await api.registerMail(mail.mail_id, { category, product_code: product || null, reviewer: signedIn });
      await syncFromApi();
      onRegistered(mail.mail_id, ticket.ticket_id);
      toast.success(`티켓 ${ticket.ticket_id} 로 등록했습니다`, { action: { label: "열기", onClick: () => go.ticket(ticket.ticket_id) } });
    } catch (e: any) {
      toast.error(`등록하지 못했습니다: ${e.message || e}`);
    } finally {
      setRegistering(false);
    }
  };

  const rules = analysis?.rules;
  const extraction = analysis?.extraction;
  const families = [...new Map(products.map((p) => [p.family, p.familyLabel])).entries()];
  return (
    <div className="grid gap-4">
      <Card className="gap-4 p-6">
        <div className="flex flex-wrap items-center justify-between gap-2 text-sm text-muted-foreground">
          <span>{mail.sender} · <Mono>{mail.company}</Mono></span>
          <span className="flex items-center gap-2"><TierTag tier={mail.customer_tier} />{mail.country} · <Mono>{(mail.language || "-").toUpperCase()}</Mono> · {new Date(mail.received_at).toLocaleString("ko-KR")}</span>
        </div>
        <h1 className="text-2xl font-bold leading-snug">{mail.subject}</h1>
        {analysis?.body_ko && (
          <div className="flex gap-1.5">
            <Button size="sm" variant={korean ? "outline" : "default"} onClick={() => setKorean(false)}>원문</Button>
            <Button size="sm" variant={korean ? "default" : "outline"} onClick={() => setKorean(true)}>한국어 번역</Button>
          </div>
        )}
        <p className="whitespace-pre-wrap text-[15px] leading-relaxed">{korean && analysis?.body_ko ? analysis.body_ko : mail.body}</p>
      </Card>

      {mail.ticket_id ? (
        <Card className="flex-row items-center justify-between gap-4 p-6">
          <span className="flex items-center gap-2.5"><CheckCircle2 className="size-5 text-success" aria-hidden />티켓 <Mono>{mail.ticket_id}</Mono> 로 등록했습니다. 문의 관리에서 이어서 처리합니다.</span>
          <Button onClick={() => go.ticket(mail.ticket_id!)}>티켓 열기</Button>
        </Card>
      ) : (
        <Card className="gap-5 p-6">
          <div className="flex items-center justify-between gap-3">
            <h2 className="flex items-center gap-2 text-lg font-semibold"><AiMark />AI 분석 · 담당 부서</h2>
            {analyzing && <span className="flex items-center gap-2 text-sm text-muted-foreground"><Loader2 className="size-4 animate-spin" aria-hidden />AI가 유형·제품·긴급도를 분석하고 있습니다…</span>}
          </div>
          {failed && <p className="rounded-xl bg-destructive/10 px-4 py-3 text-sm text-destructive">분석을 요청하지 못했습니다: {failed} <Button size="sm" variant="outline" className="ml-2" onClick={() => void run()}>다시 시도</Button></p>}
          {analysis?.error && <p className="rounded-xl bg-warning/20 px-4 py-3 text-sm text-warning-ink">AI 분석에 실패했습니다 ({analysis.error}). 유형을 직접 고르고 등록하면 처리 흐름이 다시 분석합니다.</p>}

          {(analysis || failed) && (
            <div className="grid grid-cols-2 gap-4">
              <Field label={<>유형 {analysis?.classification && <small>· {analysis.category_by === "reviewer" ? "담당자 선택" : `AI 판단 · 확신도 ${Math.round(analysis.classification.confidence * 100)}%`}</small>}</>}>
                <NativeSelect value={category} onChange={(e) => setCategory(e.target.value)} disabled={analyzing || registering}>
                  <option value="">유형 선택</option>
                  {Object.entries(CATEGORY_LABEL).map(([code, label]) => <option key={code} value={code}>{label} ({code})</option>)}
                </NativeSelect>
              </Field>
              <Field label={<>제품 {extraction && <small>· {analysis?.product_by === "reviewer" ? "담당자 선택" : aiProduct ? "AI 추출" : "AI가 찾지 못함"}</small>}</>}>
                <NativeSelect value={product} onChange={(e) => setProduct(e.target.value)} disabled={analyzing || registering}>
                  <option value="">미확인</option>
                  {families.map(([family, label]) => (
                    <optgroup key={family} label={label}>
                      {products.filter((p) => p.family === family).map((p) => <option key={p.code} value={p.code}>{p.name} ({p.code})</option>)}
                    </optgroup>
                  ))}
                  {product && !products.some((p) => p.code === product) && <option value={product}>{product}</option>}
                </NativeSelect>
              </Field>
            </div>
          )}

          {extraction && (
            <Facts rows={[
              ["긴급도", <Tag key="u" tone={extraction.urgency === "SAFETY" ? "red" : extraction.urgency === "NONE" ? "" : "amber"}>{URGENCY_LABEL[extraction.urgency] || extraction.urgency}</Tag>],
              ["오류 코드", extraction.error_code ? <Mono key="e">{extraction.error_code}</Mono> : "없음"],
              ["펌웨어", extraction.fw_version || "미기재"],
            ]} />
          )}

          {rules && (
            <section className={cn("grid gap-3 rounded-xl bg-accent/70 p-4", dirty && "opacity-50")}>
              <div className="flex items-baseline justify-between gap-3">
                <span className="text-sm text-muted-foreground">담당 부서</span>
                <small className="text-muted-foreground">규칙 <Mono>{rules.routing_rule_id}</Mono></small>
              </div>
              <strong className="text-xl">{DEPT_LABEL[rules.assigned_dept] || rules.assigned_dept} <Mono className="text-sm font-normal text-muted-foreground">{rules.assigned_dept}</Mono></strong>
              <Facts rows={[
                ["우선순위", <span key="p" className="flex items-center gap-2"><PriorityTag p={rules.priority} /><small className="text-muted-foreground">규칙 <Mono>{rules.priority_rule_id}</Mono></small></span>],
                ["SLA", `첫 응답 ${rules.sla_first_response_h}시간 · 해결 ${rules.sla_resolution_h}시간`],
                ["다음 단계", analysis?.route ? ROUTE_LABEL[analysis.route] : "-"],
                ...(rules.escalate_to ? [["이관 예정", DEPT_LABEL[rules.escalate_to] || rules.escalate_to] as [string, React.ReactNode]] : []),
                ["빠진 정보", rules.missing_info.length ? (
                  <ul key="m" className="grid gap-1">{rules.missing_info.map((f) => (
                    <li key={f} className="flex items-center gap-2">{analysis?.field_labels[f] || f}{rules.missing_blocking.includes(f) && <Tag tone="red">필수</Tag>}</li>
                  ))}</ul>
                ) : "없음"],
              ]} />
            </section>
          )}

          {(analysis || failed) && (
            <div className="flex flex-wrap items-center justify-end gap-2.5 border-t pt-4">
              {dirty && !analysis?.error && <small className="mr-auto text-muted-foreground">바꾼 유형·제품으로 다시 분석하면 담당 부서가 다시 정해집니다.</small>}
              {registering && <span className="mr-auto flex items-center gap-2 text-sm text-muted-foreground"><Loader2 className="size-4 animate-spin" aria-hidden />티켓을 등록하고 있습니다. 근거 검색과 답변 초안까지 준비합니다 (1~2분).</span>}
              {dirty && !analysis?.error && <Button variant="outline" disabled={analyzing || registering} onClick={() => void rerun()}>바꾼 값으로 다시 분석</Button>}
              <Button disabled={!canRegister} onClick={() => void register()}>티켓으로 등록</Button>
            </div>
          )}
        </Card>
      )}
    </div>
  );
}
