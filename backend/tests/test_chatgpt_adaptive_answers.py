import os
import re
import tempfile
import uuid
import pytest
from unittest.mock import Mock
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.database import Base
from backend.app.models.user import User
from backend.app.models.chat import Chat
from backend.app.models.message import Message
from backend.app.models.memory import ConversationMemory
from backend.app.services.answer_planner import answer_planner
from backend.app.services.llm_service import llm_service, SYSTEM_PROMPT
from backend.app.services.memory_service import memory_service
from backend.app.services.embedding_service import embedding_service
from backend.app.security.auth import hash_password


# ==============================================================================
# FIXTURES
# ==============================================================================

@pytest.fixture(autouse=True)
def deterministic_embedder(monkeypatch):
    monkeypatch.setattr(embedding_service, "embed_text", embedding_service._fallback_embed)
    monkeypatch.setattr(embedding_service, "embed_batch", lambda texts: [embedding_service._fallback_embed(t) for t in texts])


@pytest.fixture
def temp_db_file():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    try:
        os.remove(path)
    except Exception:
        pass


@pytest.fixture
def db_session(temp_db_file):
    engine = create_engine(f"sqlite:///{temp_db_file}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


# ==============================================================================
# TEST 1: SIMPLE DEFINITION QUESTION (NO FORCED HEADINGS / NO DIAGRAM / CONCISE)
# ==============================================================================
def test_1_simple_definition_no_forced_step_or_diagram_template():
    """
    Acceptance criteria:
    'What is FI-CA?' gets a short natural answer with no diagram or forced structure.
    Verify that the system section is present and no forced template is applied.
    """
    query = "What is FI-CA?"
    plan = answer_planner.plan_answer(query)
    hint = answer_planner.detect_format_hint(query)

    assert hint["is_simple_question"] is True
    assert hint["wants_steps"] is False
    assert hint["wants_diagram"] is False

    format_guidance, structure_guidance, word_target = llm_service._build_adaptive_format_section(
        query=query,
        plan=plan
    )

    # 1. Structure guidance should be suppressed so rigid multi-section headers are NOT forced
    assert structure_guidance == ""
    # 2. Word target is concise
    assert word_target <= 200
    # 3. Format guidance explicitly advises conversational prose without forced headings or diagrams
    assert "Normal Simple Question" in format_guidance
    assert "Do NOT use forced headings, bullet lists, or diagrams" in format_guidance
    assert "A one-line question gets a short answer" in format_guidance

    # 4. In generate_answer, verify the assembled prompt reaching the provider
    captured_prompts = []
    def mock_provider(user_prompt, system_prompt):
        captured_prompts.append((user_prompt, system_prompt))
        return "FI-CA (Contract Accounts Receivable and Payable) is the subledger in SAP designed for high-volume customer accounting."

    dummy_evidence = [{
        "source_type": "knowledge_base",
        "document_name": "AC240 FI-CA Manual",
        "page_number": 12,
        "section": "Overview",
        "chunk_text": "FI-CA manages mass billing and payments for millions of accounts."
    }]

    saved_call = llm_service._call_groq
    llm_service._call_groq = mock_provider
    try:
        llm_service.groq_api_key = "dummy-key"
        ans = llm_service.generate_answer(query, dummy_evidence, source_type="knowledge_base")
        assert len(captured_prompts) == 1
        user_prompt, system_prompt = captured_prompts[0]

        # Check that system prompt has ChatGPT-style adaptive instructions
        assert "CHATGPT-STYLE ADAPTIVE ANSWERS" in system_prompt
        assert "MERMAID DIAGRAM RULES" in system_prompt

        # Check user prompt
        assert "Normal Simple Question" in user_prompt
        assert "Do NOT use forced headings, bullet lists, or diagrams" in user_prompt
        assert "STRUCTURE REQUIREMENT (Conceptual Architecture):" not in user_prompt
        assert "FI-CA" in ans
    finally:
        llm_service._call_groq = saved_call


# ==============================================================================
# TEST 2: STEP-BY-STEP TROUBLESHOOTING PRODUCES NUMBERED STEPS GUIDANCE
# ==============================================================================
def test_2_step_by_step_troubleshooting_produces_numbered_steps_guidance():
    """
    Acceptance criteria:
    'How do I troubleshoot duplicate invoices after a subscription order change? Give steps.'
    results in numbered steps guidance (what, where, expected result, verification note).
    """
    query = "How do I troubleshoot duplicate invoices after a subscription order change? Give steps."
    plan = answer_planner.plan_answer(query)
    hint = answer_planner.detect_format_hint(query)

    assert hint["wants_steps"] is True

    format_guidance, structure_guidance, word_target = llm_service._build_adaptive_format_section(
        query=query,
        plan=plan
    )

    assert "FORMAT REQUIREMENT (User requested step-by-step)" in format_guidance
    assert "numbered step-by-step guide" in format_guidance
    assert "what to check or do, where, and what result to expect" in format_guidance
    assert "short verification or 'if it still fails' note at the end" in format_guidance

    captured_prompts = []
    def mock_provider(user_prompt, system_prompt):
        captured_prompts.append((user_prompt, system_prompt))
        return "1. Check the subscription order in CRMD_ORDER..."

    saved_call = llm_service._call_groq
    llm_service._call_groq = mock_provider
    try:
        llm_service.groq_api_key = "dummy-key"
        dummy_evidence = [{
            "source_type": "knowledge_base",
            "document_name": "CI Invoicing Manual",
            "page_number": 45,
            "section": "Troubleshooting",
            "chunk_text": "Check duplicate BITs in FKKBIX_BITCAT and billing orders in FKKBIX_BILL_M."
        }]
        ans = llm_service.generate_answer(query, dummy_evidence, source_type="knowledge_base")
        assert len(captured_prompts) >= 1
        user_prompt, system_prompt = captured_prompts[0]

        assert "FORMAT REQUIREMENT (User requested step-by-step)" in user_prompt
        assert "what to check or do, where, and what result to expect" in user_prompt
    finally:
        llm_service._call_groq = saved_call


# ==============================================================================
# TEST 3: FLOW / DIAGRAM REQUEST PRODUCES DIAGRAM GUIDANCE (EXPLANATION DOES NOT)
# ==============================================================================
def test_3_flow_diagram_request_produces_diagram_guidance():
    """
    Acceptance criteria:
    'Show me the flow / structure / diagram' results in diagram guidance reaching the model.
    A plain explanation question does NOT include diagram guidance.
    """
    diagram_query = "Show me the flow and structure of subscription order replication to CC"
    plain_query = "Explain how subscription orders replicate to CC"

    hint_diag = answer_planner.detect_format_hint(diagram_query)
    hint_plain = answer_planner.detect_format_hint(plain_query)

    assert hint_diag["wants_diagram"] is True
    assert hint_plain["wants_diagram"] is False

    format_diag, _, _ = llm_service._build_adaptive_format_section(
        query=diagram_query,
        plan=answer_planner.plan_answer(diagram_query)
    )
    format_plain, _, _ = llm_service._build_adaptive_format_section(
        query=plain_query,
        plan=answer_planner.plan_answer(plain_query)
    )

    # Diagram request has explicit flow diagram requirement with formatting rules
    assert "FORMAT REQUIREMENT (User requested diagram / architecture / workflow / sequence)" in format_diag
    assert "Mermaid diagram" in format_diag
    assert "Mermaid Diagram Syntax Rules" in format_diag

    # Plain explanation does NOT demand a diagram
    assert "FORMAT REQUIREMENT (User requested diagram / architecture / workflow / sequence)" not in format_plain


# ==============================================================================
# TEST 4: FOLLOW-UP CONTINUES NUMBERING AND FORMAT NATURAL CONTINUATION
# ==============================================================================
def test_4_followup_next_step_continues_numbering_and_format():
    """
    Acceptance criteria:
    'What is the next step?' in a continued chat continues the earlier numbering and format
    without restarting from scratch or repeating the summary.
    """
    chat_history_with_steps = (
        "User: How do I troubleshoot stuck billable items? Give steps.\n"
        "Assistant: Here is the initial troubleshooting guide:\n"
        "1. Check the BIT status in transaction FKKBIX_BITCAT.\n"
        "2. Review the application log in SLG1 under object FKKBIX.\n"
        "3. Verify whether rating in CC generated exceptions."
    )

    followup_query = "What is the next step?"
    hint = answer_planner.detect_format_hint(
        query=followup_query,
        chat_history_context=chat_history_with_steps
    )

    assert hint["is_followup_next_step"] is True
    assert "Step 4" in hint["followup_instructions"]
    assert "Do not restart from Step 1" in hint["followup_instructions"]

    format_guidance, _, _ = llm_service._build_adaptive_format_section(
        query=followup_query,
        plan=answer_planner.plan_answer(followup_query, is_follow_up=True),
        chat_history_context=chat_history_with_steps
    )

    assert "FORMAT REQUIREMENT (Follow-up Continuity)" in format_guidance
    assert "Step 4" in format_guidance
    assert "Do not restart from Step 1" in format_guidance


# ==============================================================================
# TEST 5: FORMAT OVERRIDES & USER-SCOPED STANDING PREFERENCES
# ==============================================================================
def test_5_format_overrides_and_standing_preferences(db_session):
    """
    Acceptance criteria:
    - Single-turn 'no diagram' or 'short answer' instruction is honored for that answer.
    - A standing preference ('always', 'from now on') is stored per user and not visible to others.
    """
    # Part A: Single-turn overrides
    no_diag_query = "Explain CI billing process, no diagram please"
    hint_no_diag = answer_planner.detect_format_hint(no_diag_query)
    assert hint_no_diag["wants_no_diagram"] is True
    format_no_diag, _, _ = llm_service._build_adaptive_format_section(
        query=no_diag_query,
        plan=answer_planner.plan_answer(no_diag_query)
    )
    assert "User specified NO diagram" in format_no_diag
    assert "Do NOT include any flow chart, diagram" in format_no_diag

    short_query = "What is CC rating? Short answer"
    hint_short = answer_planner.detect_format_hint(short_query)
    assert hint_short["wants_short"] is True
    format_short, _, word_tgt = llm_service._build_adaptive_format_section(
        query=short_query,
        plan=answer_planner.plan_answer(short_query)
    )
    assert "User requested short answer" in format_short
    assert word_tgt <= 120

    # Part B: Standing preferences stored per user in memory service
    user1 = User(id="user-pref-1", email="pref1@clyptus.ai", name="User 1", password_hash=hash_password("Pass123!"), role="consultant", memory_enabled=True)
    user2 = User(id="user-pref-2", email="pref2@clyptus.ai", name="User 2", password_hash=hash_password("Pass123!"), role="consultant", memory_enabled=True)
    db_session.add_all([user1, user2])
    db_session.commit()

    chat1 = Chat(id="chat-pref-1", user_id=user1.id, title="User1 Chat")
    db_session.add(chat1)
    db_session.commit()

    # User 1 states a standing preference:
    memory_service.extract_and_persist(
        db=db_session,
        user_id=user1.id,
        chat_id=chat1.id,
        user_message="From now on, always give short answers without diagrams",
        assistant_message="Understood, I will always provide short answers without diagrams from now on."
    )

    # Verify memory is stored for user1
    u1_mems = db_session.query(ConversationMemory).filter(
        ConversationMemory.user_id == user1.id,
        ConversationMemory.status == "active"
    ).all()
    assert len(u1_mems) >= 1
    assert any("short answer" in m.summary.lower() for m in u1_mems)

    # Verify user 2 has NO memories (strict isolation)
    u2_mems = db_session.query(ConversationMemory).filter(
        ConversationMemory.user_id == user2.id,
        ConversationMemory.status == "active"
    ).all()
    assert len(u2_mems) == 0

    # When user 1 queries in a brand new chat, retrieved memory contains the preference
    retrieved = memory_service.retrieve_relevant_memories(
        db=db_session,
        user_id=user1.id,
        query="Explain BIT aggregation in CI"
    )
    assert retrieved["previous_context_used"] is True
    formatted_context = retrieved["formatted_context"]

    # Adaptive format builder detects standing preference from memory context
    hint_standing = answer_planner.detect_format_hint(
        query="Explain BIT aggregation in CI",
        memory_context=formatted_context
    )
    assert hint_standing["standing_preference"] in ("short answer", "no diagram")

    # When user 1 issues an update/correction to change preference:
    memory_service.extract_and_persist(
        db=db_session,
        user_id=user1.id,
        chat_id=chat1.id,
        user_message="Actually, from now on explain in detail with tables",
        assistant_message="Got it! I will now provide detailed explanations with tables."
    )
    # The older short answer preference should be superseded
    superseded = db_session.query(ConversationMemory).filter(
        ConversationMemory.user_id == user1.id,
        ConversationMemory.status == "superseded"
    ).all()
    assert len(superseded) >= 1


# ==============================================================================
# TEST 6: HINT OR ROUTER FAILURE DOES NOT BREAK NORMAL ANSWERING
# ==============================================================================
def test_6_hint_or_router_failure_does_not_break_answering(monkeypatch):
    """
    Acceptance criteria:
    Any hint or router failure does not break normal answering.
    On error, continue without it.
    """
    def broken_detect_hint(*args, **kwargs):
        raise RuntimeError("Unexpected simulated failure in format router")

    monkeypatch.setattr(answer_planner, "detect_format_hint", broken_detect_hint)

    captured_prompts = []
    def mock_provider(user_prompt, system_prompt):
        captured_prompts.append((user_prompt, system_prompt))
        return "Standard technical answer generated safely despite router failure."

    monkeypatch.setattr(llm_service, "_call_groq", mock_provider)
    llm_service.groq_api_key = "dummy-key"

    dummy_evidence = [{
        "source_type": "knowledge_base",
        "document_name": "AC240",
        "page_number": 1,
        "section": "Sec 1",
        "chunk_text": "Sample evidence passage."
    }]

    # generate_answer should succeed without raising any exception!
    ans = llm_service.generate_answer(
        query="What is transaction FP08?",
        evidence=dummy_evidence,
        source_type="knowledge_base"
    )
    assert "Standard technical answer" in ans
    assert len(captured_prompts) == 1

    # stream_answer should also succeed without raising any exception!
    def mock_stream_provider(user_prompt, system_prompt):
        yield "Streamed token 1 "
        yield "Streamed token 2"

    monkeypatch.setattr(llm_service, "_stream_groq", mock_stream_provider)
    stream_tokens = list(llm_service.stream_answer(
        query="What is transaction FP08?",
        evidence=dummy_evidence,
        source_type="knowledge_base"
    ))
    assert "".join(stream_tokens) == "Streamed token 1 Streamed token 2"
