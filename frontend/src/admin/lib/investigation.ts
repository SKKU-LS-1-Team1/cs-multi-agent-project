import type { Ticket } from "./types";

export const INVESTIGATION_STEPS: Record<string, string> = {
  triage: "1차 검토", serial_trace: "시리얼·출하 이력 추적",
  impact_assessment: "영향 범위 검토", reproduction_test: "재현 시험",
};

/** 회신 해석 결과는 제안이다. 고객 자료 확인과 담당자 최종 판정은 별도로 유지한다. */
export function investigationTask(t: Ticket) {
  const f = t.specialistFollowup;
  if (!f || f.status === "confirmed" || t.stage === 5 || t.sent || t.activeComposer === "expert") return null;
  if (t.purpose === "request" && t.draft && t.customerRequestStatus !== "waiting") return null;
  const missing: string[] = f.missing_fields || [];
  const labels = missing.map(field => t.fieldLabels?.[field] || field);
  const canRequest = ["READY_FOR_REVIEW", "ON_HOLD"].includes(t.apiStatus) && !t.manualReply;
  if (missing.length && t.customerRequestStatus !== "waiting" && canRequest) return {
    kind: "request", title: "사내 분석 중 · 추가자료 필요", task: "전문부서가 요청한 자료 중 아직 확인되지 않은 항목을 고객에게 요청하세요.",
    missing: labels,
  };
  if (!f.pending_replies && f.reading?.conclusion && !f.needs_review) return {
    kind: "confirm", title: "전문부서 검토 결과 도착", task: "전문부서의 검토 결과를 확인한 뒤 고객 답변에 반영하세요.", missing: [],
  };
  if (!f.reading && !f.pending_replies) return {
    kind: "analyze", title: "사내 분석 중 · 회신 확인 필요", task: f.error || "등록된 회신에서 진행 내용과 다음 행동을 확인하세요.", missing: [],
  };
  if (f.reading && f.needs_review) return {
    kind: "review", title: "사내 분석 중 · 담당자 확인 필요", task: "회신에 확인이 필요한 내용이 있습니다. 원문과 적용 조건을 검토하세요.", missing: [],
  };
  return { kind: "progress", title: "사내 분석 중", task: t.customerRequestStatus === "waiting"
    ? "고객에게 요청한 자료를 기다리고 있습니다. 현재까지의 진행상황을 안내할 수 있습니다."
    : "전문부서의 검토가 진행 중입니다. 필요하면 고객에게 진행상황을 안내하세요.", missing: [] };
}
