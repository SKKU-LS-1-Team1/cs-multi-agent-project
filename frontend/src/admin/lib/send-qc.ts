import type { CustomerQc } from "../../api/client";

/** 발송 전 QC 화면 상태. 실제 QC API 연결 전에는 서버 문의의 발송을 허용하지 않는다. */
export type QcIssue = { category: "abuse" | "confidential"; excerpt: string; reason: string };
export type QcResult = { status: "passed" } | { status: "blocked"; issues: QcIssue[] };
export type QcState =
  | { phase: "idle" | "checking" | "sending" | "sent" }
  | { phase: "blocked"; issues: QcIssue[] }
  | { phase: "error"; message: string };
export type QcInput = { sourceText: string; finalText: string; language: string };

export async function checkBeforeSend(_input: QcInput, demo: boolean): Promise<QcResult> {
  if (!demo) throw new Error("발송 전 AI 검증 서비스가 아직 연결되지 않았습니다. 발송되지 않았습니다.");
  // 예시 문의에서 화면 전환만 확인한다. 실제 내용 분석이나 AI 검증 결과가 아니다.
  await new Promise((resolve) => setTimeout(resolve, 700));
  return { status: "passed" };
}

export class SendQcSession {
  private running = false;
  private cancelled = false;
  private sent = false;
  constructor(private update: (state: QcState) => void) {}

  cancel() { this.cancelled = true; }

  /** One server request checks the exact stored preview and records approval atomically.
   * No browser timeout races a still-running server approval into a second send. */
  async runServer(submit: () => Promise<{ sent: boolean; qc?: CustomerQc | null; error?: string }>) {
    if (this.running || this.cancelled || this.sent) return;
    this.running = true;
    this.update({ phase: "checking" });
    try {
      const result = await submit();
      if (this.cancelled) return;
      if (result.sent && result.qc?.decision === "PASS") {
        this.sent = true;
        this.update({ phase: "sent" });
      } else if (result.qc?.decision === "BLOCK" || result.qc?.decision === "REVIEW") {
        this.update({ phase: "blocked", issues: result.qc.issues.map(issue => ({
          category: issue.category === "ABUSE" ? "abuse" : "confidential",
          excerpt: `${issue.paragraph_id.replace("p", "")}번 문단${issue.source_id ? ` · 제한 자료 ${issue.source_id}` : ""}`,
          reason: `${issue.reason} ${issue.suggestion}`,
        })) });
      } else {
        this.update({ phase: "error", message: result.qc?.message || result.error || "발송 완료를 확인하지 못했습니다. 문의 처리 이력을 확인해 주세요." });
      }
    } catch {
      if (!this.cancelled) this.update({ phase: "error", message: "발송 결과를 확인하지 못했습니다. 문의 처리 이력을 확인해 주세요." });
    } finally { this.running = false; }
  }

  async run(options: {
    input: QcInput;
    check: (input: QcInput) => Promise<QcResult>;
    isCurrent: () => boolean;
    send: () => Promise<boolean>;
    timeoutMs?: number;
  }) {
    if (this.running || this.cancelled || this.sent) return;
    this.running = true;
    this.update({ phase: "checking" });
    let timer: ReturnType<typeof setTimeout> | undefined;
    try {
      const result = await Promise.race([
        options.check({ ...options.input }),
        new Promise<never>((_, reject) => {
          timer = setTimeout(() => reject(new Error("검증 시간이 초과되었습니다. 발송되지 않았습니다. 다시 시도해 주세요.")), options.timeoutMs ?? 20000);
        }),
      ]);
      clearTimeout(timer);
      if (this.cancelled) return;
      if (!options.isCurrent()) throw new Error("검증 중 내용이나 문의 정보가 변경되었습니다. 최신 내용을 다시 확인해 주세요.");
      if (result?.status === "blocked" && Array.isArray(result.issues) && result.issues.length) {
        this.update({ phase: "blocked", issues: result.issues });
        return;
      }
      if (result?.status !== "passed") throw new Error("검증 결과를 확인할 수 없습니다. 발송되지 않았습니다.");
      this.update({ phase: "sending" });
      const sent = await options.send();
      if (!sent) throw new Error("발송이 완료되지 않았습니다. 내용을 확인한 후 다시 시도해 주세요.");
      this.sent = true;
      if (!this.cancelled) this.update({ phase: "sent" });
    } catch (error) {
      if (!this.cancelled) this.update({ phase: "error", message: error instanceof Error ? error.message : "검증을 완료하지 못했습니다. 발송되지 않았습니다." });
    } finally {
      clearTimeout(timer);
      this.running = false;
    }
  }
}
