import pytest
from unittest.mock import Mock, patch
from typing import Generator

from backend.app.services.llm_service import (
    llm_service,
    count_answer_words,
    is_length_rule_exempt,
    MIN_WORDS,
    MAX_WORDS,
    TARGET_MIN,
    TARGET_MAX,
)


def _generate_word_block(n_words: int, prefix: str = "word") -> str:
    """Helper to generate an exact number of whitespace-separated words."""
    return " ".join(f"{prefix}{i}" for i in range(n_words))


# ==============================================================================
# TEST 1: 400-WORD EXPANSION, 2000-WORD CONDENSATION, IN-RANGE NO RETRY
# ==============================================================================
def test_expansion_and_condensation_retries():
    """
    1. A 400-word reply triggers exactly one expansion retry.
    2. A 2,000-word reply triggers exactly one condensation retry.
    3. A reply in range (e.g. 1,000 words) triggers no retry.
    """
    query = "What is SAP FI-CA and how does it integrate with Convergent Invoicing?"
    dummy_evidence = [{
        "source_type": "knowledge_base",
        "document_name": "AC240",
        "page_number": 1,
        "section": "Overview",
        "chunk_text": "FI-CA subledger handles mass open item accounting."
    }]

    # Case A: 400 words triggers exactly one expansion
    call_log = []
    def mock_expansion_provider(prompt, system_prompt):
        call_log.append(prompt)
        if len(call_log) == 1:
            return _generate_word_block(400)
        return _generate_word_block(1000)

    saved_call = llm_service._call_groq
    saved_key = llm_service.groq_api_key
    try:
        llm_service.groq_api_key = "mock-key"
        llm_service._call_groq = mock_expansion_provider

        result = llm_service.generate_answer(query, dummy_evidence, source_type="knowledge_base")
        assert len(call_log) == 2, f"Expected exactly 2 provider calls (1 initial + 1 expansion), got {len(call_log)}"
        assert "EXPAND THE ANSWER" in call_log[1]
        assert count_answer_words(result) == 1000

        # Case B: 2,000 words triggers exactly one condensation
        call_log.clear()
        def mock_condensation_provider(prompt, system_prompt):
            call_log.append(prompt)
            if len(call_log) == 1:
                return _generate_word_block(2000)
            return _generate_word_block(1100)

        llm_service._call_groq = mock_condensation_provider
        result_cond = llm_service.generate_answer(query, dummy_evidence, source_type="knowledge_base")
        assert len(call_log) == 2, f"Expected exactly 2 provider calls (1 initial + 1 condensation), got {len(call_log)}"
        assert "CONDENSE THE ANSWER" in call_log[1]
        assert count_answer_words(result_cond) == 1100

        # Case C: 1,000 words (in range) triggers no retry
        call_log.clear()
        def mock_in_range_provider(prompt, system_prompt):
            call_log.append(prompt)
            return _generate_word_block(1000)

        llm_service._call_groq = mock_in_range_provider
        result_ok = llm_service.generate_answer(query, dummy_evidence, source_type="knowledge_base")
        assert len(call_log) == 1, f"Expected exactly 1 call (no retry for in-range answer), got {len(call_log)}"
        assert count_answer_words(result_ok) == 1000

    finally:
        llm_service._call_groq = saved_call
        llm_service.groq_api_key = saved_key


# ==============================================================================
# TEST 2: ONE RETRY MAX (NO LOOPS IF STILL OUT OF RANGE)
# ==============================================================================
def test_no_loops_when_retry_still_out_of_range():
    """
    After one retry, the result is returned even if still out of range (no endless loops).
    """
    query = "How do I configure provider contracts in SOM?"
    dummy_evidence = [{
        "source_type": "knowledge_base",
        "document_name": "SOM_Guide",
        "page_number": 5,
        "section": "Config",
        "chunk_text": "Provider contracts are configured in SPRO under SOM."
    }]

    call_log = []
    def mock_stubborn_provider(prompt, system_prompt):
        call_log.append(prompt)
        # Even after expansion, still returns only 500 words (< 700)
        return _generate_word_block(500)

    saved_call = llm_service._call_groq
    saved_key = llm_service.groq_api_key
    try:
        llm_service.groq_api_key = "mock-key"
        llm_service._call_groq = mock_stubborn_provider

        result = llm_service.generate_answer(query, dummy_evidence, source_type="knowledge_base")
        assert len(call_log) == 2, f"Expected max 1 retry (total 2 calls), but got {len(call_log)}"
        assert count_answer_words(result) == 500
    finally:
        llm_service._call_groq = saved_call
        llm_service.groq_api_key = saved_key


# ==============================================================================
# TEST 3: WORD COUNTING EXCLUDES FENCED CODE BLOCKS AND SOURCES LIST
# ==============================================================================
def test_word_counting_excludes_code_blocks_and_sources():
    """
    Word counting precisely counts whitespace-separated words in the body,
    excluding fenced code blocks (text diagrams) and trailing sources lists.
    """
    body_words = 850
    code_words = 150
    sources_words = 60

    body = _generate_word_block(body_words, prefix="body")
    code_block = "```text\n" + _generate_word_block(code_words, prefix="code") + "\n```"
    sources_section = "\n\n### Sources\n" + _generate_word_block(sources_words, prefix="source")

    full_text = f"{body}\n\n{code_block}{sources_section}"

    counted = count_answer_words(full_text)
    assert counted == body_words, f"Expected {body_words} body words, but counted {counted}"

    # Also test bolded **Sources:** variant
    sources_bold = "\n\n**Sources:**\n" + _generate_word_block(sources_words, prefix="source")
    full_bold = f"{body}\n\n{code_block}{sources_bold}"
    assert count_answer_words(full_bold) == body_words


# ==============================================================================
# TEST 4: COUNTER OR RETRY FAILURE FAILS OPEN
# ==============================================================================
def test_fail_open_on_counter_or_retry_error():
    """
    If word counting or the retry call raises an error, the original answer
    is safely returned without raising an exception to the caller.
    """
    query = "Explain CI mass billing execution."
    dummy_evidence = [{
        "source_type": "knowledge_base",
        "document_name": "CI_Billing",
        "page_number": 20,
        "section": "Mass Run",
        "chunk_text": "FKKBIX_BILL_M executes mass billing runs for billable items."
    }]

    original_answer = _generate_word_block(300, prefix="initial")

    saved_call = llm_service._call_groq
    saved_key = llm_service.groq_api_key
    try:
        llm_service.groq_api_key = "mock-key"

        call_count = 0
        def mock_exploding_retry(prompt, system_prompt):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return original_answer
            raise RuntimeError("Cloud provider network timeout during expansion retry")

        llm_service._call_groq = mock_exploding_retry

        # Must not raise RuntimeError; must fail open and return original_answer
        res = llm_service.generate_answer(query, dummy_evidence, source_type="knowledge_base")
        assert res == original_answer
    finally:
        llm_service._call_groq = saved_call
        llm_service.groq_api_key = saved_key


# ==============================================================================
# TEST 5: STREAMING MODE DOES NOT RETRY OR BUFFER
# ==============================================================================
def test_streaming_mode_does_not_retry_or_buffer():
    """
    Streaming mode streams tokens immediately without buffering or executing retries.
    """
    query = "Describe Convergent Charging architecture."
    dummy_evidence = [{
        "source_type": "knowledge_base",
        "document_name": "CC_Overview",
        "page_number": 2,
        "section": "Architecture",
        "chunk_text": "CC provides real-time rating and charging engine."
    }]

    tokens = ["Convergent ", "Charging ", "rates ", "events ", "in ", "real-time."]
    stream_call_count = 0

    def mock_stream_provider(prompt, system_prompt):
        nonlocal stream_call_count
        stream_call_count += 1
        for tok in tokens:
            yield tok

    saved_stream = llm_service._stream_groq
    saved_key = llm_service.groq_api_key
    try:
        llm_service.groq_api_key = "mock-key"
        llm_service._stream_groq = mock_stream_provider

        stream_gen = llm_service.stream_answer(query, dummy_evidence, source_type="knowledge_base")

        received_tokens = []
        for token in stream_gen:
            received_tokens.append(token)

        assert received_tokens == tokens
        # Verify provider was invoked exactly once (no retry on streaming)
        assert stream_call_count == 1
    finally:
        llm_service._stream_groq = saved_stream
        llm_service.groq_api_key = saved_key


# ==============================================================================
# TEST 6: PROMPT CONTAINS LENGTH RULE, BRIM REQUIREMENTS, NO-INVENTED IDENTIFIERS
# ==============================================================================
def test_prompt_contains_mandatory_length_and_brim_rules():
    """
    The generated user prompt contains:
    - 700-1,500 word length rule (and 900-1,200 target).
    - BRIM content requirements (process flow, transaction codes, SPRO configuration, troubleshooting).
    - No-invented-identifier rule ("verify in your system", never write "or similar").
    """
    query = "How do I troubleshoot duplicate invoices after a subscription order change?"
    dummy_evidence = [{
        "source_type": "knowledge_base",
        "document_name": "CI_Invoicing",
        "page_number": 15,
        "section": "Troubleshooting",
        "chunk_text": "Verify billing orders in FKKBIX_BILL_M."
    }]

    captured_prompt = None
    def mock_inspector(prompt, system_prompt):
        nonlocal captured_prompt
        captured_prompt = prompt
        return _generate_word_block(1000)

    saved_call = llm_service._call_groq
    saved_key = llm_service.groq_api_key
    try:
        llm_service.groq_api_key = "mock-key"
        llm_service._call_groq = mock_inspector

        llm_service.generate_answer(query, dummy_evidence, source_type="knowledge_base")

        assert captured_prompt is not None
        # 1. Length rule
        assert "MANDATORY LENGTH AND DEPTH REQUIREMENTS" in captured_prompt
        assert f"MORE than {MIN_WORDS} words and FEWER than {MAX_WORDS} words" in captured_prompt
        assert f"target roughly {TARGET_MIN} to {TARGET_MAX} words" in captured_prompt
        assert "excluding fenced code blocks" in captured_prompt
        assert "trailing sources/citations list" in captured_prompt

        # 2. BRIM requirements
        assert "SAP BRIM questions" in captured_prompt
        assert "Process flow" in captured_prompt
        assert "Transaction codes" in captured_prompt
        assert "Configuration details and SPRO paths" in captured_prompt
        assert "Troubleshooting steps" in captured_prompt

        # 3. No invented identifiers
        assert "NO-INVENTED-IDENTIFIERS RULE" in captured_prompt
        assert "verify in your system" in captured_prompt
        assert "Never write 'or similar' beside an identifier" in captured_prompt
    finally:
        llm_service._call_groq = saved_call
        llm_service.groq_api_key = saved_key


# ==============================================================================
# TEST 7: EXCEPTIONS (GREETING, CLARIFYING QUESTION, EXPLICIT ONE-LINE OVERRIDE)
# ==============================================================================
def test_exceptions_bypass_length_rule():
    """
    Greetings, clarifying questions, and explicit length overrides ('one line')
    bypass the 700-1,500 word rule without triggering expansion retries.
    """
    dummy_evidence = [{
        "source_type": "knowledge_base",
        "document_name": "Manual",
        "page_number": 1,
        "section": "Intro",
        "chunk_text": "SAP system overview."
    }]

    saved_call = llm_service._call_groq
    saved_key = llm_service.groq_api_key
    try:
        llm_service.groq_api_key = "mock-key"

        # Case A: Greeting bypasses rule
        call_count = 0
        def mock_greeting_provider(prompt, system_prompt):
            nonlocal call_count
            call_count += 1
            return "Hello! How can I assist you with SAP BRIM today?"

        llm_service._call_groq = mock_greeting_provider
        ans_greeting = llm_service.generate_answer("Hi", dummy_evidence, source_type="knowledge_base")
        assert call_count == 1, "Greeting should not trigger expansion retry"
        assert "assist you with SAP BRIM" in ans_greeting

        # Case B: Explicit 'one line' instruction honored without retry
        call_count = 0
        def mock_oneline_provider(prompt, system_prompt):
            nonlocal call_count
            call_count += 1
            return "A billable item (BIT) represents a discrete record of billable usage or charges in Convergent Invoicing."

        llm_service._call_groq = mock_oneline_provider
        ans_oneline = llm_service.generate_answer(
            "Answer in one line: what is a billable item?",
            dummy_evidence,
            source_type="knowledge_base"
        )
        assert call_count == 1, "Explicit 'one line' query should not trigger expansion retry"
        assert count_answer_words(ans_oneline) < 50

        # Case C: Clarifying question response bypasses rule
        call_count = 0
        def mock_clarifying_provider(prompt, system_prompt):
            nonlocal call_count
            call_count += 1
            return "Could you please clarify which SAP release (S/4HANA 2023 or ECC 6.0) you are running?"

        llm_service._call_groq = mock_clarifying_provider
        ans_clarify = llm_service.generate_answer(
            "How do I fix error 102?",
            dummy_evidence,
            source_type="knowledge_base"
        )
        assert call_count == 1, "Clarifying question should not trigger expansion retry"
        assert "Could you please clarify" in ans_clarify

    finally:
        llm_service._call_groq = saved_call
        llm_service.groq_api_key = saved_key
