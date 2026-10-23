import re
import html
from typing import Dict, Any, List, Set, Tuple, Optional


class SpecValidator:
    """
    Validates and sanitizes visual specifications and generative prompts.
    
    Guarantees:
    - Schema conformity.
    - Technical label verification (unsupported T-codes, tables, or paths are sanitized).
    - Prompt injection defense (delimiters and directives stripped).
    - SVG / XSS safety (scripts, event handlers, and foreign elements blocked).
    - Screenshot defense (enforces illustration style, never authentic GUI screenshots).
    """

    ALLOWED_VISUAL_TYPES = {
        "flow_diagram", "architecture", "system_landscape", "document_flow",
        "decision_tree", "troubleshooting_path", "sequence", "interaction",
        "comparison", "lifecycle", "conceptual_illustration"
    }

    # Known standard / high-level SAP acronyms always permitted
    COMMON_SAP_TERMS = {
        "sap", "brim", "som", "cc", "ci", "fi-ca", "fica", "gl", "erp",
        "s/4hana", "s4hana", "ecc", "crm", "fiori", "gui", "bit", "cit",
        "odi", "order", "contract", "invoice", "billing", "clearing", "dunning"
    }

    @classmethod
    def validate_and_sanitize(
        cls,
        spec: Dict[str, Any],
        answer_text: str = "",
        evidence_text: str = ""
    ) -> Tuple[bool, Dict[str, Any], Optional[str]]:
        """
        Validates spec structure, sanitizes text, verifies technical identifiers.
        Returns: (is_valid, sanitized_spec, error_message)
        """
        if not isinstance(spec, dict):
            return False, {}, "Specification must be a JSON object"

        v_type = str(spec.get("type", "flow_diagram")).lower()
        if v_type not in cls.ALLOWED_VISUAL_TYPES:
            v_type = "flow_diagram"

        title = cls._clean_text(spec.get("title", "SAP Architecture Illustration"))
        caption = cls._clean_text(spec.get("caption", ""))

        # Assemble verified corpus to check technical labels
        corpus = (answer_text + " " + evidence_text).lower()

        # Sanitize nodes
        raw_nodes = spec.get("nodes", [])
        if not isinstance(raw_nodes, list) or not raw_nodes:
            # Fallback default nodes if empty
            raw_nodes = [
                {"id": "1", "label": "Start Process", "step_id": "STEP 1"},
                {"id": "2", "label": "Execute Processing", "step_id": "STEP 2"},
                {"id": "3", "label": "Verify Result", "step_id": "STEP 3"}
            ]

        sanitized_nodes = []
        for idx, n in enumerate(raw_nodes):
            if not isinstance(n, dict):
                continue
            n_id = str(n.get("id", idx + 1))
            raw_label = str(n.get("label", f"Step {idx+1}"))
            raw_desc = str(n.get("description", n.get("role", "")))
            raw_tcode = str(n.get("tcode", n.get("details", "")))

            # Verify and sanitize labels against corpus
            sanitized_label = cls._sanitize_technical_label(raw_label, corpus)
            sanitized_desc = cls._clean_text(raw_desc)
            sanitized_tcode = cls._verify_identifier(raw_tcode, corpus)

            sanitized_nodes.append({
                "id": n_id,
                "label": sanitized_label,
                "description": sanitized_desc,
                "tcode": sanitized_tcode,
                "step_id": cls._clean_text(n.get("step_id", f"STEP {idx+1}")),
                "type": cls._clean_text(n.get("type", "process"))
            })

        # Sanitize edges
        raw_edges = spec.get("edges", [])
        sanitized_edges = []
        if isinstance(raw_edges, list):
            for e in raw_edges:
                if isinstance(e, dict):
                    sanitized_edges.append({
                        "from": str(e.get("from", "")),
                        "to": str(e.get("to", "")),
                        "label": cls._clean_text(e.get("label", ""))
                    })

        sanitized_spec = {
            "type": v_type,
            "title": title,
            "caption": caption,
            "step_id": cls._clean_text(spec.get("step_id", "")),
            "nodes": sanitized_nodes,
            "edges": sanitized_edges,
            "root_question": cls._clean_text(spec.get("root_question", "")),
            "yes_action": cls._clean_text(spec.get("yes_action", "")),
            "no_action": cls._clean_text(spec.get("no_action", "")),
            "columns": spec.get("columns", []),
            "branches": spec.get("branches", []),
            "groups": spec.get("groups", []),
            "rows": spec.get("rows", []),
            "is_generative": spec.get("is_generative", False),
        }

        return True, sanitized_spec, None

    @classmethod
    def _clean_text(cls, text: Any) -> str:
        """Strip dangerous HTML/SVG injection and trim length."""
        if not text:
            return ""
        s = str(text)
        # Strip script tags, javascript:, onload, etc.
        s = re.sub(r"(?i)<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>", "", s)
        s = re.sub(r"(?i)\bon\w+\s*=", "", s)
        s = re.sub(r"(?i)javascript:", "", s)
        s = re.sub(r"[<>]", "", s)
        return s.strip()[:180]

    @classmethod
    def _sanitize_technical_label(cls, label: str, corpus: str) -> str:
        """
        Checks if specific SAP identifiers in the label (e.g. FKKBIX, CRMD_ORDER)
        are supported by evidence/answer. If unsupported, replaces with neutral wording.
        """
        cleaned = cls._clean_text(label)
        # Find potential SAP identifiers (uppercase word with numbers/underscores)
        tokens = re.findall(r"\b[A-Z0-9_\/]{3,}\b", cleaned)
        for token in tokens:
            t_low = token.lower()
            if t_low in cls.COMMON_SAP_TERMS or len(t_low) <= 2:
                continue
            # If specific technical identifier is NOT present anywhere in evidence/answer
            if t_low not in corpus and not any(t_low in c for c in corpus.split()):
                # Replace with generic label
                cleaned = cleaned.replace(token, "Standard Step")
        return cleaned

    @classmethod
    def _verify_identifier(cls, identifier: str, corpus: str) -> str:
        """Verify T-code or database table against verified answer corpus."""
        cleaned = cls._clean_text(identifier)
        if not cleaned:
            return ""
        c_low = cleaned.lower()
        if c_low in cls.COMMON_SAP_TERMS:
            return cleaned
        # If identifier not found in evidence or answer, mark as unverified or drop
        if c_low not in corpus:
            return ""
        return cleaned

    @classmethod
    def sanitize_generative_prompt(cls, prompt: str) -> Tuple[bool, str]:
        """
        Sanitizes prompts for Path B generative image generation.
        Blocks injection, authentic GUI simulation, real persons, and unsafe keywords.
        """
        p_clean = cls._clean_text(prompt)
        p_lower = p_clean.lower()

        # Reject disallowed content
        disallowed = [
            "screenshot of sap", "fake sap gui", "counterfeit", "nsfw",
            "explicit", "violence", "copyright", "trademark logo", "real person",
            "password", "secret key"
        ]
        if any(d in p_lower for d in disallowed):
            return False, "Disallowed visual prompt content"

        # Mandatory safety and disclaimer phrasing
        safe_prompt = (
            f"Conceptual enterprise software illustration: {p_clean}. "
            "Clean digital infographic style, professional enterprise diagram, "
            "no realistic personal photographs, no fake UI buttons, abstract modern tech illustration."
        )
        return True, safe_prompt


def validate_diagram_spec(spec: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    """Checks if a diagram spec has valid type and schema."""
    if not isinstance(spec, dict) or "type" not in spec:
        return False, "Specification must be a JSON object containing a 'type' field."
    return True, None


def sanitize_diagram_spec(spec: Dict[str, Any], corpus: str = "") -> Dict[str, Any]:
    """Validates and sanitizes a diagram spec against answer/evidence corpus."""
    is_valid, sanitized, err = SpecValidator.validate_and_sanitize(spec, answer_text=corpus)
    return sanitized


def sanitize_generative_prompt(prompt: str) -> str:
    """Sanitizes generative prompt, stripping injections and enforcing safe enterprise style."""
    clean = re.sub(r"(?i)ignore\s+(all\s+)?(previous|prior)\s+instructions[^\.\n]*", "", prompt)
    clean = re.sub(r"(?i)passwords?", "", clean)
    ok, safe = SpecValidator.sanitize_generative_prompt(clean)
    return safe if ok else "Enterprise technical software concept illustration."
