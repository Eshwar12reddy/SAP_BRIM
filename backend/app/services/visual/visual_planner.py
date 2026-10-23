
"""
Visual Planner for question-driven image and diagram generation.
Decides when, what, and how to draw based on user inquiry, chat history,
memory, and evidence.

Supports explicit requests, proactive generation, follow-up resolution,
revisions, and SAP-only visual generation.
"""

import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from backend.app.config import settings
from backend.app.services.sap_classifier import sap_classifier
from backend.app.services.visual.spec_validator import (
    validate_diagram_spec,
    sanitize_diagram_spec,
    sanitize_generative_prompt,
)

logger = logging.getLogger(__name__)

EXPLICIT_VISUAL_KEYWORDS = [
    "draw",
    "diagram",
    "show me",
    "illustrate",
    "visualize",
    "flow chart",
    "flowchart",
    "architecture",
    "give me an image",
    "give me a picture",
    "generate an image",
    "map it",
    "what does it look like",
    "draw that",
    "show it as a diagram",
    "make a diagram",
    "create a diagram",
    "picture of",
    "visual",
    "visual representation",
]

PROACTIVE_TOPIC_TRIGGERS = [
    "end-to-end",
    "lifecycle",
    "order to cash",
    "subscription order to fi-ca",
    "subscription order",
    "billable item",
    "billing document",
    "convergent charging",
    "convergent invoicing",
    "rates a usage event",
    "rating",
    "integration",
    "landscape",
    "decision tree",
    "troubleshooting path",
    "comparison",
    "compare",
    " vs ",
    "versus",
    "difference between",
    "sequence",
    "data flow",
    "document flow",
]

NO_VISUAL_PHRASES = [
    "no image",
    "no diagram",
    "no picture",
    "without diagram",
    "without image",
    "don't draw",
    "dont draw",
    "do not draw",
    "text only",
    "no visual",
    "only text",
]

SIMPLE_DEFINITION_PATTERNS = [
    r"^what\s+is\s+[\w\s\-/]+[?]?$",
    r"^what\s+are\s+[\w\s\-/]+[?]?$",
    r"^define\s+[\w\s\-/]+[?]?$",
    r"^who\s+is\s+[\w\s\-/]+[?]?$",
    r"^meaning\s+of\s+[\w\s\-/]+[?]?$",
]


class VisualPlanner:
    """Plans diagrams and images for SAP-related questions only."""

    @staticmethod
    def _parse_chat_history(context: str) -> List[Dict[str, str]]:
        """
        Convert formatted conversation history into the role/content
        message format expected by the SAP classifier.

        Expected input:
            User: Explain SAP BRIM.
            Assistant: SAP BRIM supports...
            User: Draw that as a diagram.
        """
        if not context:
            return []

        messages: List[Dict[str, str]] = []

        pattern = (
            r"^(User|Assistant):\s*"
            r"(.*?)(?=^(?:User|Assistant):|\Z)"
        )

        for role, content in re.findall(
            pattern,
            context,
            re.IGNORECASE | re.MULTILINE | re.DOTALL,
        ):
            messages.append(
                {
                    "role": role.lower(),
                    "content": content.strip(),
                }
            )

        return messages

    def evaluate_request(
        self,
        query: str,
        chat_history_context: str = "",
        memory_context: str = "",
        answer_text: str = "",
    ) -> Dict[str, Any]:
        """
        Determine whether a visual should be generated.

        SAP-only policy:
        - SAP-related requests may proceed through visual planning.
        - Contextual follow-ups may proceed when the conversation
          establishes an SAP-related subject.
        - Unrelated questions must not generate visuals.
        - Explicit requests for no visuals always take precedence.
        """
        q_lower = query.strip().lower()
        mem_lower = memory_context.lower() if memory_context else ""

        # 1. Respect explicit requests not to generate visuals.
        # This check does not need classifier execution.
        for phrase in NO_VISUAL_PHRASES:
            if phrase in q_lower:
                return {
                    "wants_visual": False,
                    "reason": (
                        "User explicitly requested no visuals "
                        f"('{phrase}')"
                    ),
                    "trigger": "suppressed",
                }

        # 2. Respect standing preferences against visuals.
        if (
            "no diagram" in mem_lower
            or "no image" in mem_lower
            or "never diagram" in mem_lower
        ):
            has_explicit_now = any(
                keyword in q_lower
                for keyword in EXPLICIT_VISUAL_KEYWORDS
            )

            if not has_explicit_now:
                return {
                    "wants_visual": False,
                    "reason": (
                        "Standing user preference prefers "
                        "no diagrams/images"
                    ),
                    "trigger": "suppressed_by_preference",
                }

        # 3. Enforce SAP-only visual generation.
        # Convert the formatted conversation history into messages
        # so the classifier can identify contextual SAP follow-ups.
        chat_history = self._parse_chat_history(
            chat_history_context
        )

        try:
            is_sap_query = sap_classifier.is_sap_related(
                query,
                chat_history=chat_history,
            )
        except Exception:
            # Fail closed: a classifier failure must not enable
            # visual generation for a potentially unrelated query.
            logger.exception(
                "SAP classification failed during visual planning."
            )

            return {
                "wants_visual": False,
                "reason": (
                    "SAP scope could not be verified. "
                    "Visual generation is disabled."
                ),
                "trigger": "sap_classification_error",
            }

        if not is_sap_query:
            logger.info(
                "Visual generation suppressed for a non-SAP query."
            )

            return {
                "wants_visual": False,
                "reason": (
                    "Visual generation is restricted to "
                    "SAP-related questions."
                ),
                "trigger": "out_of_scope",
            }

        # 4. Suppress simple definitions unless a visual is explicitly
        # requested. The SAP scope check has already passed.
        is_simple_def = any(
            re.match(pattern, q_lower)
            for pattern in SIMPLE_DEFINITION_PATTERNS
        )

        if is_simple_def:
            has_explicit = any(
                keyword in q_lower
                for keyword in [
                    "draw",
                    "diagram",
                    "illustrate",
                    "image",
                    "architecture",
                ]
            )

            if not has_explicit:
                return {
                    "wants_visual": False,
                    "reason": (
                        "Simple definition inquiry; "
                        "text response is standard."
                    ),
                    "trigger": "suppressed_simple_definition",
                }

        # 5. Detect an explicit visual request.
        is_explicit = False
        matched_explicit_kw = ""

        for keyword in EXPLICIT_VISUAL_KEYWORDS:
            if keyword in q_lower:
                is_explicit = True
                matched_explicit_kw = keyword
                break

        # Detect a diagram revision request.
        is_revision = (
            "make it simpler" in q_lower
            or "simplify" in q_lower
            or "revise diagram" in q_lower
        )

        if is_explicit or is_revision:
            visual_type, is_generative = self._resolve_visual_type(
                q_lower,
                chat_history_context,
                is_explicit=True,
            )

            return {
                "wants_visual": True,
                "trigger": (
                    "revision" if is_revision else "explicit"
                ),
                "matched_keyword": (
                    matched_explicit_kw
                    or ("simplify" if is_revision else "")
                ),
                "visual_type": visual_type,
                "is_generative": is_generative,
                "is_revision": is_revision,
            }

        # 6. Detect SAP-related topics that benefit from proactive
        # structured diagrams.
        combined_text = f"{q_lower} {answer_text.lower()}"
        proactive_matched = None

        for trigger in PROACTIVE_TOPIC_TRIGGERS:
            if trigger in combined_text:
                proactive_matched = trigger
                break

        if proactive_matched:
            has_process_detail = (
                len(answer_text.split()) > 6
                or any(
                    word in q_lower
                    for word in [
                        "rates",
                        "rating",
                        "lifecycle",
                        "flow",
                        "landscape",
                        "event",
                        "compare",
                        "comparison",
                        "troubleshoot",
                        "decision",
                    ]
                )
            )

            if has_process_detail:
                visual_type, _ = self._resolve_visual_type(
                    combined_text,
                    chat_history_context,
                    is_explicit=False,
                )

                return {
                    "wants_visual": True,
                    "trigger": "proactive",
                    "matched_keyword": proactive_matched,
                    "visual_type": visual_type,
                    # Proactive visuals remain structured diagrams.
                    "is_generative": False,
                    "is_revision": False,
                }

        # 7. No visual criteria were met.
        return {
            "wants_visual": False,
            "reason": (
                "No explicit request and no proactive "
                "visual criteria met."
            ),
            "trigger": "none",
        }

    def _resolve_visual_type(
        self,
        text: str,
        chat_history: str = "",
        is_explicit: bool = False,
    ) -> Tuple[str, bool]:
        """
        Resolve the best visual type and whether it uses
        generative image rendering.
        """
        # Path B: generative conceptual illustration.
        if settings.ENABLE_GENERATIVE_IMAGES and (
            "generate an image" in text
            or "picture of" in text
            or "concept illustration" in text
            or "conceptual" in text
        ):
            return "generative_illustration", True

        # Path A: structured SAP diagrams.
        if (
            "architecture" in text
            or "landscape" in text
            or "integration" in text
            or "brim" in text
        ):
            return "architecture", False

        if (
            "decision" in text
            or "tree" in text
            or "troubleshooting" in text
        ):
            return "decision_tree", False

        if "sequence" in text or "interaction" in text:
            return "sequence", False

        if (
            "compare" in text
            or "comparison" in text
            or "difference" in text
        ):
            return "comparison", False

        if (
            "lifecycle" in text
            or "document flow" in text
            or "order to" in text
            or "subscription order" in text
        ):
            return "lifecycle", False

        return "flow_diagram", False

    def resolve_subject(
        self,
        query: str,
        chat_history_context: str = "",
        memory_context: str = "",
    ) -> str:
        """
        Resolve the subject for follow-ups such as
        'draw that' or 'show it as a diagram'.
        """
        q = query.strip()
        q_lower = q.lower()

        # Extract a subject if the current query supplies one.
        cleaned = re.sub(
            r"^(draw|show me|illustrate|visualize|diagram|"
            r"generate an image of)\s+(that|it|this)\b",
            "",
            q_lower,
        ).strip()

        if cleaned and len(cleaned) > 3:
            return cleaned

        # Otherwise, find the most recent user message.
        if chat_history_context:
            matches = re.findall(
                r"User:\s*(.*?)(?=\nAssistant:|\Z)",
                chat_history_context,
                re.DOTALL | re.IGNORECASE,
            )

            if matches:
                last_user_msg = matches[-1].strip()

                last_topic = re.sub(
                    r"(draw|show|what is|how to|explain)\s*",
                    "",
                    last_user_msg,
                    flags=re.IGNORECASE,
                ).strip()

                if last_topic:
                    return last_topic

        # Fallback for an established SAP conversation.
        return "SAP End-to-End Process Flow"

    def plan_visual_specs(
        self,
        query: str,
        answer_text: str,
        evidence_text: str = "",
        chat_history_context: str = "",
        memory_context: str = "",
        previous_spec: Optional[Dict[str, Any]] = None,
        corpus: str = "",
    ) -> List[Dict[str, Any]]:
        """
        Create validated diagram specifications or generative prompts.

        Visual planning is restricted to SAP-related questions.
        Technical labels are sanitized against the available answer
        and evidence corpus.
        """
        eval_result = self.evaluate_request(
            query=query,
            chat_history_context=chat_history_context,
            memory_context=memory_context,
            answer_text=answer_text,
        )

        if not eval_result.get("wants_visual"):
            return []

        resolved_subject = self.resolve_subject(
            query,
            chat_history_context,
            memory_context,
        )

        visual_type = eval_result.get(
            "visual_type",
            "flow_diagram",
        )

        is_generative = eval_result.get(
            "is_generative",
            False,
        )

        is_revision = eval_result.get(
            "is_revision",
            False,
        )

        combined_corpus = (
            f"{corpus} {answer_text} {evidence_text}"
        ).strip()

        specs: List[Dict[str, Any]] = []

        # Handle diagram revision.
        if is_revision and previous_spec:
            revised = self._simplify_spec(
                previous_spec,
                combined_corpus,
            )
            specs.append(revised)
            return specs

        # Path B: generative conceptual image.
        if (
            is_generative
            and settings.ENABLE_GENERATIVE_IMAGES
        ):
            prompt = sanitize_generative_prompt(
                f"Professional clean conceptual enterprise "
                f"software diagram illustrating {resolved_subject}. "
                "Architectural concept, clean modern vector style, "
                "blueprint design."
            )

            spec = {
                "type": "generative_illustration",
                "title": (
                    "Conceptual Illustration: "
                    f"{resolved_subject.title()}"
                ),
                "caption": (
                    f"Visual concept of {resolved_subject}. "
                    "AI-generated illustration - not an SAP screenshot."
                ),
                "prompt": prompt,
                "is_generative": True,
            }

            specs.append(spec)
            return specs[: settings.MAX_VISUALS_PER_ANSWER]

        # Path A: structured diagram.
        spec = self._build_structured_spec(
            visual_type=visual_type,
            subject=resolved_subject,
            query=query,
            answer_text=answer_text,
            corpus=combined_corpus,
        )

        sanitized_spec = sanitize_diagram_spec(
            spec,
            combined_corpus,
        )

        specs.append(sanitized_spec)

        return specs[: settings.MAX_VISUALS_PER_ANSWER]

    def _build_structured_spec(
        self,
        visual_type: str,
        subject: str,
        query: str,
        answer_text: str,
        corpus: str,
    ) -> Dict[str, Any]:
        """Build a structured diagram for an SAP-related topic."""
        q_lower = query.lower()
        sub_lower = subject.lower()
        ans_lower = answer_text.lower()

        # 1. Comparison diagram.
        if (
            visual_type == "comparison"
            or "compare" in q_lower
            or "difference" in q_lower
            or " vs " in q_lower
        ):
            return {
                "type": "comparison",
                "title": (
                    f"Structural Comparison: {subject.title()}"
                ),
                "caption": (
                    "Comparative architectural breakdown of "
                    "components. AI-generated illustration - "
                    "not an SAP screenshot."
                ),
                "columns": [
                    {
                        "header": "Component A (e.g., CI)",
                        "items": [
                            "Aggregates high-volume billable items",
                            "Handles partner settlement and "
                            "complex invoice layout",
                            "Generates legal invoice document",
                        ],
                    },
                    {
                        "header": "Component B (e.g., FI-CA)",
                        "items": [
                            "High-volume subledger accounting",
                            "Manages payments, clearing, dunning, "
                            "and returns",
                            "Summarized reconciliation postings "
                            "to General Ledger",
                        ],
                    },
                ],
            }

        # 2. Decision tree / troubleshooting diagram.
        if (
            visual_type == "decision_tree"
            or "troubleshoot" in q_lower
            or "decision" in q_lower
        ):
            return {
                "type": "decision_tree",
                "title": (
                    f"Resolution Decision Tree: {subject.title()}"
                ),
                "caption": (
                    "Decision pathways and verification criteria. "
                    "AI-generated illustration - not an SAP screenshot."
                ),
                "root_question": (
                    "Does the document exist in the initial stage?"
                ),
                "branches": [
                    {
                        "condition": "Yes (Document Found)",
                        "action": (
                            "Inspect processing status code and "
                            "application logs in SLG1"
                        ),
                        "status": "PASS",
                    },
                    {
                        "condition": "No (Missing Document)",
                        "action": (
                            "Check interface queue monitor SMQ1/SMQ2 "
                            "for backlog or RFC failure"
                        ),
                        "status": "FAIL",
                    },
                ],
            }

        # 3. System architecture / landscape.
        if (
            visual_type == "architecture"
            or "architecture" in q_lower
            or "landscape" in q_lower
        ):
            return {
                "type": "architecture",
                "title": (
                    f"System Architecture: {subject.title()}"
                ),
                "caption": (
                    f"Enterprise architectural components for "
                    f"{subject}. AI-generated illustration - "
                    "not an SAP screenshot."
                ),
                "groups": [
                    {
                        "id": "channel_layer",
                        "title": "Omnichannel Engagement",
                        "color": "#1e3a5f",
                        "nodes": [
                            {
                                "id": "portal",
                                "title": (
                                    "Self-Service Portal / E-Commerce"
                                ),
                                "component": "Fiori / Web",
                            },
                            {
                                "id": "som_crm",
                                "title": (
                                    "Subscription Order Management"
                                ),
                                "component": "S/4HANA SOM",
                            },
                        ],
                    },
                    {
                        "id": "rating_layer",
                        "title": "Real-Time Monetization Engine",
                        "color": "#0d9488",
                        "nodes": [
                            {
                                "id": "cc_rating",
                                "title": (
                                    "SAP Convergent Charging (CC)"
                                ),
                                "component": "Core Server",
                            },
                            {
                                "id": "allowance",
                                "title": "Allowance & Balance Store",
                                "component": "CC Database",
                            },
                        ],
                    },
                    {
                        "id": "financial_layer",
                        "title": "Receivables & General Ledger",
                        "color": "#2563eb",
                        "nodes": [
                            {
                                "id": "ci_engine",
                                "title": (
                                    "SAP Convergent Invoicing (CI)"
                                ),
                                "component": "S/4HANA",
                            },
                            {
                                "id": "fica_ledger",
                                "title": (
                                    "Contract Accounting (FI-CA)"
                                ),
                                "component": "Subledger",
                            },
                        ],
                    },
                ],
                "edges": [
                    {
                        "source": "som_crm",
                        "target": "cc_rating",
                        "label": "ODI Contract Sync",
                    },
                    {
                        "source": "cc_rating",
                        "target": "ci_engine",
                        "label": "Billable Items",
                    },
                    {
                        "source": "ci_engine",
                        "target": "fica_ledger",
                        "label": "Open Items / Reconciliation",
                    },
                ],
            }

        # 4. SOM to FI-CA / subscription order posting lifecycle.
        if (
            "som" in q_lower
            or "fi-ca" in q_lower
            or "subscription order" in q_lower
            or "order to" in q_lower
            or "end-to-end" in q_lower
            or "billable item" in q_lower
        ):
            return {
                "type": "lifecycle",
                "title": "SAP BRIM End-to-End Document Flow",
                "caption": (
                    "Document lifecycle from Subscription Order "
                    "via CC and CI into FI-CA posting. "
                    "AI-generated illustration - not an SAP screenshot."
                ),
                "nodes": [
                    {
                        "id": "som",
                        "title": "Subscription Order (SOM)",
                        "description": (
                            "Customer order captures products, "
                            "recurring charges, and counters"
                        ),
                        "component": "SOM",
                        "tcode": "CRMD_ORDER",
                    },
                    {
                        "id": "cc",
                        "title": "Usage Rating (SAP CC)",
                        "description": (
                            "Real-time usage rating and allowance "
                            "consumption via charging logic"
                        ),
                        "component": "Convergent Charging",
                    },
                    {
                        "id": "ci_bit",
                        "title": "Billable Items (CI)",
                        "description": (
                            "Billable items created and stored in "
                            "the relevant processing status"
                        ),
                        "component": "Convergent Invoicing",
                        "tcode": "FKKBIX_BIT_M",
                    },
                    {
                        "id": "ci_inv",
                        "title": "Invoicing & Billing (CI)",
                        "description": (
                            "Mass billing processes eligible billable "
                            "items and creates invoice documents"
                        ),
                        "component": "Convergent Invoicing",
                        "tcode": "FKKINV_M",
                    },
                    {
                        "id": "fica_post",
                        "title": (
                            "Contract Account Posting (FI-CA)"
                        ),
                        "description": (
                            "Receivables are posted to the contract "
                            "account and reconciliation is performed"
                        ),
                        "component": "FI-CA",
                        "tcode": "FPG1",
                    },
                ],
                "edges": [
                    {
                        "source": "som",
                        "target": "cc",
                        "label": "Contract / Product Context",
                    },
                    {
                        "source": "cc",
                        "target": "ci_bit",
                        "label": "Rated Usage / Charge Data",
                    },
                    {
                        "source": "ci_bit",
                        "target": "ci_inv",
                        "label": "Billable Item Processing",
                    },
                    {
                        "source": "ci_inv",
                        "target": "fica_post",
                        "label": "Invoice / Receivables Posting",
                    },
                ],
            }

        # 5. Convergent Charging rating flow.
        if (
            "convergent charging" in q_lower
            or "rate" in q_lower
            or "usage event" in q_lower
            or " cc " in f" {q_lower} "
        ):
            return {
                "type": "flow_diagram",
                "title": (
                    "SAP Convergent Charging: Usage Rating Process"
                ),
                "caption": (
                    "Step-by-step rating logic for incoming "
                    "consumption events in SAP CC. "
                    "AI-generated illustration - not an SAP screenshot."
                ),
                "nodes": [
                    {
                        "id": "step1",
                        "title": "Receive Consumption Event",
                        "description": (
                            "Mediation sends the usage event to "
                            "the configured SAP CC interface"
                        ),
                        "component": "SAP CC",
                    },
                    {
                        "id": "step2",
                        "title": "Contract & Allowance Lookup",
                        "description": (
                            "Resolve the applicable provider contract "
                            "and relevant allowance or balance data"
                        ),
                        "component": "Core Server",
                    },
                    {
                        "id": "step3",
                        "title": "Price Plan Execution",
                        "description": (
                            "Calculate charges using the configured "
                            "price plan, tariffs, and applicable rules"
                        ),
                        "component": "Rating Engine",
                    },
                    {
                        "id": "step4",
                        "title": "Billable Item Generation",
                        "description": (
                            "Rated charge data is made available "
                            "for downstream billing processing"
                        ),
                        "component": "CI Integration",
                    },
                ],
                "edges": [
                    {
                        "source": "step1",
                        "target": "step2",
                        "label": "Event Ingestion",
                    },
                    {
                        "source": "step2",
                        "target": "step3",
                        "label": "Contract / Allowance Context",
                    },
                    {
                        "source": "step3",
                        "target": "step4",
                        "label": "Rated Charge Data",
                    },
                ],
            }

        # 6. Architecture fallback for integration-related requests.
        if (
            "architecture" in q_lower
            or "landscape" in q_lower
            or "integration" in q_lower
            or visual_type == "architecture"
        ):
            return {
                "type": "architecture",
                "title": (
                    f"System Architecture: {subject.title()}"
                ),
                "caption": (
                    f"Enterprise architectural components for "
                    f"{subject}. AI-generated illustration - "
                    "not an SAP screenshot."
                ),
                "groups": [
                    {
                        "id": "channel_layer",
                        "title": "Omnichannel Engagement",
                        "color": "#1e3a5f",
                        "nodes": [
                            {
                                "id": "portal",
                                "title": (
                                    "Self-Service Portal / E-Commerce"
                                ),
                                "component": "Fiori / Web",
                            },
                            {
                                "id": "som_crm",
                                "title": (
                                    "Subscription Order Management"
                                ),
                                "component": "S/4HANA SOM",
                            },
                        ],
                    },
                    {
                        "id": "rating_layer",
                        "title": "Real-Time Monetization Engine",
                        "color": "#0d9488",
                        "nodes": [
                            {
                                "id": "cc_rating",
                                "title": (
                                    "SAP Convergent Charging (CC)"
                                ),
                                "component": "Core Server",
                            },
                            {
                                "id": "allowance",
                                "title": "Allowance & Balance Store",
                                "component": "CC Database",
                            },
                        ],
                    },
                    {
                        "id": "financial_layer",
                        "title": "Receivables & General Ledger",
                        "color": "#2563eb",
                        "nodes": [
                            {
                                "id": "ci_engine",
                                "title": (
                                    "SAP Convergent Invoicing (CI)"
                                ),
                                "component": "S/4HANA",
                            },
                            {
                                "id": "fica_ledger",
                                "title": (
                                    "Contract Accounting (FI-CA)"
                                ),
                                "component": "Subledger",
                            },
                        ],
                    },
                ],
                "edges": [
                    {
                        "source": "som_crm",
                        "target": "cc_rating",
                        "label": "ODI Contract Sync",
                    },
                    {
                        "source": "cc_rating",
                        "target": "ci_engine",
                        "label": "Billable Items",
                    },
                    {
                        "source": "ci_engine",
                        "target": "fica_ledger",
                        "label": "Open Items / Reconciliation",
                    },
                ],
            }

        # 7. Comparison fallback.
        if (
            visual_type == "comparison"
            or "compare" in q_lower
            or "difference" in q_lower
        ):
            return {
                "type": "comparison",
                "title": (
                    f"Structural Comparison: {subject.title()}"
                ),
                "caption": (
                    "Comparative architectural breakdown of "
                    "components. AI-generated illustration - "
                    "not an SAP screenshot."
                ),
                "columns": [
                    {
                        "header": "Component A (e.g., CI)",
                        "items": [
                            "Aggregates high-volume billable items",
                            "Handles partner settlement and "
                            "complex invoice layout",
                            "Generates legal invoice document",
                        ],
                    },
                    {
                        "header": "Component B (e.g., FI-CA)",
                        "items": [
                            "High-volume subledger accounting",
                            "Manages payments, clearing, dunning, "
                            "and returns",
                            "Summarized reconciliation postings "
                            "to General Ledger",
                        ],
                    },
                ],
            }

        # 8. Troubleshooting fallback.
        if (
            visual_type == "decision_tree"
            or "troubleshoot" in q_lower
            or "error" in q_lower
        ):
            return {
                "type": "decision_tree",
                "title": (
                    f"Resolution Decision Tree: {subject.title()}"
                ),
                "caption": (
                    "Decision pathways and verification criteria. "
                    "AI-generated illustration - not an SAP screenshot."
                ),
                "root_question": (
                    "Does the document exist in the initial stage?"
                ),
                "branches": [
                    {
                        "condition": "Yes (Document Found)",
                        "action": (
                            "Inspect processing status code and "
                            "application logs in SLG1"
                        ),
                        "status": "PASS",
                    },
                    {
                        "condition": "No (Missing Document)",
                        "action": (
                            "Check interface queue monitor SMQ1/SMQ2 "
                            "for backlog or RFC failure"
                        ),
                        "status": "FAIL",
                    },
                ],
            }

        # 9. Default structured process flow.
        return {
            "type": "flow_diagram",
            "title": f"Process Flow: {subject.title()}",
            "caption": (
                f"Structured workflow for {subject}. "
                "AI-generated illustration - not an SAP screenshot."
            ),
            "nodes": [
                {
                    "id": "n1",
                    "title": "Initialization & Trigger",
                    "description": (
                        f"Triggering condition for {subject}"
                    ),
                    "component": "System Input",
                },
                {
                    "id": "n2",
                    "title": "Processing & Business Logic",
                    "description": (
                        "Validation against applicable configuration "
                        "and business rules"
                    ),
                    "component": "Core Logic",
                },
                {
                    "id": "n3",
                    "title": "Final Output & Posting",
                    "description": (
                        "Target document generation and applicable "
                        "accounting update"
                    ),
                    "component": "Output",
                },
            ],
            "edges": [
                {
                    "source": "n1",
                    "target": "n2",
                    "label": "Validates",
                },
                {
                    "source": "n2",
                    "target": "n3",
                    "label": "Generates",
                },
            ],
        }

    def _simplify_spec(
        self,
        original_spec: Dict[str, Any],
        corpus: str,
    ) -> Dict[str, Any]:
        """Create a simplified revision of an existing diagram."""
        spec = json.loads(json.dumps(original_spec))

        spec["title"] = (
            f"Simplified: {spec.get('title', 'Process Flow')}"
        )

        spec["caption"] = (
            "Simplified diagram layout with core steps. "
            "AI-generated illustration - not an SAP screenshot."
        )

        # Keep fewer nodes and simplify the connections.
        if (
            "nodes" in spec
            and isinstance(spec["nodes"], list)
        ):
            nodes = spec["nodes"]

            if len(nodes) > 3:
                kept = [
                    nodes[0],
                    nodes[len(nodes) // 2],
                    nodes[-1],
                ]

                spec["nodes"] = kept

                spec["edges"] = [
                    {
                        "source": kept[0]["id"],
                        "target": kept[1]["id"],
                        "label": "Next",
                    },
                    {
                        "source": kept[1]["id"],
                        "target": kept[2]["id"],
                        "label": "Complete",
                    },
                ]

        return sanitize_diagram_spec(spec, corpus)


visual_planner = VisualPlanner()
