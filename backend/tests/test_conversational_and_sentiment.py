import pytest
from unittest.mock import patch, MagicMock
from backend.app.services.conversational_service import conversational_service
from backend.app.services.rag_service import rag_service


class TestNaturalGreetingDetection:
    """Verify natural greeting detection, spelling variations, and direct conversational responses."""

    @pytest.mark.parametrize("greeting,expected_key", [
        ("hi", "hi"),
        ("Hi!", "hi"),
        ("HI 👋", "hi"),
        ("hii", "hii"),
        ("Hii! 😊", "hii"),
        ("hiiii", "hii"),
        ("hlo", "hlo"),
        ("Hlo!", "hlo"),
        ("hloo", "hloo"),
        ("hlooo", "hloo"),
        ("hello", "hello"),
        ("Hello!", "hello"),
        ("helloo", "helloo"),
        ("hey", "hey"),
        ("Hey! 😊", "hey"),
        ("good morning", "good_morning"),
        ("Good Morning! ☀️", "good_morning"),
        ("good afternoon", "good_afternoon"),
        ("good evening", "good_evening"),
    ])
    def test_greeting_variations_detected(self, greeting: str, expected_key: str):
        analysis = conversational_service.analyze(greeting)
        assert analysis["intent"] == "greeting"
        assert analysis["is_conversational_only"] is True
        assert analysis["direct_reply"] is not None
        assert len(analysis["direct_reply"]) > 5

    def test_compound_greeting(self):
        """User: 'hii hlo' -> friendly greeting without repeating multiple greetings."""
        analysis = conversational_service.analyze("hii hlo")
        assert analysis["intent"] == "greeting"
        assert analysis["is_conversational_only"] is True
        assert analysis["direct_reply"] is not None
        # Does not repeat double greetings like "Hii Hello"
        assert not analysis["direct_reply"].lower().startswith("hii hello")

    def test_presence_check(self):
        """User: 'are you there?' -> 'Yes, I'm here! What would you like help with?'"""
        analysis = conversational_service.analyze("are you there?")
        assert analysis["intent"] == "help_request"
        assert analysis["is_conversational_only"] is True
        assert "here" in analysis["direct_reply"].lower()

    def test_farewell_and_thanks(self):
        """User: 'thank you', 'bye' -> courteous conversational replies."""
        thanks = conversational_service.analyze("thank you")
        assert thanks["intent"] == "thanks"
        assert thanks["is_conversational_only"] is True
        assert any(w in thanks["direct_reply"].lower() for w in ["welcome", "happy", "glad", "anytime"])

        bye = conversational_service.analyze("bye")
        assert bye["intent"] == "farewell"
        assert bye["is_conversational_only"] is True
        assert any(w in bye["direct_reply"].lower() for w in ["goodbye", "bye", "take care"])

    def test_word_boundary_safety_not_greeting(self):
        """Queries containing 'hi' as part of another word must not be misclassified as greeting."""
        queries = [
            "Which SAP transaction should I use?",
            "What is shipment hierarchy?",
            "Explain archiving in FI-CA",
        ]
        for q in queries:
            analysis = conversational_service.analyze(q)
            assert analysis["intent"] != "greeting"
            assert analysis["is_conversational_only"] is False


class TestSentimentAnalysis:
    """Verify sentiment classification and adaptive tone guidance."""

    def test_urgent_production_incident(self):
        """User: 'Production billing has failed and customers are affected.' -> Urgent sentiment."""
        query = "Production billing has failed and customers are affected."
        sentiment = conversational_service.detect_sentiment(query)
        assert sentiment["sentiment"] == "urgent"
        assert sentiment["confidence"] >= 0.90
        assert "impact assessment" in sentiment["tone_guidance"].lower() or "prioritize" in sentiment["tone_guidance"].lower()

    def test_negative_feedback_or_complaint(self):
        """User: 'Your previous answer is wrong.' -> Negative sentiment with constructive correction tone."""
        query = "Your previous answer is wrong."
        sentiment = conversational_service.detect_sentiment(query)
        assert sentiment["sentiment"] == "negative"
        assert "pointing that out" in sentiment["tone_guidance"].lower() or "verify" in sentiment["tone_guidance"].lower()

    def test_confused_user(self):
        """User: 'I don't understand this SAP BRIM process.' -> Confused sentiment with simplifying guidance."""
        query = "I don't understand this SAP BRIM process."
        sentiment = conversational_service.detect_sentiment(query)
        assert sentiment["sentiment"] == "confused"
        assert "step by step" in sentiment["tone_guidance"].lower() or "break it down" in sentiment["tone_guidance"].lower()

    def test_positive_feedback(self):
        """User expresses appreciation and satisfaction."""
        query = "This explanation was brilliant and very helpful, thanks!"
        sentiment = conversational_service.detect_sentiment(query)
        assert sentiment["sentiment"] == "positive"

    def test_neutral_question(self):
        """Ordinary technical inquiry -> neutral sentiment."""
        query = "What is the primary key of table DFKKOP?"
        sentiment = conversational_service.detect_sentiment(query)
        assert sentiment["sentiment"] == "neutral"


class TestIntentDetectionBeforeRetrieval:
    """Verify 9 required intent categories and mixed-intent routing."""

    def test_pure_emotional_feedback_direct_response(self):
        """Pure complaint returns direct reply asking for technical clarification without running RAG."""
        analysis = conversational_service.analyze("Your previous answer is wrong.")
        assert analysis["intent"] == "emotional_feedback"
        assert analysis["is_conversational_only"] is True
        assert "verify the technical details" in analysis["direct_reply"].lower()

    def test_thanks_but_answer_is_incorrect(self):
        """Context-aware reply acknowledging thanks and prioritizing error correction."""
        analysis = conversational_service.analyze("thanks, but your answer is incorrect")
        assert analysis["intent"] == "emotional_feedback"
        assert analysis["is_conversational_only"] is True
        assert "welcome" in analysis["direct_reply"].lower()
        assert "verify" in analysis["direct_reply"].lower() or "correct" in analysis["direct_reply"].lower()

    def test_mixed_greeting_and_technical_question(self):
        """'hi, I have an SAP issue with billing' -> extracted technical query with greeting preface."""
        analysis = conversational_service.analyze("hi, I have an SAP issue with billing")
        assert analysis["is_mixed"] is True
        assert analysis["is_conversational_only"] is False
        assert "sap issue with billing" in analysis["extracted_query"].lower()

    def test_follow_up_with_history(self):
        """'explain more' with chat history -> recognized as sap_followup."""
        chat_history = [
            {"role": "user", "content": "What is Convergent Invoicing?"},
            {"role": "assistant", "content": "Convergent Invoicing processes billable items."}
        ]
        analysis = conversational_service.analyze("explain more", chat_history=chat_history)
        assert analysis["intent"] == "sap_followup"
        assert analysis["is_conversational_only"] is False

    def test_out_of_scope_detection(self):
        """Non-SAP general knowledge questions flagged as out-of-scope."""
        analysis = conversational_service.analyze("What is the recipe for chocolate cake?")
        assert analysis["intent"] == "out_of_scope"
        assert analysis["is_conversational_only"] is False


class TestRAGIntegrationWithoutRetrieval:
    """Verify that greetings in rag_service bypass Tavily, KB retrieval, and LLM generation."""

    @patch("backend.app.services.rag_service.web_search_service.search_sap_authoritative")
    @patch("backend.app.services.rag_service.retrieval_service.hybrid_search")
    @patch("backend.app.services.rag_service.llm_service.generate_answer")
    def test_greeting_bypasses_all_retrieval(self, mock_llm, mock_kb, mock_web):
        mock_db = MagicMock()
        result = rag_service.process_query(mock_db, "hi")

        assert result["source_type"] == "conversational"
        assert "Hi!" in result["answer"] or "help" in result["answer"].lower()
        assert result["citations"] == []
        assert result["web_sources"] == []
        assert result["grounding_status"] == "not_applicable"

        # Crucial check: zero external calls or database retrieval triggered!
        mock_web.assert_not_called()
        mock_kb.assert_not_called()
        mock_llm.assert_not_called()

    @patch("backend.app.services.rag_service.web_search_service.search_sap_authoritative")
    @patch("backend.app.services.rag_service.retrieval_service.hybrid_search")
    @patch("backend.app.services.rag_service.llm_service.generate_answer")
    def test_variations_bypass_retrieval(self, mock_llm, mock_kb, mock_web):
        mock_db = MagicMock()
        for greeting in ["hii", "hlo", "hloo", "hello", "good morning", "thank you", "bye"]:
            result = rag_service.process_query(mock_db, greeting)
            assert result["source_type"] == "conversational"
            assert result["grounding_status"] == "not_applicable"

        mock_web.assert_not_called()
        mock_kb.assert_not_called()
        mock_llm.assert_not_called()
