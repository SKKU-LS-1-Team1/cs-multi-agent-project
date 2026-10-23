import { api, type ProgressNotice } from "../../api/client";
import type { Ticket } from "./types";

export const noticeTickets = (customerId: string, rows: Ticket[]) => rows.filter((t) => t.source === "api" && t.apiCustomerId === customerId);
const selectionKey = (ids: string[]) => JSON.stringify([...new Set(ids)].sort());
const matches = (notice: ProgressNotice, ids: string[]) => selectionKey(notice.ticket_ids) === selectionKey(ids);
export type NoticeState = {
  ticketIds: string[]; text: string; notice: ProgressNotice | null;
  busy: "load" | "generate" | "prepare" | null; error: string;
};
export const preparedNotice = (s: NoticeState) => s.notice?.status === "prepared" &&
  s.notice.approved_text === s.text && matches(s.notice, s.ticketIds) && s.notice.final_text ? s.notice : null;

/** Each selection owns its requests. Late responses may not replace another selection or staff edits. */
export class NoticeSession {
  state: NoticeState = { ticketIds: [], text: "", notice: null, busy: null, error: "" };
  private epoch = 0;
  private editVersion = 0;
  private requestId: string | null = null;
  constructor(private notify: (state: NoticeState) => void) {}
  private update(patch: Partial<NoticeState>) { this.state = { ...this.state, ...patch }; this.notify(this.state); }
  select(ids: string[]) {
    this.epoch++; this.editVersion++; this.requestId = null;
    this.update({ ticketIds: [...new Set(ids)].sort(), text: "", notice: null, busy: null, error: "" });
  }
  dispose() { this.epoch++; }
  edit(text: string) { this.editVersion++; this.update({ text }); }
  async restore() {
    if (!this.state.ticketIds.length || this.state.busy) return;
    const epoch = this.epoch, edits = this.editVersion;
    this.update({ busy: "load", error: "" });
    try {
      const rows = await api.progressNotices(this.state.ticketIds[0]);
      if (epoch !== this.epoch) return;
      const notice = rows.filter((r) => matches(r, this.state.ticketIds)).sort((a, b) => b.created_at.localeCompare(a.created_at))[0];
      if (notice) this.update({ notice, ...(edits === this.editVersion ? { text: notice.approved_text ?? notice.draft_text ?? "" } : {}), error: notice.error || "" });
    } catch (error) { if (epoch === this.epoch) this.update({ error: `이전 안내문을 불러오지 못했습니다: ${error}` }); }
    finally { if (epoch === this.epoch) this.update({ busy: null }); }
  }
  async generate() {
    if (!this.state.ticketIds.length || this.state.busy) return false;
    const epoch = this.epoch, edits = this.editVersion;
    this.requestId ??= crypto.randomUUID();
    this.update({ busy: "generate", error: "" });
    try {
      const notice = await api.progressNotice(this.state.ticketIds[0], { notice_id: this.requestId, ticket_ids: this.state.ticketIds });
      if (epoch !== this.epoch) return false;
      if (!matches(notice, this.state.ticketIds) || notice.error || !notice.draft_text) {
        this.update({ error: notice.error || "영어 초안을 생성하지 못했습니다. 기존 작성 내용은 보존했습니다." }); return false;
      }
      this.requestId = null;
      this.update({ notice, ...(edits === this.editVersion ? { text: notice.approved_text ?? notice.draft_text } : {}) });
      return true;
    } catch (error) {
      if (epoch === this.epoch) {
        // A rejected snapshot cannot be retried under its old ID. Network failures keep it for idempotency.
        if (error && typeof error === "object" && "message" in error && /^409\b/.test(String(error.message))) this.requestId = null;
        this.update({ error: `초안 작성 실패: ${error}` });
      }
      return false;
    }
    finally { if (epoch === this.epoch) this.update({ busy: null }); }
  }
  async prepare(reviewer: string) {
    const { notice, text } = this.state;
    if (!notice || !text.trim() || this.state.busy) return null;
    if (notice.status === "prepared" && notice.approved_text !== text) {
      this.update({ error: "이미 확인한 안내문이 변경됐습니다. 다시 작성하여 새 안내문을 확인해 주세요." }); return null;
    }
    const epoch = this.epoch;
    this.update({ busy: "prepare", error: "" });
    try {
      const result = await api.prepareProgressNotice(notice.anchor_ticket_id, notice.notice_id, { reviewer, edited_text: text });
      if (epoch !== this.epoch) return null;
      if (!matches(result, this.state.ticketIds) || result.notice_id !== notice.notice_id) {
        this.update({ error: "선택한 문의의 안내문인지 확인할 수 없습니다. 다시 불러와 주세요." }); return null;
      }
      this.update({ notice: result, error: result.error || (result.status !== "prepared" || !result.final_text ? "고객 언어 문구를 준비하지 못했습니다. 영어 초안은 보존했습니다." : "") });
      return preparedNotice(this.state);
    } catch (error) { if (epoch === this.epoch) this.update({ error: `문구 준비 실패: ${error}` }); return null; }
    finally { if (epoch === this.epoch) this.update({ busy: null }); }
  }
}
