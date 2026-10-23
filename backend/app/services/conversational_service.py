import re
import random
from typing import Dict, Any, List, Optional, Tuple


class ConversationalService:
    """
    Lightweight, zero-latency Intent and Sentiment pre-processing service for Clyptus.AI.

    Identifies user sentiment (positive, neutral, negative, confused, urgent),
    classifies intent (greeting, farewell, thanks, help request, feedback, SAP question,
    troubleshooting, follow-up, out-of-scope), and generates dynamic human-like conversational
    replies without invoking external LLMs or RAG pipelines unnecessarily.
    """

    # Normalized greeting patterns
    GREETING_PATTERNS = [
        # Compound greetings first (e.g. "hii hlo", "hi hello")
        (r"^\s*(hi|hii|hlo|hloo|hello|helloo|hey)\s+(hi|hii|hlo|hloo|hello|helloo|hey)\s*$", "compound"),
        # Multi-letter specific variations before single letter
        (r"^\s*h+i{2,}\s*$", "hii"),
        (r"^\s*h+i\s*$", "hi"),
        (r"^\s*h+l+o{2,}\s*$", "hloo"),
        (r"^\s*h+l+o\s*$", "hlo"),
        (r"^\s*h+l+w+\s*$", "hlo"),
        (r"^\s*h+e+l+l+o{2,}\s*$", "helloo"),
        (r"^\s*h+e+l+l+o\s*$", "hello"),
        (r"^\s*h+e+l+o\s*$", "hello"),
        (r"^\s*h+e+y+\s*$", "hey"),
        (r"^\s*howdy\s*$", "howdy"),
        (r"^\s*hola\s*$", "hola"),
        (r"^\s*namaste\s*$", "namaste"),
        (r"^\s*greetings\s*$", "greetings"),
        (r"^\s*good\s*morning\s*$", "good_morning"),
        (r"^\s*good\s*afternoon\s*$", "good_afternoon"),
        (r"^\s*good\s*evening\s*$", "good_evening"),
        (r"^\s*good\s*day\s*$", "good_day"),
        (r"^\s*how\s*(are\s*you|r\s*u|is\s*it\s*going|do\s*you\s*do)\s*\??$", "how_are_you"),
        (r"^\s*what('s|\s*is)\s*up\s*\??$", "what_up"),
        (r"^\s*sup\s*\??$", "what_up"),
    ]

    # Farewell patterns
    FAREWELL_PATTERNS = [
        r"^\s*(bye|byee|byeee|goodbye|good\s*bye|cya|see\s*you|see\s*ya|see\s*u)\s*[!.]*$",
        r"^\s*(talk\s*to\s*you\s*later|ttyl|catch\s*you\s*later)\s*[!.]*$",
        r"^\s*(take\s*care|have\s*a\s*good\s*one|have\s*a\s*great\s*day|have\s*a\s*nice\s*day)\s*[!.]*$",
        r"^\s*good\s*night\s*[!.]*$",
    ]

    # Thanks patterns
    THANKS_PATTERNS = [
        r"^\s*(thank\s*you|thanks|thx|thnx|thank\s*u|tysm)\s*[!.]*$",
        r"^\s*(many\s*thanks|thank\s*you\s*so\s*much|thanks\s*a\s*lot|appreciate\s*it|much\s*appreciated)\s*[!.]*$",
    ]

    # Presence patterns
    PRESENCE_PATTERNS = [
        r"^\s*are\s*you\s*(there|online|listening|awake|real|alive)\s*\??$",
        r"^\s*(u|you)\s*there\s*\??$",
    ]

    # Help request and identity patterns
    HELP_REQUEST_PATTERNS = [
        r"^\s*can\s*you\s*help\s*(me)?\s*\??$",
        r"^\s*i\s*need\s*help\s*[!.]*$",
        r"^\s*(who|what)\s*are\s*you\s*\??$",
        r"^\s*what('s|\s*is)\s*your\s*name\s*\??$",
        r"^\s*what\s*can\s*you\s*do\s*\??$",
        r"^\s*what\s*do\s*you\s*do\s*\??$",
        r"^\s*tell\s*me\s*about\s*yourself\s*[!.]*$",
    ]

    # Follow-up patterns when conversation history exists
    FOLLOWUP_PATTERNS = [
        r"^\s*(can\s*you\s*)?(explain|tell\s*me|elaborate|clarify)\s*(more|further|in\s*detail)\s*\??$",
        r"^\s*more\s*details\s*\??$",
        r"^\s*why\s*\??$",
        r"^\s*how\s*so\s*\??$",
        r"^\s*(give|provide)\s*(an|a|me\s*an|me\s*a)?\s*example\s*\??$",
        r"^\s*explain\s*this\s*\??$",
        r"^\s*what\s*about\s*(that|it)\s*\??$",
        r"^\s*continue\s*[!.]*$",
    ]

    # Out of scope topics (non-SAP general knowledge)
    OUT_OF_SCOPE_PATTERNS = [
        r"\b(weather|temperature|forecast|rain|climate)\b",
        r"\b(recipe|cook|bake|ingredients|dinner|lunch|breakfast)\b",
        r"\b(cricket|football|soccer|nba|ipl|olympics|sports)\b",
        r"\b(movie|cinema|actor|actress|hollywood|bollywood|song|music)\b",
        r"\b(president|prime\s*minister|election|politics|parliament)\b",
    ]

    # Sentiment vocabulary
    POSITIVE_WORDS = {
        "great", "awesome", "excellent", "perfect", "helpful", "good", "nice",
        "love", "kudos", "brilliant", "wonderful", "super", "fantastic", "appreciate",
        "thanks", "thank", "impressive", "clever", "smart"
    }

    NEGATIVE_WORDS = {
        "wrong", "incorrect", "false", "bad", "terrible", "horrible", "useless",
        "error", "not working", "doesnt work", "doesn't work", "failed", "disappointed",
        "frustrated", "annoying", "poor", "mistake", "garbage", "hate", "unhelpful",
        "inaccurate", "hallucination", "nonsense", "rubbish"
    }

    CONFUSED_WORDS = {
        "confused", "don't understand", "dont understand", "unclear", "lost",
        "not clear", "what does that mean", "makes no sense", "hard to understand",
        "overwhelming", "explain simply", "too complex", "not following", "huh",
        "what do you mean", "can you simplify"
    }

    URGENT_WORDS = {
        "production", "prod", "critical", "urgent", "emergency", "p1", "p0",
        "severity 1", "sev 1", "outage", "downtime", "customers affected",
        "system down", "live issue", "blocker", "showstopper", "immediate", "asap"
    }

    # Dynamic greeting replies
    GREETING_RESPONSES = {
        "hi": [
            "Hi! 👋 How can I help you today?",
            "Hi! 👋 What SAP topic can I assist you with?",
            "Hi there! How can I help you today? 😊"
        ],
        "hii": [
            "Hii! 😊 How can I help you?",
            "Hii! 👋 What can I help you with today?",
            "Hii there! Ready to help with any SAP questions. 😊"
        ],
        "hlo": [
            "Hello! 👋 How can I help you today?",
            "Hello! 😊 What can I help you with?",
            "Hello! How can I assist you today? 👋"
        ],
        "hloo": [
            "Helloo! 😊 What can I help you with?",
            "Helloo! 👋 How can I help you today?",
            "Helloo! Ready to help with your SAP queries. 😊"
        ],
        "compound": [
            "Hello! 😊 How can I help you today?",
            "Hi there! 👋 What can I assist you with?",
            "Hello! Ready to assist you with any SAP topic. 😊"
        ],
        "hello": [
            "Hello! How can I help you today? 👋",
            "Hello! What can I assist you with today?",
            "Hello! How can I help you with SAP today? 😊"
        ],
        "helloo": [
            "Helloo! 😊 What can I help you with?",
            "Helloo! How can I help you today? 👋"
        ],
        "hey": [
            "Hey! 😊 What can I help you with?",
            "Hey there! How can I assist you today? 👋",
            "Hey! Ready for your SAP questions. 😊"
        ],
        "good_morning": [
            "Good morning! ☀️ How can I help you today?",
            "Good morning! What SAP topic are you working on today? 😊",
            "Good morning! How can I assist you today? ☀️"
        ],
        "good_afternoon": [
            "Good afternoon! How can I help you today? 😊",
            "Good afternoon! What can I assist you with today? 👋"
        ],
        "good_evening": [
            "Good evening! How can I help you today? 😊",
            "Good evening! What SAP questions do you have tonight? 👋"
        ],
        "good_day": [
            "Good day! How can I help you with SAP today? 😊",
            "Good day! What can I assist you with? 👋"
        ],
        "how_are_you": [
            "I'm doing well, thank you for asking! 😊 How can I help you with SAP today?",
            "Doing great and ready to help! What SAP topic are we exploring today? 👋",
            "I'm doing well! 😊 What can I assist you with today?"
        ],
        "what_up": [
            "Not much, just ready to solve some SAP challenges! 😊 What's on your mind?",
            "Hey! Ready to assist you with SAP. What can I help with today? 👋"
        ],
        "default": [
            "Hello! 👋 How can I help you today?",
            "Hi there! 😊 What can I assist you with today?",
            "Hello! Ready to help with your SAP queries. 👋"
        ]
    }

    FAREWELL_RESPONSES = [
        "Goodbye! Have a great day! 👋",
        "Goodbye! Have a great day!",
        "Bye! Feel free to reach out whenever you have more SAP questions. 😊",
        "Take care! Have a wonderful day! 👋",
    ]

    THANKS_RESPONSES = [
        "You're welcome! 😊 Happy to help.",
        "You're welcome! Happy to help. 😊",
        "Glad I could help! Let me know if you need anything else on SAP. 👋",
        "Anytime! Happy to support your SAP questions. 😊",
    ]

    PRESENCE_RESPONSES = [
        "Yes, I'm here! What would you like help with? 😊",
        "Yes, I'm here! What would you like help with?",
        "Yes, I'm here and ready to assist! What can I help you with today? 👋",
    ]

    HELP_REQUEST_RESPONSES = [
        "I'm right here and ready to assist! Ask me any SAP or SAP BRIM question. 👋",
        "I'm Clyptus.AI, your enterprise SAP specialist. How can I help you today? 😊",
        "I'm here to help with SAP architecture, transactions, configuration, and troubleshooting. What do you need assistance with? 👋",
    ]

    @staticmethod
    def _clean_and_normalize(text: str) -> str:
        """Strip punctuation and reduce excessive letter repetitions (e.g. hiiiii -> hii)."""
        t = text.strip().lower()
        # Remove emojis and punctuation for regex matching
        t = re.sub(r"[^\w\s]", "", t)
        # Collapse 3+ repeating letters to 2
        t = re.sub(r"(.)\1{2,}", r"\1\1", t)
        return t.strip()

    def detect_sentiment(self, text: str) -> Dict[str, Any]:
        """
        Classifies user sentiment into positive, neutral, negative, confused, or urgent.
        Computes match score and provides adaptive tone guidance.
        """
        raw_lower = text.strip().lower()
        words = set(re.findall(r"\b[a-z0-9_'-]+\b", raw_lower))

        # Check for urgent signals first (production impact overrides other tones)
        urgent_matches = [w for w in self.URGENT_WORDS if w in raw_lower or w in words]
        if urgent_matches and any(p in raw_lower for p in ["failed", "down", "outage", "critical", "incident", "affected", "error", "broken", "stop", "issue"]):
            return {
                "sentiment": "urgent",
                "confidence": 0.95,
                "matches": urgent_matches,
                "tone_guidance": "Understood. Let's prioritize impact assessment, evidence collection, and safe recovery steps."
            }

        # Check negative signals
        negative_matches = [w for w in self.NEGATIVE_WORDS if w in raw_lower or w in words]
        if negative_matches and any(p in raw_lower for p in ["wrong", "incorrect", "false", "doesn't work", "doesnt work", "error", "not working", "fail", "useless", "bad"]):
            return {
                "sentiment": "negative",
                "confidence": 0.85,
                "matches": negative_matches,
                "tone_guidance": "Thanks for pointing that out. Let's verify the technical details and correct the answer."
            }

        # Check confused signals
        confused_matches = [w for w in self.CONFUSED_WORDS if w in raw_lower or w in words]
        if confused_matches:
            return {
                "sentiment": "confused",
                "confidence": 0.80,
                "matches": confused_matches,
                "tone_guidance": "No problem. Let's break it down step by step in simple terms."
            }

        # Check positive signals
        positive_matches = [w for w in self.POSITIVE_WORDS if w in words]
        if positive_matches and not negative_matches:
            return {
                "sentiment": "positive",
                "confidence": 0.80,
                "matches": positive_matches,
                "tone_guidance": "Maintain a warm, enthusiastic, professional senior SAP consultant tone."
            }

        return {
            "sentiment": "neutral",
            "confidence": 0.90,
            "matches": [],
            "tone_guidance": ""
        }

        return {
            "sentiment": "neutral",
            "confidence": 0.90,
            "matches": [],
            "tone_guidance": ""
        }

    def classify_intent(self, text: str, chat_history: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        """
        Lightweight intent classifier recognizing:
        1. greeting
        2. farewell
        3. thanks
        4. help_request
        5. emotional_feedback
        6. sap_troubleshooting
        7. sap_question
        8. sap_followup
        9. out_of_scope
        Also detects mixed inputs (e.g. 'hi, I have a billing issue').
        """
        raw = text.strip()
        cleaned = self._clean_and_normalize(raw)
        raw_lower = raw.lower()

        # 1. Pure Greetings
        for pat, key in self.GREETING_PATTERNS:
            if re.search(pat, cleaned, re.IGNORECASE):
                reply = random.choice(self.GREETING_RESPONSES.get(key, self.GREETING_RESPONSES["default"]))
                if "sap" not in reply.lower():
                    reply = f"{reply.rstrip('!?.')} I can help with SAP-related questions. What SAP topic can I assist with?"
                return {
                    "intent": "greeting",
                    "is_conversational_only": True,
                    "is_mixed": False,
                    "extracted_query": raw,
                    "direct_reply": reply,
                    "greeting_key": key
                }

        # 2. Pure Farewells
        for pat in self.FAREWELL_PATTERNS:
            if re.search(pat, cleaned, re.IGNORECASE):
                reply = random.choice(self.FAREWELL_RESPONSES)
                return {
                    "intent": "farewell",
                    "is_conversational_only": True,
                    "is_mixed": False,
                    "extracted_query": raw,
                    "direct_reply": reply
                }

        # 3. Pure Thanks
        for pat in self.THANKS_PATTERNS:
            if re.search(pat, cleaned, re.IGNORECASE):
                reply = random.choice(self.THANKS_RESPONSES)
                return {
                    "intent": "thanks",
                    "is_conversational_only": True,
                    "is_mixed": False,
                    "extracted_query": raw,
                    "direct_reply": reply
                }

        # 4. Presence Requests (e.g. "are you there?")
        for pat in self.PRESENCE_PATTERNS:
            if re.search(pat, cleaned, re.IGNORECASE):
                reply = random.choice(self.PRESENCE_RESPONSES)
                return {
                    "intent": "help_request",
                    "is_conversational_only": True,
                    "is_mixed": False,
                    "extracted_query": raw,
                    "direct_reply": reply
                }

        # 5. Help & Identity Requests (e.g. "who are you?", "can you help me?")
        for pat in self.HELP_REQUEST_PATTERNS:
            if re.search(pat, cleaned, re.IGNORECASE):
                reply = random.choice(self.HELP_REQUEST_RESPONSES)
                return {
                    "intent": "help_request",
                    "is_conversational_only": True,
                    "is_mixed": False,
                    "extracted_query": raw,
                    "direct_reply": reply
                }

        # 5. Pure Emotional Feedback without a question
        negative_feedback_patterns = [
            r"^\s*your\s*previous\s*answer\s*is\s*wrong\s*[!.]*$",
            r"^\s*(that('s|\s*is)\s*wrong|this\s*is\s*incorrect|you\s*are\s*wrong)\s*[!.]*$",
            r"^\s*(incorrect\s*answer|wrong\s*information)\s*[!.]*$",
        ]
        for pat in negative_feedback_patterns:
            if re.search(pat, cleaned, re.IGNORECASE):
                reply = "Thanks for pointing that out. Let's verify the technical details and correct the answer. Which specific transaction, document, or step needs review?"
                return {
                    "intent": "emotional_feedback",
                    "is_conversational_only": True,
                    "is_mixed": False,
                    "extracted_query": raw,
                    "direct_reply": reply
                }

        # 6. Check for Mixed Intent (e.g., Greeting + Technical Inquiry)
        mixed_greeting_match = re.match(
            r"^(hi+|hello+|hlo+|hey+|good\s*(morning|afternoon|evening))\s*[,!.:-]*\s*(.+)$",
            raw_lower,
            re.IGNORECASE
        )
        if mixed_greeting_match:
            subsequent = mixed_greeting_match.group(3) if mixed_greeting_match.group(3) else mixed_greeting_match.group(2)
            subsequent = subsequent.strip()
            if len(subsequent.split()) >= 2:
                return {
                    "intent": "sap_question",
                    "is_conversational_only": False,
                    "is_mixed": True,
                    "extracted_query": subsequent,
                    "greeting_preface": "Hello! ",
                    "direct_reply": None
                }

        # Mixed Thanks + Technical Query or Correction
        mixed_thanks_match = re.match(
            r"^(thanks|thank\s*you|thx)\s*[,!.:-]*\s*(but|however|can\s*you|what\s*about)\s+(.+)$",
            raw_lower,
            re.IGNORECASE
        )
        if mixed_thanks_match:
            subsequent = mixed_thanks_match.group(3).strip()
            # If the user is just saying the previous answer was wrong (e.g. "thanks, but your answer is incorrect")
            if any(w in subsequent for w in ["wrong", "incorrect", "false", "mistake", "error in answer"]):
                return {
                    "intent": "emotional_feedback",
                    "is_conversational_only": True,
                    "is_mixed": False,
                    "extracted_query": raw,
                    "direct_reply": "You're welcome! Thanks for pointing that out. Let's verify the technical details and correct the answer. Which specific transaction, document, or step needs review?"
                }
            return {
                "intent": "sap_question",
                "is_conversational_only": False,
                "is_mixed": True,
                "extracted_query": subsequent,
                "greeting_preface": "You're welcome! ",
                "direct_reply": None
            }

        # 7. Check for follow-up questions when conversation history exists
        if chat_history and len(chat_history) > 0:
            for pat in self.FOLLOWUP_PATTERNS:
                if re.search(pat, cleaned, re.IGNORECASE):
                    return {
                        "intent": "sap_followup",
                        "is_conversational_only": False,
                        "is_mixed": False,
                        "extracted_query": raw,
                        "direct_reply": None
                    }

        # 8. Check for out-of-scope topics
        sap_mentions = [
            "sap", "brim", "convergent", "charging", "invoicing", "fi-ca", "fica",
            "som", "hana", "s/4hana", "bapi", "idoc", "abap", "fiori", "billable",
            "provider contract", "consumption", "tcode", "t-code", "table"
        ]
        has_sap_keyword = any(k in raw_lower for k in sap_mentions)
        if not has_sap_keyword:
            for pat in self.OUT_OF_SCOPE_PATTERNS:
                if re.search(pat, raw_lower, re.IGNORECASE):
                    return {
                        "intent": "out_of_scope",
                        "is_conversational_only": False,
                        "is_mixed": False,
                        "extracted_query": raw,
                        "direct_reply": None
                    }

        # 9. Check for Troubleshooting scenarios vs General SAP questions
        troubleshooting_keywords = [
            "error", "fail", "failed", "dump", "stuck", "exception", "abort",
            "cannot", "terminate", "issue", "troubleshoot", "incident", "outage"
        ]
        if any(w in raw_lower for w in troubleshooting_keywords):
            return {
                "intent": "sap_troubleshooting",
                "is_conversational_only": False,
                "is_mixed": False,
                "extracted_query": raw,
                "direct_reply": None
            }

        return {
            "intent": "sap_question",
            "is_conversational_only": False,
            "is_mixed": False,
            "extracted_query": raw,
            "direct_reply": None
        }

    def analyze(self, text: str, chat_history: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        """
        End-to-end conversational analysis combining intent classification and sentiment analysis.
        """
        sentiment_data = self.detect_sentiment(text)
        intent_data = self.classify_intent(text, chat_history=chat_history)

        return {
            "intent": intent_data["intent"],
            "is_conversational_only": intent_data["is_conversational_only"],
            "is_mixed": intent_data.get("is_mixed", False),
            "extracted_query": intent_data.get("extracted_query", text),
            "direct_reply": intent_data.get("direct_reply"),
            "greeting_preface": intent_data.get("greeting_preface"),
            "sentiment": sentiment_data["sentiment"],
            "sentiment_confidence": sentiment_data["confidence"],
            "sentiment_matches": sentiment_data.get("matches", []),
            "tone_guidance": sentiment_data["tone_guidance"],
        }


conversational_service = ConversationalService()
