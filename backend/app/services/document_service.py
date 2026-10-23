
import re
import hashlib
from pathlib import Path
from typing import List, Dict, Any, Optional

import pymupdf
from backend.app.config import settings


class DocumentService:
    # Curated metadata lookup for known SAP publications
    SAP_DOC_METADATA = {
        "pdfdownload.pdf": {
            "title": "SAP S/4HANA Subscription Order Management (SOM) Guide",
            "module": "SOM / BRIM",
            "product": "SAP S/4HANA BRIM",
        },
        "SAP CC.pdf": {
            "title": "SAP Convergent Charging (CC) Implementation Guide",
            "module": "CC / BRIM",
            "product": "SAP Convergent Charging",
        },
        "SAP CI1.pdf": {
            "title": "SAP Cloud Integration & Convergent Invoicing Guide (Part 1)",
            "module": "CI / BRIM",
            "product": "SAP Convergent Invoicing",
        },
        "SAP CI2.pdf": {
            "title": "SAP Cloud Integration & Convergent Invoicing Guide (Part 2)",
            "module": "CI / BRIM",
            "product": "SAP Convergent Invoicing",
        },
        "SAP CI3.pdf": {
            "title": "SAP Cloud Integration & Convergent Invoicing Guide (Part 3)",
            "module": "CI / BRIM",
            "product": "SAP Convergent Invoicing",
        },
        "SAP CI4.pdf": {
            "title": "SAP Cloud Integration & Convergent Invoicing Guide (Part 4)",
            "module": "CI / BRIM",
            "product": "SAP Convergent Invoicing",
        },
        "SAP FI-CA.pdf": {
            "title": "SAP Contract Accounts Receivable and Payable (FI-CA) Guide",
            "module": "FI-CA / BRIM",
            "product": "SAP FI-CA",
        },
        "2020_S4H_BRIM_SOM_Device_as_a_Service.pdf": {
            "title": "SAP S/4HANA BRIM SOM: Device as a Service (DaaS) Architecture",
            "module": "SOM / BRIM",
            "product": "SAP S/4HANA BRIM",
        },
        "Authorizations-in-S4-HANA-and-Fiori.pdf": {
            "title": "Authorizations and Security Architecture in SAP S/4HANA and Fiori",
            "module": "Security / Basis / Fiori",
            "product": "SAP S/4HANA",
        },
        "Billing_and_Revenue_Innovation_Management.pdf": {
            "title": "SAP Billing and Revenue Innovation Management (BRIM) Solution Overview",
            "module": "BRIM Architecture",
            "product": "SAP BRIM",
        },
        "BR234_EN_SOM 2.pdf": {
            "title": "BR234: SAP S/4HANA Subscription Order Management (SOM) Course Handbook",
            "module": "SOM / BRIM",
            "product": "SAP S/4HANA BRIM",
        },
        "BRIM Q Bank.pdf": {
            "title": "SAP BRIM Certification and Technical Interview Question Bank",
            "module": "BRIM Architecture",
            "product": "SAP BRIM",
        },
        "BRIM_AC240_EN_Col16.pdf": {
            "title": "AC240: SAP BRIM Solution Overview & End-to-End Integration Handbook",
            "module": "BRIM Core",
            "product": "SAP BRIM",
        },
        "Budget billing.pdf": {
            "title": "SAP FI-CA & BRIM Budget Billing Plan Configuration Guide",
            "module": "FI-CA / BRIM",
            "product": "SAP FI-CA",
        },
        "E_Book_ABAP_RESTful_Programming_Model_2020_Rel_NW_wwwERPExamsCom.pdf": {
            "title": "ABAP RESTful Application Programming Model (RAP) Reference Guide",
            "module": "ABAP RAP / Development",
            "product": "SAP S/4HANA & BTP",
        },
        "RAR Contract Reversal Process.pdf": {
            "title": "SAP Revenue Accounting and Reporting (RAR) Contract Reversal Process",
            "module": "RAR / Revenue Accounting",
            "product": "SAP S/4HANA RAR",
        },
        "SAP BRIM Press Book 2nd Edition - Expertsoft.pdf": {
            "title": "SAP Press: SAP Billing and Revenue Innovation Management (2nd Edition)",
            "module": "BRIM End-to-End",
            "product": "SAP BRIM",
        },
        "SAP Revenue Recognition (RAR) Processing Flow, Exemptions, Reversals & System Integration.pdf": {
            "title": "SAP RAR Revenue Recognition Processing Flow, Exemptions, & System Integration",
            "module": "RAR / Revenue Accounting",
            "product": "SAP S/4HANA RAR",
        },
        "SAP-PRESS-Catalog-Shop.pdf": {
            "title": "SAP Press Technical & Architecture Publication Catalog",
            "module": "SAP Reference",
            "product": "SAP Ecosystem",
        },
        "SIMPL_OP1709.pdf": {
            "title": "Simplification List for SAP S/4HANA Enterprise Management",
            "module": "S/4HANA Transition",
            "product": "SAP S/4HANA",
        },
        "mg.pdf": {
            "title": "SAP BRIM Master Guide: Solution Landscapes & Implementation Strategy",
            "module": "BRIM Architecture",
            "product": "SAP BRIM",
        },
        "SAP_BRIM_CC_Convergent_Charging_Advanced_Architecture.pdf": {
            "title": "SAP Convergent Charging (CC) Advanced Architecture & Implementation Guide",
            "module": "CC / BRIM",
            "product": "SAP Convergent Charging",
        },
        "SAP_BRIM_FICA_Contract_Accounts_Master_Handbook.pdf": {
            "title": "SAP Contract Accounts Receivable and Payable (FI-CA) Master Configuration & Architecture Guide",
            "module": "FI-CA / BRIM",
            "product": "SAP FI-CA",
        },
        "SAP_BRIM_Convergent_Invoicing_CIT_BIT_Master_Architecture.pdf": {
            "title": "SAP Convergent Invoicing (CI) Consumption & Billable Item Management Master Guide",
            "module": "CI / BRIM",
            "product": "SAP Convergent Invoicing",
        },
        "SAP_BRIM_SOM_Subscription_Order_Management_Master_Guide.pdf": {
            "title": "SAP Subscription Order Management (SOM) Master Configuration & Order Distribution Guide",
            "module": "SOM / BRIM",
            "product": "SAP S/4HANA BRIM",
        },
        "SAP_BRIM_End_to_End_Integration_and_SPRO_Cookbook.pdf": {
            "title": "SAP BRIM End-to-End Integration, SPRO Customizing Cookbook & War-Room Guide",
            "module": "BRIM End-to-End",
            "product": "SAP BRIM",
        },
    }

    @staticmethod
    def get_document_info(
        filename: str,
        sample_text: str = "",
    ) -> Dict[str, str]:
        """Derive title, module, and product from lookup or content."""
        if filename in DocumentService.SAP_DOC_METADATA:
            return DocumentService.SAP_DOC_METADATA[filename]

        lower_fn = filename.lower()
        lower_txt = sample_text[:1000].lower() if sample_text else ""
        combined = f"{lower_fn} {lower_txt}"

        module = "General SAP"
        product = "SAP ERP"

        if "som" in combined or "subscription" in combined:
            module, product = "SOM / BRIM", "SAP S/4HANA BRIM"
        elif (
            "fi-ca" in combined
            or "fica" in combined
            or "contract accounts" in combined
        ):
            module, product = "FI-CA / BRIM", "SAP FI-CA"
        elif "convergent charging" in combined or " cc " in combined:
            module, product = "CC / BRIM", "SAP Convergent Charging"
        elif "convergent invoicing" in combined or " ci " in combined:
            module, product = "CI / BRIM", "SAP Convergent Invoicing"
        elif "rar" in combined or "revenue accounting" in combined:
            module, product = "RAR / Revenue Accounting", "SAP S/4HANA RAR"
        elif "brim" in combined or "billing and revenue" in combined:
            module, product = "BRIM Architecture", "SAP BRIM"
        elif (
            "fiori" in combined
            or "authorization" in combined
            or "security" in combined
        ):
            module, product = "Security / Fiori", "SAP S/4HANA"
        elif "abap" in combined or "rap" in combined:
            module, product = "ABAP RAP", "SAP S/4HANA & BTP"
        elif "s/4" in combined or "s4hana" in combined:
            module, product = "S/4HANA Core", "SAP S/4HANA"

        clean_title = re.sub(r"[\-_]+", " ", Path(filename).stem).strip()
        clean_title = re.sub(r"\s+", " ", clean_title).title()

        return {
            "title": clean_title,
            "module": module,
            "product": product,
        }

    @staticmethod
    def compute_file_hash(file_path: Path) -> str:
        """Compute a SHA-256 hash for idempotency."""
        hasher = hashlib.sha256()
        with open(file_path, "rb") as file:
            while chunk := file.read(65536):
                hasher.update(chunk)
        return hasher.hexdigest()

    @staticmethod
    def clean_text(text: str) -> str:
        """Clean extracted text without removing technical content."""
        if not text:
            return ""

        text = text.replace("\x00", "")
        text = re.sub(r"[\ue000-\uf8ff\ufffd]", " ", text)
        text = re.sub(
            r"Warning\s+This document has been generated from SAP Help Portal[^\n]*",
            "",
            text,
            flags=re.IGNORECASE,
        )
        text = re.sub(
            r"Original content:\s*https?://help\.sap\.com[^\n]*",
            "",
            text,
            flags=re.IGNORECASE,
        )
        text = re.sub(
            r"Generated on:\s*\d{4}-\d{2}-\d{2}[^\n]*",
            "",
            text,
            flags=re.IGNORECASE,
        )
        text = re.sub(r"(?i)\bPage\s+\d+(\s+of\s+\d+)?\b", "", text)
        text = re.sub(
            r"(?i)SAP S/4HANA\s*\|\s*\d{4}[^\n]*",
            "",
            text,
        )
        text = re.sub(r"\r\n|\r", "\n", text)
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip().replace("\x00", "")

    @staticmethod
    def extract_pdf_pages(file_path: Path) -> List[Dict[str, Any]]:
        """Extract text and track section headings across PDF pages."""
        pages_data = []
        doc = pymupdf.open(str(file_path))
        active_section = "Overview"
        active_subsection = ""

        try:
            for page_idx in range(len(doc)):
                page = doc[page_idx]
                page_number = page_idx + 1
                raw_text = page.get_text("text") or ""
                cleaned_text = DocumentService.clean_text(raw_text)

                headings = []
                lines = [
                    line.strip()
                    for line in cleaned_text.split("\n")
                    if line.strip()
                ]

                for line in lines:
                    if (
                        re.match(
                            r"^(?:(?:Section|Chapter)\s+\d+(?:\.\d+)*|\d+(?:\.\d+)*\s+[A-Z0-9].*|\d+\s+[A-Z][A-Za-z0-9\s\-_/:]{3,50})$",
                            line,
                        )
                        and len(line) < 70
                    ):
                        headings.append(line)
                    elif (
                        len(line) < 45
                        and line.isupper()
                        and not line.startswith("PAGE")
                    ):
                        headings.append(line.title())

                if headings:
                    active_section = headings[0]
                    active_subsection = headings[1] if len(headings) > 1 else ""

                pages_data.append({
                    "page_number": page_number,
                    "text": cleaned_text,
                    "headings": headings,
                    "active_section": active_section,
                    "active_subsection": active_subsection,
                })
        finally:
            doc.close()

        return pages_data

    @staticmethod
    def extract_text_file(file_path: Path) -> List[Dict[str, Any]]:
        """Extract text or Markdown, segmenting on Markdown headings."""
        with open(file_path, "r", encoding="utf-8", errors="replace") as file:
            raw_text = file.read().replace("\x00", "")

        cleaned = DocumentService.clean_text(raw_text)
        if not cleaned:
            return []

        sections = re.split(r"\n(?=#{1,2}\s+)", cleaned)
        pages_data = []

        for idx, section in enumerate(sections, start=1):
            section_clean = section.strip().replace("\x00", "")
            if not section_clean:
                continue

            first_line = section_clean.split("\n")[0].strip("# ").strip()
            heading = (
                first_line
                if first_line and len(first_line) < 80
                else f"Section {idx}"
            )

            pages_data.append({
                "page_number": idx,
                "text": section_clean,
                "headings": [heading],
                "active_section": heading,
                "active_subsection": "",
            })

        return pages_data

    @staticmethod
    def extract_docx_file(file_path: Path) -> List[Dict[str, Any]]:
        """Extract text from DOCX files if python-docx is installed."""
        try:
            import docx

            doc = docx.Document(str(file_path))
            full_text = "\n\n".join(
                paragraph.text
                for paragraph in doc.paragraphs
                if paragraph.text.strip()
            ).replace("\x00", "")

            cleaned = DocumentService.clean_text(full_text)
            if not cleaned:
                return []

            sections = re.split(r"\n(?=#{1,2}\s+)", cleaned)
            pages_data = []

            for idx, section in enumerate(sections, start=1):
                section_clean = section.strip()
                if not section_clean:
                    continue

                first_line = section_clean.split("\n")[0].strip("# ").strip()
                heading = (
                    first_line
                    if first_line and len(first_line) < 80
                    else f"Section {idx}"
                )

                pages_data.append({
                    "page_number": idx,
                    "text": section_clean,
                    "headings": [heading],
                    "active_section": heading,
                    "active_subsection": "",
                })

            return pages_data
        except ImportError:
            return []
        except Exception:
            return []

    @staticmethod
    def extract_document_pages(file_path: Path) -> List[Dict[str, Any]]:
        """Extract pages from supported document formats."""
        suffix = file_path.suffix.lower()

        if suffix == ".pdf":
            return DocumentService.extract_pdf_pages(file_path)
        if suffix in [".txt", ".md", ".markdown"]:
            return DocumentService.extract_text_file(file_path)
        if suffix == ".docx":
            return DocumentService.extract_docx_file(file_path)

        try:
            return DocumentService.extract_text_file(file_path)
        except Exception:
            return []

    @staticmethod
    def _detect_chunk_type(text: str) -> str:
        """Determine the semantic archetype of a chunk."""
        if re.search(
            r"(?:Step\s+\d+|\bProcedure\b|\bPrerequisites\b|\bHow\s+to\b|\n\s*\d+\.\s+[A-Z])",
            text,
            re.IGNORECASE,
        ):
            return "procedure"

        if re.search(
            r"(?:\|.*\|.*\||\bTable\s+\d+|\bField\s+Name\b.*\bDescription\b)",
            text,
            re.IGNORECASE,
        ):
            return "table"

        if re.search(
            r"(?:\bOverview\b|\bIntroduction\b|\bArchitecture\b|\bSummary\b)",
            text,
            re.IGNORECASE,
        ):
            return "overview"

        return "concept"

    @staticmethod
    def chunk_page_text(
        text: str,
        page_number: int,
        document_name: str,
        active_section: str,
        active_subsection: str = "",
        target_chunk_size: Optional[int] = None,
        chunk_overlap: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Structure-aware SAP documentation chunker.

        Enforces a hard maximum chunk length and uses configured overlap.
        Prefers logical boundaries without exceeding the configured limit.
        """
        chunk_size = (
            target_chunk_size
            if target_chunk_size is not None
            else getattr(settings, "CHUNK_SIZE", 1200)
        )
        overlap = (
            chunk_overlap
            if chunk_overlap is not None
            else getattr(settings, "CHUNK_OVERLAP", 200)
        )

        if chunk_size <= 0:
            raise ValueError("CHUNK_SIZE must be greater than zero")
        if overlap < 0 or overlap >= chunk_size:
            raise ValueError(
                "CHUNK_OVERLAP must be >= 0 and smaller than CHUNK_SIZE"
            )

        if not text:
            return []

        cleaned = text.strip().replace("\x00", "")
        if len(cleaned) < 30:
            return []

        doc_info = DocumentService.get_document_info(
            document_name,
            sample_text=cleaned,
        )

        def build_chunk(chunk_text: str, index: int) -> Dict[str, Any]:
            chunk_type = DocumentService._detect_chunk_type(chunk_text)

            return {
                "chunk_index": index,
                "page_number": page_number,
                "document_name": document_name,
                "section": active_section,
                "subsection": active_subsection,
                "chunk_text": chunk_text,
                "chunk_type": chunk_type,
                "metadata": {
                    "document_title": doc_info["title"],
                    "filename": document_name,
                    "page_number": page_number,
                    "section": active_section,
                    "subsection": active_subsection,
                    "chunk_type": chunk_type,
                    "product": doc_info["product"],
                    "module": doc_info["module"],
                    "source": "knowledge_base",
                    "char_length": len(chunk_text),
                    "has_procedure": chunk_type == "procedure",
                    "has_table": chunk_type == "table",
                },
            }

        # Keep a page intact only when it fits the strict maximum.
        if len(cleaned) <= chunk_size:
            return [build_chunk(cleaned, 0)]

        chunks: List[Dict[str, Any]] = []
        text_length = len(cleaned)
        start = 0
        chunk_index = 0

        while start < text_length:
            hard_end = min(start + chunk_size, text_length)
            end = hard_end

            if hard_end < text_length:
                search_start = start + min(300, chunk_size // 2)

                # 1. Paragraph boundary
                paragraph_break = cleaned.rfind(
                    "\n\n", search_start, hard_end
                )

                if paragraph_break != -1:
                    end = paragraph_break
                else:
                    # 2. Numbered steps and list boundaries
                    matches = list(
                        re.finditer(
                            r"\n(?:\d+\.|\-|\*|Step\s+\d+:?)\s+",
                            cleaned[search_start:hard_end],
                            re.IGNORECASE,
                        )
                    )

                    if matches:
                        end = search_start + matches[-1].start()
                    else:
                        # 3. Sentence boundary
                        sentence_break = max(
                            cleaned.rfind(". ", search_start, hard_end),
                            cleaned.rfind(".\n", search_start, hard_end),
                            cleaned.rfind("? ", search_start, hard_end),
                            cleaned.rfind("! ", search_start, hard_end),
                        )

                        if sentence_break != -1:
                            end = sentence_break + 1
                        else:
                            # 4. Line boundary
                            line_break = cleaned.rfind(
                                "\n", search_start, hard_end
                            )
                            if line_break != -1:
                                end = line_break

            # Never exceed the hard maximum.
            end = min(end, hard_end)

            # Always advance, even if no suitable boundary is found.
            if end <= start:
                end = hard_end

            chunk_text = cleaned[start:end].strip()

            if chunk_text:
                if len(chunk_text) > chunk_size:
                    raise RuntimeError(
                        "Generated chunk exceeds configured chunk size"
                    )

                chunks.append(build_chunk(chunk_text, chunk_index))
                chunk_index += 1

            if end >= text_length:
                break

            # Apply overlap while ensuring the next start moves forward.
            start = max(end - overlap, start + 1)

        return chunks


document_service = DocumentService()
