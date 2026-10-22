// 대응 버튼. 줄(목록)에서는 사실에 맞는 버튼 하나. 상태가 대응 중·결과 확인·종결이면 그 상태에 맞는 표시/버튼으로 바뀐다.
// 결과 확인 예정일이 되면 "종결 / 계속 확인", 종결 뒤에는 "재개".
import { Button } from "@admin/components/ui/button";
import { careStatus, KIND_LABEL, recordOf, resolveCare, useCare, type CareKind } from "@admin/lib/care";
import { primaryReason, type Customer, type Reason } from "@admin/lib/customers";
import { openModal } from "@admin/lib/store";
import { AiMark } from "./common";
import { cn } from "@admin/lib/utils";

/** AI 가 초안을 만들어 주는 대응(진행 상황 안내). */
export const AI_KINDS: CareKind[] = ["notice"];
export const AI_STYLE = "border-0 bg-gradient-to-r from-[#003377] to-[#026bb4] text-white hover:opacity-90";

/** 대응 버튼은 지연·임박 문의에만 있다. 지연 이력과 반복 문의는 참고 정보라 버튼이 없다. */
const ALL: Record<Reason, CareKind[]> = { urgent: ["notice"], breach: [], repeat: [] };
const day = (iso: string) => iso.slice(5, 10).replace("-", ".");

export function CareButtons({ c, reason }: { c: Customer; reason?: Reason }) {
  const care = useCare(), status = careStatus(care[c.id]), rec = recordOf(c.id);
  const r = reason || primaryReason(c), kinds = r ? ALL[r] : [];
  const run = (k: CareKind) => openModal("care", { customerId: c.id, kind: k });
  if (status === "due") return <div className="flex gap-2"><Button size="sm" onClick={() => resolveCare(c.id, true)}>종결</Button><Button size="sm" variant="outline" onClick={() => resolveCare(c.id, false)}>계속 확인</Button></div>;
  if (status === "resolved") return <Button size="sm" variant="ghost" onClick={() => resolveCare(c.id, false)}>재개</Button>;
  if (!kinds.length) return null;
  if (status === "acted") return <span className="text-sm text-muted-foreground">대응 중{rec.followUp ? ` · ${day(rec.followUp)} 확인` : ""}</span>;
  return <Button size="sm" className={cn(AI_KINDS.includes(kinds[0]) && AI_STYLE)} onClick={() => run(kinds[0])}>{AI_KINDS.includes(kinds[0]) && <AiMark className="size-3.5 text-white" />}{KIND_LABEL[kinds[0]]}</Button>;
}

/** 대응 하나를 여는 버튼(AI 초안이 나오는 대응은 그라데이션 + ✦). 상세 화면에서 이유마다 하나씩 쓴다. */
export function ActionButton({ c, kind }: { c: Customer; kind: CareKind }) {
  const ai = AI_KINDS.includes(kind);
  return <Button size="sm" className={cn(ai && AI_STYLE)} onClick={() => openModal("care", { customerId: c.id, kind })}>{ai && <AiMark className="size-3.5 text-white" />}{KIND_LABEL[kind]}</Button>;
}
