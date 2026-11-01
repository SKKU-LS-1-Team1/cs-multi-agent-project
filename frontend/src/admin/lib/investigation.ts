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

/** Local composer intent can differ from the last saved server state. Never show its old advice. */
export function copilotMode(t: Ticket, choice: string | null = null): string {
  if (t.stage === 5 || t.sent) return "closed";
  if (t.apiStatus === "ANALYSIS_PENDING") return "analysis_pending";
  if (t.customerRequestStatus === "waiting") return "wait_customer";
  if (t.activeComposer === "expert") return "specialist_prepare";
  if (t.purpose === "request" && t.draft) return "customer_request";
  const task = investigationTask(t);
  if (task) return task.kind === "request" ? "customer_request"
    : task.kind === "progress" ? "wait_specialist" : "specialist_review";
  if (t.specialistRequests?.some((r: any) => !r.reply)) return "wait_specialist";
  if (t.purpose === "answer" && t.draft && t.composerOpen) return "customer_answer";
  if (choice) return { request: "customer_request", answer: "customer_answer", expert: "specialist_prepare" }[choice] || "manual_review";
  if (t.purpose === "answer" && t.draft) return "customer_answer";
  return t.copilot?.workflow?.mode || "manual_review";
}

export function referralSuggestions(t: Ticket) {
  // Merely having a defect, a potential department, or a draft customer answer isn't referral intent.
  if (t.activeComposer !== "expert" || copilotMode(t) !== "specialist_prepare"
    || t.specialistRequests?.length || !["READY_FOR_REVIEW", "ON_HOLD"].includes(t.apiStatus)) return [];
  return (t.copilot?.request_plan || []).filter((r: any) => r.origin === "recommended" && r.status !== "confirmed");
}


const REASON_TITLES: Record<string, string> = {
  customer_request: "추가정보가 필요한 이유",
  customer_answer: "답변 작성 근거",
  specialist_prepare: "전문부서 검토가 필요한 이유",
  specialist_review: "회신에서 확인할 사항",
  wait_customer: "고객 회신 대기 내용",
  wait_specialist: "전문부서 회신 대기 내용",
  manual_review: "담당자 검토가 필요한 이유",
  analysis_pending: "분석 대기 내용",
  closed: "처리 결과",
};

/** One presentation policy for the current action, requested fields and supporting material. */
export function copilotPresentation(t: Ticket, choice: string | null = null) {
  const mode = copilotMode(t, choice);
  const plan = t.copilot?.request_plan || [];
  const workflow = t.copilot?.workflow;
  const requestFields = mode !== "customer_request" ? [] : workflow?.mode === mode
    ? workflow.request_fields
    : plan.filter((row: any) => row.origin !== "recommended" && row.status !== "confirmed").map((row: any) => row.field);
  const rows = requestFields.map((field: string) => plan.find((row: any) => row.field === field))
    .filter((row: any) => row && row.status !== "confirmed");
  return {
    mode,
    requestRows: rows,
    reasonTitle: REASON_TITLES[mode] || "검토 근거",
    showTechnicalContext: ["customer_answer", "specialist_prepare", "specialist_review"].includes(mode),
    showUnresolved: !["customer_request", "wait_customer", "wait_specialist", "closed"].includes(mode),
    showNextReason: mode !== "customer_request" && workflow?.mode === mode,
  };
}

const REQUEST_LABELS: Record<string, string> = {
  product_model: "제품 모델", serial_no: "시리얼 번호", error_code: "오류 코드",
  current_fw: "현재 설치된 펌웨어 버전", photos: "제품·명판 사진", logs: "장비 로그",
  quantity: "수량", operating_condition: "문제 발생 당시 운전 조건", load_type: "연결된 부하 종류",
  motor_nameplate: "모터 명판 정보", cable_length: "모터 케이블 길이", carrier_frequency: "캐리어 주파수",
  accel_decel_time: "가속·감속 시간",
};
export function requestFieldLabel(field: string, fallback: string) { return REQUEST_LABELS[field] || fallback; }
