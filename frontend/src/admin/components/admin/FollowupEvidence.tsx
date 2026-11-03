import type { FollowupLink, FollowupQuote } from "../../../api/client";

/** The link judgement already contains validated quotes. Opening the panel makes no AI call. */
export function FollowupEvidence({ link }: { link?: FollowupLink | null }) {
  if (!link || link.dismissed) return null;
  const unique = new Map<string, FollowupQuote>();
  for (const ref of [...(link.references || []), ...(link.previous_response?.references || [])]) {
    unique.set(`${ref.source_id}\n${ref.quote}`, ref);
  }
  const current = [...unique.values()].filter((ref) => ref.source_id === "current");
  const previous = [...unique.values()].filter((ref) => ref.source_id !== "current");
  const quotes = (items: FollowupQuote[]) => items.map((ref) => (
    <blockquote key={`${ref.source_id}:${ref.quote}`} className="border-l-2 border-info/30 pl-3 text-sm leading-relaxed whitespace-pre-wrap [overflow-wrap:anywhere]">{ref.quote}</blockquote>
  ));
  return <div className="grid min-w-0 gap-3 text-[15px] leading-[1.7] [overflow-wrap:anywhere]">
    <div className="rounded-2xl bg-[#026bb4]/[0.06] p-4">
      <p className="mb-1 font-semibold">연결 이유</p>
      <p>{link.reason}</p>
    </div>
    <dl className="grid gap-3 rounded-2xl bg-muted/50 p-4">
      <div><dt className="font-semibold">이전 대응</dt><dd className="mt-1 text-muted-foreground">{link.previous_response?.text || "이전 대응 요약이 없습니다. 아래 원문을 확인해 주세요."}</dd></div>
      <div><dt className="font-semibold">이번 접수에서 추가된 내용</dt><dd className="mt-1">{link.new_information || "별도로 확인된 추가 내용이 없습니다."}</dd></div>
    </dl>
    {(previous.length > 0 || current.length > 0) && <details className="min-w-0 rounded-xl border border-border p-3 text-sm">
      <summary className="cursor-pointer font-medium text-muted-foreground">근거 원문 보기</summary>
      <div className="mt-3 grid gap-4">
        {previous.length > 0 && <div className="grid gap-2"><p className="font-semibold">이전 문의 · {link.previous_ticket_id}</p>{quotes(previous)}</div>}
        {current.length > 0 && <div className="grid gap-2"><p className="font-semibold">이번 접수 원문</p>{quotes(current)}</div>}
      </div>
    </details>}
  </div>;
}
