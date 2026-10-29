# 업무 메일함 (CSA-74 · 김동규)
# 앞단(문의서·챗봇)을 거치지 않고 메일로 바로 온 문의를 담당자가 티켓으로 등록한다.
#
# 흐름: 메일 목록 → 메일 하나 열기 → AI 분석(analyze) → 담당자 검토(유형·제품 고치면 다시 분석)
#       → 등록(register) = 문의 관리의 티켓 하나. 등록한 메일은 목록에 "등록됨" + 티켓 번호.
#
# - 메일: data/raw/tickets.csv 의 valid 분할 EMAIL 문의를 유형마다 MAILS_PER_CATEGORY 건씩 고른다
#   (train 은 사례 학습용, test 는 최종 평가용이라 쓰지 않는다). 받은 시각은 원래 순서를 지키며 지금
#   기준 최근 시각으로 옮겨 보여 준다. 원천 파일이 없으면 빈 메일함.
# - 분석(analyze): 처리 흐름과 같은 함수(GraphDeps 의 classify · extract · translate)와 규칙
#   (rules/engine.apply_rules)을 티켓을 만들지 않고 돌린다 → 유형 · 제품 · 긴급도 · 담당 부서 ·
#   우선순위 · SLA · 빠진 정보 · 다음 단계. 담당자가 유형이나 제품을 고르면 그 값으로 다시 분석하고
#   (유형을 고르면 분류는 LLM 없이 그 값), 부서·우선순위는 규칙이 다시 정한다. 결과는 메일 · 고른 값
#   별로 캐시한다 (같은 메일을 다시 열어도 LLM 을 다시 부르지 않는다).
# - 등록(register): 담당자가 확인한 유형 · 제품을 실어 TicketService.submit 에 넣는다. 처리 흐름이
#   같은 규칙으로 부서를 정하므로 검토한 부서와 티켓의 부서가 같다. thread_ref = "mail:<메일 id>" 라
#   두 번 눌러도 티켓은 하나다 (이미 등록됐으면 그 티켓을 돌려준다). 등록 여부도 이 키로
#   records 에서 찾아서 서버를 다시 켜도(DB) 유지된다.
import csv
import logging
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Lock
from typing import Any

from pydantic import BaseModel

from cs_agent.agents.analysis import AnalysisError
from cs_agent.config import get_settings
from cs_agent.domain import Category, Urgency
from cs_agent.rules.engine import apply_rules
from cs_agent.schemas import Classification, Extraction, InquiryIn, RuleResult, TicketOut

_LOGGER = logging.getLogger(__name__)

MAILS_PER_CATEGORY = 2
MAIL_SPACING = timedelta(minutes=37)  # 메일함에 보여 줄 받은 시각 간격
THREAD_PREFIX = "mail:"


class MailNotFound(KeyError):
    pass


@dataclass(frozen=True)
class Mail:
    mail_id: str
    received_at: datetime
    sender: str
    company: str
    customer_id: str | None
    customer_tier: str
    country: str | None
    language: str | None
    subject: str
    body: str

    def inquiry(self, category: Category | None = None, product_code: str | None = None):
        return InquiryIn(
            channel="EMAIL",
            customer_id=self.customer_id,
            customer_tier=self.customer_tier,
            country=self.country,
            language=self.language,
            subject=self.subject,
            body=self.body,
            category=category,
            product_code=product_code,
            thread_ref=f"{THREAD_PREFIX}{self.mail_id}",
            received_at=self.received_at,
        )


class MailOut(BaseModel):
    mail_id: str
    received_at: datetime
    sender: str
    company: str
    customer_tier: str
    country: str | None
    language: str | None
    subject: str
    body: str
    ticket_id: str | None = None  # 등록했으면 티켓 번호
    analyzed: bool = False


class MailAnalyzeIn(BaseModel):
    """담당자가 고친 값. 없으면 AI 가 정한다."""

    category: Category | None = None
    product_code: str | None = None


class MailRegisterIn(MailAnalyzeIn):
    category: Category  # 등록은 담당자가 확인한 유형으로
    reviewer: str = ""


class MailAnalysis(BaseModel):
    mail_id: str
    classification: Classification | None = None
    extraction: Extraction | None = None
    rules: RuleResult | None = None
    route: str | None = None  # draft | info_request | human
    body_ko: str | None = None  # 상담원용 한국어 번역 (실패하면 없음)
    field_labels: dict[str, str] = {}  # 필수정보 항목 이름 (티켓 화면과 같은 info_field_codebook)
    error: str | None = None  # 분석 실패 (등록하면 처리 흐름이 분석 대기로 다시 돈다)
    category_by: str = "ai"  # ai | reviewer
    product_by: str = "ai"


def load_mails(
    path: Path | None = None, now: datetime | None = None, per_category: int = MAILS_PER_CATEGORY
) -> list[Mail]:
    """valid 분할 EMAIL 문의를 유형마다 per_category 건 (받은 순서), 최근 것이 위."""
    path = path or get_settings().raw_data_dir / "tickets.csv"
    if not path.is_file():
        _LOGGER.warning("메일함 원천 데이터가 없다 → 빈 메일함: %s", path)
        return []
    with path.open(encoding="utf-8-sig", newline="") as f:
        rows = [
            r for r in csv.DictReader(f) if r["channel"] == "EMAIL" and r["data_split"] == "valid"
        ]
    rows.sort(key=lambda r: (r["received_at_utc"], r["ticket_id"]))
    picked: list[dict] = []
    counts: dict[str, int] = {}
    for row in rows:
        if counts.get(row["category_code"], 0) < per_category:
            counts[row["category_code"]] = counts.get(row["category_code"], 0) + 1
            picked.append(row)
    now = (now or datetime.now(UTC)).replace(microsecond=0)
    return [
        Mail(
            mail_id=f"MAIL-{row['ticket_id'].rsplit('-', 1)[-1]}",
            received_at=now - MAIL_SPACING * (i + 1),
            sender=row["contact_email_masked"],
            company=row["company_masked"],
            customer_id=row["customer_id"] or None,
            customer_tier=row["customer_tier"] or "STANDARD",
            country=row["country"] or None,
            language=row["language"] or None,
            subject=row["inquiry_subject"],
            body=row["inquiry_body"],
        )
        for i, row in enumerate(reversed(picked))
    ]


def route_of(extraction: Extraction, rules: RuleResult) -> str:
    """처리 흐름의 다음 단계와 같은 규칙 (graph/builder.py rules 노드)."""
    if extraction.urgency == Urgency.SAFETY:
        return "human"
    return "info_request" if rules.missing_blocking else "draft"


class Mailbox:
    def __init__(
        self,
        mails: Sequence[Mail],
        tickets: Any,
        *,
        classify: Callable,
        extract: Callable,
        translate: Callable | None,
        llm: Any,
        tables: Any,
    ) -> None:
        self.mails = {m.mail_id: m for m in mails}
        self.order = [m.mail_id for m in mails]
        self.tickets = tickets
        self.classify, self.extract, self.translate = classify, extract, translate
        self.llm, self.tables = llm, tables
        self._analyses: dict[tuple[str, str | None, str | None], MailAnalysis] = {}
        self._lock = Lock()

    @classmethod
    def from_deps(cls, mails: Sequence[Mail], tickets: Any, deps: Any) -> "Mailbox":
        return cls(
            mails,
            tickets,
            classify=deps.classify,
            extract=deps.extract,
            translate=deps.translate,
            llm=deps.llm,
            tables=deps.tables,
        )

    def _mail(self, mail_id: str) -> Mail:
        try:
            return self.mails[mail_id]
        except KeyError:
            raise MailNotFound(mail_id) from None

    def ticket_of(self, mail_id: str) -> str | None:
        return self.tickets.records.find_thread(f"{THREAD_PREFIX}{mail_id}")

    def list(self) -> list[MailOut]:
        analyzed = {key[0] for key in self._analyses}
        return [self._out(self.mails[m], m in analyzed) for m in self.order]

    def get(self, mail_id: str) -> MailOut:
        mail = self._mail(mail_id)
        return self._out(mail, any(key[0] == mail_id for key in self._analyses))

    def _out(self, mail: Mail, analyzed: bool) -> MailOut:
        return MailOut(
            mail_id=mail.mail_id,
            received_at=mail.received_at,
            sender=mail.sender,
            company=mail.company,
            customer_tier=mail.customer_tier,
            country=mail.country,
            language=mail.language,
            subject=mail.subject,
            body=mail.body,
            ticket_id=self.ticket_of(mail.mail_id),
            analyzed=analyzed,
        )

    # 분석 ---------------------------------------------------------------------------------------

    def analyze(self, mail_id: str, change: MailAnalyzeIn | None = None) -> MailAnalysis:
        mail = self._mail(mail_id)
        change = change or MailAnalyzeIn()
        product = (change.product_code or "").strip() or None
        key = (mail_id, change.category and change.category.value, product)
        with self._lock:
            if key in self._analyses:
                return self._analyses[key]
        result = self._analyze(mail, change.category, product)
        with self._lock:
            self._analyses[key] = result
        return result

    def _analyze(self, mail: Mail, category: Category | None, product: str | None) -> MailAnalysis:
        inquiry = mail.inquiry(category, product)
        result = MailAnalysis(
            mail_id=mail.mail_id,
            category_by="reviewer" if category else "ai",
            product_by="reviewer" if product else "ai",
        )
        # 번역은 분석과 따로 돈다 (처리 흐름처럼). 이미 번역했으면 다시 부르지 않는다
        body_ko = next(
            (a.body_ko for k, a in self._analyses.items() if k[0] == mail.mail_id and a.body_ko),
            None,
        )
        with ThreadPoolExecutor(max_workers=1) as pool:
            job = None
            if body_ko is None and self.translate is not None:
                job = pool.submit(self.translate, mail.body, mail.language, self.llm)
            try:
                classification = self.classify(inquiry, self.llm)
                extraction = self.extract(
                    inquiry, self.tables, llm=self.llm, category=classification.category
                )
            except AnalysisError as e:
                result.error = str(e) or type(e).__name__
            except (
                Exception
            ) as e:  # LLM 장애 등 — 화면에 알리고, 등록하면 처리 흐름이 다시 분석한다
                _LOGGER.exception("메일 분석 실패: %s", mail.mail_id)
                result.error = f"{type(e).__name__}: {e}"
            else:
                rules = apply_rules(classification, extraction, mail.customer_tier, self.tables)
                result.classification = classification
                result.extraction = extraction
                result.rules = rules
                result.route = route_of(extraction, rules)
                labels = getattr(self.tables, "field_labels", {})
                result.field_labels = {k: labels.get(k, k) for k in rules.required_info}
            if job is not None:
                try:
                    body_ko = job.result(timeout=get_settings().inquiry_translation_timeout_s)
                except FutureTimeout:
                    _LOGGER.warning("메일 번역 시간 초과: %s", mail.mail_id)
                except Exception:
                    _LOGGER.exception("메일 번역 실패: %s", mail.mail_id)
        result.body_ko = body_ko
        return result

    # 등록 ---------------------------------------------------------------------------------------

    def register(self, mail_id: str, body: MailRegisterIn) -> TicketOut:
        """확인한 유형 · 제품으로 티켓을 만든다. 이미 등록한 메일이면 그 티켓."""
        mail = self._mail(mail_id)
        if existing := self.ticket_of(mail_id):
            return self.tickets.get(existing)
        product = (body.product_code or "").strip() or None
        return self.tickets.submit(mail.inquiry(body.category, product))
