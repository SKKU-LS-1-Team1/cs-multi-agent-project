"""Final staff text is checked before sending; an old checkbox cannot approve a new failure."""

from langgraph.types import Command
from stubs import pass_customer_qc

from cs_agent.agents import verification
from cs_agent.agents.drafting import TranslationError
from cs_agent.config import Settings
from cs_agent.domain import Category, TicketStatus
from cs_agent.graph.builder import GraphDeps, build_ticket_graph
from cs_agent.llm.router import LLMRouter
from cs_agent.schemas import CheckResult, Classification, Draft, Evidence, Extraction, InquiryIn

ORIGINAL = "For MCCB-ABS-103c, please refer to the installation guide."


def setup_graph(
    check=None,
    language="en",
    translate=None,
    category=Category.MANUAL,
    secondary=None,
    qc=pass_customer_qc,
):
    checks, translations = [], []

    def recorded_check(draft, category, required, inquiry, lang, evidence, llm):
        checks.append((draft.text, lang, draft.model))
        return check(draft, lang) if check else [CheckResult(name="test", passed=True)]

    def recorded_translate(text, source, target, llm):
        translations.append(text)
        return translate(text) if translate else "Réponse vérifiée."

    graph = build_ticket_graph(
        GraphDeps(
            llm=LLMRouter(Settings(_env_file=None)),
            max_retries=0,
            check_customer_qc=qc,
            classify=lambda *args: Classification(category=category, secondary_category=secondary),
            extract=lambda *args, **kwargs: Extraction(
                product_code="MCCB-ABS-103c",
                product_family="LV_BREAKER",
                language=language,
                provided_info=["product_model", "doc_type", "preferred_language"],
            ),
            first_pass=lambda *args: [],
            finalize_evidence=lambda *args, **kwargs: [],
            write_draft=lambda *args, **kwargs: Draft(
                text=ORIGINAL,
                slots={
                    "product_code": "MCCB-ABS-103c",
                    "documents": "installation guide",
                    "draft_language": "en",
                },
                model="test",
            ),
            verify=recorded_check,
            translate_reply=recorded_translate,
            translate=lambda *args: "문의",
        )
    )
    config = {"configurable": {"thread_id": "approval-check"}}
    graph.invoke(
        {
            "ticket_id": "T-APPROVAL",
            "inquiry": InquiryIn(
                channel="email",
                language=language,
                body="Please send the MCCB-ABS-103c installation manual.",
            ),
        },
        config,
    )

    def act(**review):
        graph.invoke(Command(resume=review), config)
        return graph.get_state(config).values

    return graph, config, act, checks, translations


def test_unchanged_success_reuses_check_without_additional_call():
    graph, config, act, checks, _ = setup_graph()
    result = act(action="approve")
    assert result["status"] == TicketStatus.APPROVED
    assert result["final_reply"] == ORIGINAL
    assert len(checks) == 1


def test_edit_is_verified_exactly_and_failure_preserved_without_send_or_rewrite():
    def checker(draft, language):
        return [
            CheckResult(name="values", passed="98765" not in draft.text, reason="Invented voltage")
        ]

    graph, config, act, checks, translations = setup_graph(checker, language="fr")
    edited = "Use 98765 V for the installation."
    result = act(action="edit_approve", edited_text=edited, reviewer="Staff")
    assert result["status"] == TicketStatus.ON_HOLD
    assert result["approval_text"] == edited
    assert result["draft"].text == ORIGINAL
    assert result["approved_reply"] is None and result["final_reply"] is None
    assert result["approval_error"] and result["checks"][0].passed is False
    assert checks[-1] == (edited, "en", "staff_review")
    assert translations == []
    assert graph.get_state(config).next == ("review",)
    corrected = "For MCCB-ABS-103c, please consult the installation guide."
    result = act(action="edit_approve", edited_text=corrected, reviewer="Staff")
    assert result["status"] == TicketStatus.APPROVED
    assert result["approved_reply"] == corrected
    assert translations == [corrected]


def test_old_acknowledgement_does_not_bypass_new_candidate_failure():
    graph, config, act, checks, _ = setup_graph(
        lambda draft, lang: [CheckResult(name="grounding", passed=draft.text == ORIGINAL)]
    )
    edited = "The repair has already been completed."
    failed = act(
        action="edit_approve", edited_text=edited, reviewer="Staff", acknowledged_failures=True
    )
    assert failed["status"] == TicketStatus.ON_HOLD and failed["final_reply"] is None
    assert act(action="approve", reviewer="Staff")["status"] == TicketStatus.ON_HOLD
    approved = act(action="approve", reviewer="Staff", acknowledged_failures=True)
    assert approved["status"] == TicketStatus.APPROVED
    assert approved["approved_reply"] == edited
    assert not approved["checks"][0].passed  # 사람이 확인했지 모델 통과로 바꾸지 않는다.
    assert len(checks) == 2


def test_failed_initial_draft_requires_explicit_acknowledgement():
    graph, config, act, checks, _ = setup_graph(
        lambda draft, lang: [CheckResult(name="grounding", passed=False)]
    )
    assert act(action="approve")["status"] == TicketStatus.ON_HOLD
    assert act(action="approve", acknowledged_failures=True)["status"] == TicketStatus.ON_HOLD
    assert (
        act(action="approve", acknowledged_failures=True, reviewer="Staff")["status"]
        == TicketStatus.APPROVED
    )


def test_changed_evidence_invalidates_previous_failed_text_acknowledgement():
    graph, config, act, checks, _ = setup_graph(
        lambda draft, lang: [CheckResult(name="grounding", passed=False)]
    )
    graph.update_state(
        config, {"evidence": [Evidence(source="docs", doc_id="new", text="New evidence")]}
    )
    assert (
        act(action="approve", reviewer="Staff", acknowledged_failures=True)["status"]
        == TicketStatus.ON_HOLD
    )
    assert len(checks) == 2


def test_translation_retry_reuses_checked_edit_and_preserves_original_feedback():
    translations = []

    def translate(text):
        translations.append(text)
        if len(translations) == 1:
            raise TranslationError("temporary")
        return "Réponse vérifiée."

    graph, config, act, checks, _ = setup_graph(language="fr", translate=translate)
    text = "For MCCB-ABS-103c, please consult the installation guide."
    result = act(
        action="edit_approve", edited_text=text, reviewer="Staff", feedback="Clarified wording"
    )
    assert result["status"] == TicketStatus.ON_HOLD and result["translation_error"]
    result = act(action="approve", reviewer="Staff")
    assert result["status"] == TicketStatus.APPROVED
    assert translations == [text, text]
    assert len(checks) == 2
    assert result["approval_review"]["action"] == "edit_approve"
    assert result["approval_review"]["feedback"] == "Clarified wording"
    assert result["approval_review"]["edited_text"] == text


def test_direct_customer_language_edit_is_checked_in_customer_language_and_not_translated():
    graph, config, act, checks, translations = setup_graph(language="fr")
    text = "Veuillez consulter le guide d'installation pour votre appareil MCCB-ABS-103c."
    result = act(action="edit_approve", edited_text=text, reviewer="Staff")
    assert result["status"] == TicketStatus.APPROVED
    assert checks[-1][1] == "fr"
    assert result["final_reply"] == text and translations == []


def test_real_verifier_rejects_staff_invented_voltage():
    def real_check(candidate, lang):
        return verification.verify(
            candidate,
            Category.MANUAL,
            ("product_code", "documents"),
            "Please send the installation manual.",
            lang,
            [],
            LLMRouter(Settings(_env_file=None)),
        )

    _, _, act, _, _ = setup_graph(real_check)
    result = act(
        action="edit_approve",
        reviewer="Staff",
        edited_text="For MCCB-ABS-103c, use 98765 V on the terminals.",
    )
    assert result["status"] == TicketStatus.ON_HOLD
    assert any(c.name in {"specs", "values"} and not c.passed for c in result["checks"])


def test_rewrite_resets_failed_candidate_and_approval_metadata():
    graph, config, act, checks, _ = setup_graph(
        lambda candidate, lang: [CheckResult(name="test", passed=candidate.text == ORIGINAL)]
    )
    act(action="edit_approve", edited_text="An unsupported edit", reviewer="Staff")
    result = act(action="rewrite")
    assert result["approval_text"] is None
    assert result["approval_error"] is None
    assert result["approval_review"] is None
    assert result["draft"].text == ORIGINAL


def test_missing_original_draft_can_hold_then_manually_acknowledge_saved_candidate():
    graph, config, act, _, _ = setup_graph(
        lambda candidate, lang: [CheckResult(name="slots", passed=False)]
    )
    graph.update_state(config, {"draft": None})
    text = "Manual staff response requiring review."
    held = act(action="edit_approve", edited_text=text, reviewer="Staff")
    assert held["status"] == TicketStatus.ON_HOLD and held["approval_text"] == text
    approved = act(action="approve", reviewer="Staff", acknowledged_failures=True)
    assert approved["status"] == TicketStatus.APPROVED
    assert approved["approved_reply"] == text


def test_final_citations_come_from_edited_body_not_original_ai_draft():
    graph, config, act, _, _ = setup_graph()
    evidence = [Evidence(source="docs", doc_id="DOC", section="one", text="Guidance.")]
    graph.update_state(config, {"evidence": evidence})
    text = "Please consult this document. [DOC#one]"
    approved = act(action="edit_approve", edited_text=text, reviewer="Staff")
    assert approved["approval_cited"] == ["DOC#one"]
    assert approved["draft"].cited == []
    assert approved["final_reply"] == "Please consult this document."


def test_clean_unchanged_draft_keeps_reference_metadata_on_approval():
    graph, config, act, _, _ = setup_graph()
    original = graph.get_state(config).values["draft"]
    graph.update_state(
        config,
        {
            "draft": original.model_copy(update={"cited": ["DOC#one"]}),
            "evidence": [Evidence(source="docs", doc_id="DOC", section="one", text="Guidance.")],
        },
    )
    approved = act(action="approve")
    assert approved["status"] == TicketStatus.APPROVED
    assert approved["final_reply"] == ORIGINAL
    assert approved["approval_cited"] == ["DOC#one"]


def test_old_inline_draft_approval_cleans_text_without_losing_sources():
    graph, config, act, _, _ = setup_graph()
    original = graph.get_state(config).values["draft"]
    graph.update_state(
        config,
        {
            "draft": original.model_copy(
                update={"text": "Please consult this document [DOC#one].", "cited": ["DOC#one"]}
            ),
            "evidence": [Evidence(source="docs", doc_id="DOC", section="one", text="Guidance.")],
        },
    )
    approved = act(action="approve")
    assert approved["status"] == TicketStatus.APPROVED
    assert approved["approved_reply"] == approved["final_reply"] == "Please consult this document."
    assert approved["approval_cited"] == ["DOC#one"]
    assert approved["processing_history"][-1]["edited"] is False


def test_transient_final_verification_failure_can_retry_same_text_without_override():
    attempts = []

    def fail_once(candidate, lang):
        if candidate.text != ORIGINAL:
            attempts.append(candidate.text)
            if len(attempts) == 1:
                raise TimeoutError("temporary verifier outage")
        return [CheckResult(name="grounding", passed=True)]

    _, _, act, checks, _ = setup_graph(fail_once)
    text = "For MCCB-ABS-103c, please consult the guide."
    held = act(action="edit_approve", edited_text=text, reviewer="Staff")
    assert held["status"] == TicketStatus.ON_HOLD
    assert held["checks"][0].name == "approval_verification_error"
    done = act(action="approve", reviewer="Staff")
    assert done["status"] == TicketStatus.APPROVED
    assert attempts == [text, text]
    assert len(checks) == 3


def test_same_edit_retry_retains_original_feedback_reason_and_note():
    _, _, act, _, _ = setup_graph(
        lambda candidate, lang: [CheckResult(name="grounding", passed=candidate.text == ORIGINAL)]
    )
    text = "A corrected staff response pending human confirmation."
    held = act(
        action="edit_approve",
        edited_text=text,
        reviewer="Staff",
        feedback="Original factual correction",
        feedback_reason="FACT_ERROR",
    )
    assert held["status"] == TicketStatus.ON_HOLD
    done = act(
        action="edit_approve", edited_text=text, reviewer="Staff", acknowledged_failures=True
    )
    assert done["status"] == TicketStatus.APPROVED
    assert done["approval_review"]["feedback"] == "Original factual correction"
    assert done["approval_review"]["feedback_reason"] == "FACT_ERROR"
