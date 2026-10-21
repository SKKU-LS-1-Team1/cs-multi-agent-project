// 레거시 프로토타입의 티켓/이벤트는 동적 필드가 많아 핵심 필드만 타입으로 고정하고 나머지는 열어 둔다.
export type Ev = { kind: string; text?: string; time?: string; createdAt?: string; actor?: string; id?: string; [k: string]: any };

export type Ticket = {
  id: string;
  title: string;
  product: string;
  country: string;
  company: string;
  type: string;
  priority: string;
  status: string;
  sla: string;
  owner: string;
  language: string;
  stage: number; // 0 진행, 5 완료
  risk: boolean;
  events: Ev[];
  draft: string;
  files: string[];
  reviewed: boolean;
  [k: string]: any;
};

export type Person = {
  name: string;
  department: string;
  capacity: number;
  skills: string[];
  languages: string[];
  available: boolean;
};

export type ModalState = { type: string; props?: Record<string, any> } | null;
