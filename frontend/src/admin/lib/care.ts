// 고객 조치 기록: 누구에게 무슨 조치를 했는지, 다음 확인 일정, 해소 여부. 이 브라우저에만 저장하는 모의 저장소다.
import { useSyncExternalStore } from "react";
import { signedIn } from "./logic";
import type { ProgressNotice } from "../../api/client";

export type CareKind = "notice" | "notice_draft" | "close"; // close = 결과 확인 후 종결(시스템이 남기는 기록)
export type CareAction = { id: string; kind: CareKind; text: string; at: string; by: string; ticketIds?: string[]; language?: string; noticeId?: string; originalText?: string; finalText?: string };
export type CareNote = { id: string; text: string; at: string; by: string };
export type CareRecord = { actions: CareAction[]; followUp?: string; resolved?: boolean; pinned?: boolean; notes?: CareNote[] };
export type CareStatus = "none" | "acted" | "due" | "resolved";

export const KIND_LABEL: Record<CareKind, string> = { notice: "진행 상황 안내", notice_draft: "안내문 초안 보관", close: "종결" };
/** 예전에 저장된 기록의 종류(경과 안내·담당자 변경 등)도 이름이 나오게 한다. */
export const kindLabel = (k: string) => (KIND_LABEL as Record<string, string>)[k] ?? ({ apology: "경과 안내", assign: "담당자 변경", followup: "결과 확인", rootcause: "원인 분석 요청" } as Record<string, string>)[k] ?? "대응";
// BACKEND: 고객 대응 기록(중점 관리의 대응·종결·직접 지정)
// 필요(제안): GET   /customers/{id}/care                 → { actions[], follow_up, resolved, pinned }
//            POST  /customers/{id}/care-actions         { kind, text, follow_up? }   (kind: notice · close)
//            PATCH /customers/{id}/care                 { resolved?, pinned?, follow_up? }
// 상태(미대응 → 대응 중 → 결과 확인 → 종결)는 이 값에서 계산한다(careStatus). 결과 확인 예정일이 오늘 이전이면 "결과 확인".
// 지금: 이 브라우저 localStorage("ls-admin-care-v1")에만 저장한다.
// 내부 메모(상담원끼리 공유, 고객에게 보이지 않음): GET /customers/{id}/notes, POST /customers/{id}/notes { text }  — 작성자·시각은 서버가 붙인다.
// 참고: 결과 확인 예정일은 대응할 때 7일 뒤로 자동 설정한다. 진행 안내문은 본문을 로컬 초안으로 보관하며 실제 발송·대응 완료로 집계하지 않는다.
const KEY = "ls-admin-care-v1";
let state: Record<string, CareRecord> = {};
try { state = JSON.parse(localStorage.getItem(KEY) || "{}") || {}; } catch { /* 저장소를 못 읽으면 빈 기록으로 시작 */ }
const listeners = new Set<() => void>();
const emit = () => { state = { ...state }; try { localStorage.setItem(KEY, JSON.stringify(state)); } catch { /* 저장 실패는 무시 */ } listeners.forEach((l) => l()); };

export const useCare = () => useSyncExternalStore((l) => { listeners.add(l); return () => { listeners.delete(l); }; }, () => state);
export const recordOf = (id: string): CareRecord => state[id] || { actions: [] };
const day = (iso: string) => iso.slice(0, 10);
export const addDays = (n: number) => { const d = new Date(); d.setDate(d.getDate() + n); return d.toISOString().slice(0, 10); };

export function careStatus(r: CareRecord | undefined): CareStatus {
  if (!r) return "none";
  if (r.resolved) return "resolved";
  if (!r.actions.some((a) => a.kind !== "notice_draft")) return "none";
  return r.followUp && r.followUp <= day(new Date().toISOString()) ? "due" : "acted";
}
export function addCareAction(customerId: string, kind: CareKind, text: string, followUp?: string, details: { ticketIds?: string[]; language?: string } = {}) {
  const cur = state[customerId] || { actions: [] };
  state[customerId] = {
    ...cur, resolved: kind === "notice_draft" ? cur.resolved : false, followUp: kind === "notice_draft" ? cur.followUp : followUp ?? cur.followUp ?? addDays(7),
    actions: [{ id: crypto.randomUUID(), kind, text, at: new Date().toISOString(), by: signedIn, ...details }, ...cur.actions],
  };
  emit();
}
/** Server-prepared copy is a saved draft, never a sent message or completed customer action. */
export function rememberProgressNotice(notice: ProgressNotice) {
  if (notice.status !== "prepared" || !notice.approved_text || !notice.final_text) return;
  const cur = state[notice.customer_id] || { actions: [] }, id = `notice:${notice.notice_id}`;
  const action: CareAction = { id, kind: "notice_draft", text: `발송용 문구 준비 · 실제 발송 안 함\n${notice.final_text}`,
    at: notice.approved_at || notice.created_at, by: notice.reviewer || signedIn, ticketIds: notice.ticket_ids,
    noticeId: notice.notice_id, language: notice.target_language, originalText: notice.approved_text, finalText: notice.final_text };
  state[notice.customer_id] = { ...cur, actions: [action, ...cur.actions.filter((a) => a.id !== id)] };
  emit();
}
/** 중점 관리 수동 지정/해제(영업 요청이나 상담원 판단). */
export function setPinned(customerId: string, pinned: boolean) {
  const cur = state[customerId] || { actions: [] };
  state[customerId] = { ...cur, pinned };
  emit();
}
/** 내부 메모 추가(고객에게 보이지 않는, 상담원끼리 공유하는 특이사항). */
export function addNote(customerId: string, text: string) {
  const cur = state[customerId] || { actions: [] };
  state[customerId] = { ...cur, notes: [{ id: crypto.randomUUID(), text: text.trim(), at: new Date().toISOString(), by: signedIn }, ...(cur.notes || [])] };
  emit();
}
export function resolveCare(customerId: string, resolved: boolean) {
  const cur = state[customerId]; if (!cur) return;
  state[customerId] = { ...cur, resolved, followUp: resolved ? cur.followUp : addDays(7) };
  if (resolved) state[customerId].actions = [{ id: crypto.randomUUID(), kind: "close", text: "결과 확인 후 종결", at: new Date().toISOString(), by: signedIn }, ...cur.actions];
  emit();
}
