import pytest
from fastapi.testclient import TestClient
from stubs import ANALYSIS

from cs_agent.config import Settings
from cs_agent.llm.router import LLMRouter
from cs_agent.main import create_app

INQUIRY = {
    "channel": "WEB_FORM",
    "language": "en",
    "subject": "Dimensions of TRF-OIL-1000",
    "body": "What are the dimensions and weight of TRF-OIL-1000?",
    "category": "TECH_SPEC",
    "provided_fields": {"application": "substation"},
    "thread_ref": "web-1",
}


@pytest.fixture
def client(tmp_path):
    with TestClient(
        create_app(
            llm=LLMRouter(Settings(_env_file=None)),
            agents=ANALYSIS,
            storage="memory",
            retrievers=(None, None),
            attachments_dir=tmp_path,
        )
    ) as c:
        yield c


def test_customer_sees_status_and_reply_but_not_the_ai_draft(client) -> None:
    """시연 흐름: 문의 → 상담원 검토 중(초안 안 보임) → 승인 → 고객이 회신을 본다."""
    tid = client.post("/api/tickets", json=INQUIRY).json()["ticket_id"]

    waiting = client.get(f"/api/inquiries/{tid}").json()
    assert waiting["status"] == "IN_PROGRESS"
    assert waiting["subject"] == INQUIRY["subject"] and waiting["body"] == INQUIRY["body"]
    assert waiting["message"] is None
    assert set(waiting) == {
        "ticket_id",
        "subject",
        "body",
        "received_at",
        "status",
        "message",
        "message_language",
        "first_response_target_h",
        "resolution_target_h",
    }  # 초안·근거·점검·담당자는 내보내지 않는다

    held = client.post(
        f"/api/tickets/{tid}/action", json={"action": "edit_approve", "edited_text": "OK."}
    ).json()
    assert held["status"] == "ON_HOLD"  # 수정문은 필수 내용 점검을 통과하지 못한다.
    assert held["approval_text"] == "OK."
    assert client.get(f"/api/inquiries/{tid}").json()["message"] is None
    approved = client.post(
        f"/api/tickets/{tid}/action",
        json={"action": "approve", "acknowledged_failures": True, "reviewer": "reviewer"},
    )
    assert approved.json()["status"] == "APPROVED"
    answered = client.get(f"/api/inquiries/{tid}").json()
    assert (answered["status"], answered["message"], answered["message_language"]) == (
        "ANSWERED",
        "OK.",
        "en",
    )

    client.post(f"/api/tickets/{tid}/resolve")
    assert client.get(f"/api/inquiries/{tid}").json()["status"] == "CLOSED"


def test_info_request_is_shown_and_the_customer_reply_reopens_the_ticket(client) -> None:
    tid = client.post("/api/tickets", json=INQUIRY).json()["ticket_id"]
    # 상담원이 추가정보 요청을 고르면 요청문 초안이 나오고(아직 안 보냄), 승인하면 고객에게 간다
    drafted = client.post(
        f"/api/tickets/{tid}/action",
        json={"action": "info_request", "info_items": ["serial_no"]},
    ).json()
    assert drafted["status"] == "READY_FOR_REVIEW" and drafted["info_request"]
    assert client.get(f"/api/inquiries/{tid}").json()["message"] is None
    client.post(f"/api/tickets/{tid}/action", json={"action": "approve"})

    asked = client.get(f"/api/inquiries/{tid}").json()
    assert asked["status"] == "WAITING_CUSTOMER"
    assert asked["message"] == drafted["info_request"]  # 받은 추가정보 요청

    reply = {"channel": "WEB_FORM", "body": "Serial SN-123.", "thread_ref": "web-1"}
    assert client.post("/api/tickets", json=reply).json()["ticket_id"] == tid
    again = client.get(f"/api/inquiries/{tid}").json()
    assert again["status"] == "IN_PROGRESS" and again["message"] is None
    assert again["body"].endswith("Serial SN-123.")


def test_rejected_inquiry_is_closed_without_a_message(client) -> None:
    tid = client.post("/api/tickets", json=INQUIRY).json()["ticket_id"]
    client.post(f"/api/tickets/{tid}/action", json={"action": "reject"})

    closed = client.get(f"/api/inquiries/{tid}").json()
    assert (closed["status"], closed["message"]) == ("CLOSED", None)


def test_unknown_inquiry_is_404(client) -> None:
    assert client.get("/api/inquiries/T-NOPE").status_code == 404


def test_staff_ticket_includes_the_original_inquiry(client) -> None:
    ticket = client.post("/api/tickets", json=INQUIRY).json()

    assert ticket["inquiry"]["subject"] == INQUIRY["subject"]
    assert ticket["inquiry"]["channel"] == "WEB_FORM"


@pytest.mark.parametrize(
    ("subject", "body", "language"),
    [
        ("S100 E.OC 트립", "S100 인버터가 가속할 때 E.OC 가 떠요", "ko"),
        ("Variador S100", "Mi variador S100 se dispara con E.OC al acelerar", "es"),
        ("S100", "E.OC", "en"),
    ],
)
def test_web_form_without_language_gets_the_detected_language(client, subject, body, language):
    """화면은 language 를 보내지 않는다. 비우면 회신이 영어로 나가므로 접수 때 감지한다."""
    sent = {"channel": "WEB_FORM", "subject": subject, "body": body, "category": "DEFECT"}

    ticket = client.post("/api/tickets", json=sent).json()

    assert ticket["inquiry"]["language"] == language


def test_given_language_is_kept(client) -> None:
    ticket = client.post("/api/tickets", json={**INQUIRY, "language": "de"}).json()

    assert ticket["inquiry"]["language"] == "de"


def test_customer_submits_and_replies_without_seeing_internal_fields(client) -> None:
    """고객 도메인은 /api/tickets 를 막으므로 문의·회신은 /api/inquiries 로 보낸다 (CSA-46)."""
    created = client.post("/api/inquiries", json=INQUIRY)

    assert created.status_code == 201
    body = created.json()
    assert set(body) == {
        "ticket_id",
        "subject",
        "body",
        "received_at",
        "status",
        "message",
        "message_language",
        "first_response_target_h",
        "resolution_target_h",
    }  # AI 초안·근거·점검·담당자는 응답에도 없다
    tid = body["ticket_id"]
    client.post(f"/api/tickets/{tid}/action", json={"action": "info_request"})
    client.post(f"/api/tickets/{tid}/action", json={"action": "approve"})

    reply = {"channel": "WEB_FORM", "body": "Serial SN-1.", "thread_ref": INQUIRY["thread_ref"]}
    again = client.post("/api/inquiries", json=reply).json()
    assert again["ticket_id"] == tid  # 같은 문의로 이어진다


def test_customer_sees_expected_response_times(client) -> None:
    """접수 화면의 예상 소요시간: 규칙이 정한 SLA 목표 시간을 고객 응답에 싣는다."""
    sent = client.post("/api/inquiries", json=INQUIRY).json()
    assert sent["first_response_target_h"] > 0
    assert sent["resolution_target_h"] >= sent["first_response_target_h"]


PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64


def test_customer_uploads_photos_and_sees_them_again(client) -> None:
    tid = client.post("/api/inquiries", json=INQUIRY).json()["ticket_id"]
    up = client.post(
        f"/api/inquiries/{tid}/attachments",
        params={"name": "현장 사진.png"},
        content=PNG,
        headers={"Content-Type": "image/png"},
    )
    assert up.status_code == 201
    meta = up.json()
    assert (meta["name"], meta["content_type"]) == ("현장 사진.png", "image/png")
    assert meta["size"] == len(PNG)

    listed = client.get(f"/api/inquiries/{tid}/attachments").json()
    assert [a["attachment_id"] for a in listed] == [meta["attachment_id"]]

    got = client.get(f"/api/inquiries/{tid}/attachments/{meta['attachment_id']}")
    assert got.status_code == 200 and got.content == PNG
    assert got.headers["content-type"] == "image/png"
    assert got.headers["content-disposition"].startswith("inline")
    assert got.headers["x-content-type-options"] == "nosniff"


def test_scriptable_files_are_downloaded_not_shown(client) -> None:
    """SVG·HTML 은 스크립트를 품을 수 있어 화면 안에서 열지 않는다."""
    tid = client.post("/api/inquiries", json=INQUIRY).json()["ticket_id"]
    svg = b"<svg xmlns='http://www.w3.org/2000/svg'><script>alert(1)</script></svg>"
    aid = client.post(
        f"/api/inquiries/{tid}/attachments",
        params={"name": "../../etc/x.svg"},
        content=svg,
        headers={"Content-Type": "image/svg+xml"},
    ).json()["attachment_id"]
    got = client.get(f"/api/inquiries/{tid}/attachments/{aid}")
    assert got.headers["content-type"] == "application/octet-stream"
    assert got.headers["content-disposition"].startswith("attachment")
    assert client.get(f"/api/inquiries/{tid}/attachments").json()[0]["name"] == "x.svg"


def test_attachment_upload_limits(client, monkeypatch) -> None:
    """없는 문의 · 잘못된 id · 빈 파일 · 크기 · 개수 제한."""
    from cs_agent.api import inquiries
    from cs_agent.services import attachments

    tid = client.post("/api/inquiries", json=INQUIRY).json()["ticket_id"]
    url = f"/api/inquiries/{tid}/attachments"
    unknown = "/api/inquiries/T-000000000000/attachments"
    assert client.post(unknown, params={"name": "a.png"}, content=PNG).status_code == 404
    assert client.get(unknown).status_code == 404
    assert client.get(f"{url}/{'0' * 32}").status_code == 404
    assert client.get(f"{url}/..%2F..%2Fx").status_code == 404
    assert client.post(url, params={"name": "a.png"}, content=b"").status_code == 422

    monkeypatch.setattr(inquiries, "MAX_BYTES", 10)
    monkeypatch.setattr(attachments, "MAX_BYTES", 10)
    assert client.post(url, params={"name": "a.png"}, content=PNG).status_code == 413

    monkeypatch.setattr(attachments, "MAX_FILES", 1)
    assert client.post(url, params={"name": "a.png"}, content=b"12345").status_code == 201
    assert client.post(url, params={"name": "b.png"}, content=b"12345").status_code == 422

    # 받다가 실패한 업로드(빈 파일 · 너무 큼 · 개수 초과)는 임시 파일을 남기지 않는다
    store = client.app.state.attachments
    assert not list((store.root / tid).glob(".upload-*"))
