# 고객 화면 · 관리자 프로토타입

```bash
cd frontend
npm ci
npm run dev
```

Vite가 출력한 주소에서 고객 화면은 `/`, 관리자 화면은 `/admin/`으로 엽니다.
관리자 프로토타입은 백엔드 없이 실행할 수 있습니다. 고객 화면의 기존 `/api` 프록시는
그대로 로컬 FastAPI(8000)를 사용합니다.

## 관리자 화면 이식 범위

`admin-workspace`의 React 소스를 `src/admin/`에 복사했습니다.
원본 폴더, `legacy/`, `node_modules`, `.env`, 빌드 결과물은 이식 대상이 아닙니다.
React·React DOM을 19.3.1로 올리고 관련 타입과 관리자 UI 의존성을 함께 반영했습니다.

현재 관리자 화면은 **API 미연결 프로토타입**입니다.

- 티켓·처리 이력은 브라우저 localStorage의 `cs-agent-admin-prototype-v1`에 저장합니다.
- 초안 생성·번역·승인·발송·배정·전문부서 회신은 기존 로컬 시뮬레이션입니다.
- 실제 이메일 발송, DB 갱신, LLM 호출을 하지 않습니다.
- `src/admin/data/knowledge-data.js`는 원본 프로토타입의 정적 사례·문서 데이터입니다.
- 실제 API 연동은 후속 작업입니다. 기존 `src/api/client.ts`와 관리자 스켈레톤
  `src/pages/admin/`은 보존했습니다.

## 경로와 구조

| 경로 | 화면 |
| --- | --- |
| `/admin/` | 고객지원 업무 현황 |
| `/admin/collab` | 전문부서 협업 |
| `/admin/resources` | 리소스 배정 |
| `/admin/tickets` | 티켓 목록 |
| `/admin/tickets/:ticketId` | 티켓 상세 |
| `/admin/knowledge` | 지식·해결 사례 |

이전 `/admin/dashboard` 주소는 관리자 업무 현황으로 이동합니다.
관리자 내부 경로는 `BrowserRouter basename="/admin"`으로 처리합니다.
`@admin/*` 별칭은 `src/admin/*`를 가리킵니다.

고객용 `index.html`과 관리자용 `admin/index.html`을 같은 Vite 빌드로 생성합니다.
각각 별도 문서로 열어 관리자 Tailwind reset·테마가 고객 화면에 영향을 주지 않게 했습니다.
고객 화면에서 관리자 화면으로 이동하는 링크는 문서를 전환하는 일반 링크입니다.

개발·미리보기에서는 Vite가 `/admin/*`를 관리자 HTML로 연결하며,
배포에서는 `infra/nginx/nginx.conf`의 `/admin/` 규칙이 같은 역할을 합니다.
기존 Dockerfile의 `npm run build`로 두 화면이 함께 빌드됩니다.

## 확인

```bash
npm run build
npm run preview
```

타입 검사 및 고객·관리자 빌드, 관리자 티켓 상세 새로고침, 메뉴 이동,
모달 열기·닫기, 로컬 초안 작성, 고객 화면 진입을 확인합니다.
정적 사례 데이터가 포함돼 관리자 번들 크기 경고가 있습니다.
데이터 API 연결과 분할 로딩은 후속 작업에서 다룹니다.
