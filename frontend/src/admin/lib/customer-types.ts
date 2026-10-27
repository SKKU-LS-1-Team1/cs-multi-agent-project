export type Customer = {
  id: string; name: string; c: string; cn: string; tier: "PLATINUM" | "GOLD" | "STANDARD"; seg: string; since: string;
  n: number; // 12개월 문의 수
  breach: number; // 12개월 동안 SLA 를 넘긴 횟수
  last: string;
  fam: [string, number][]; // 자주 문의한 제품군
  urgent: [string, string, string, number, number, string][]; // 해결 기한을 넘겼거나 넘기기 직전인 진행 중 티켓 전부(가장 지연된 순): id, 제목, 우선순위, 해결 목표(시간), 경과(시간), 상태
  urgentN: number;
  notice_tickets: { id: string; title: string; status: string; language: string | null }[];
  safety: [string, string][];
  t: [string, string, string, string, string, string, string, string][]; // 최근 문의: id, 날짜, 제목, 유형, 제품군, 우선순위, 상태, SLA
};
