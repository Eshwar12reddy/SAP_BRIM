import html
import re
from typing import Dict, Any, List, Optional, Tuple


class SapGuiSvgBuilder:
    """
    Deterministic SVG builder for SAP BRIM Visual Step-by-Step Troubleshooting:
    1. Simplified SAP GUI screen window mockup with:
       - Window title bar: "Step N · <transaction code> · <screen name>"
       - Menu/Command field showing the transaction code
       - Table/form fields with realistic sample values (marked as examples)
       - Ring around the exact target field/button/row
       - Numbered callout circles (1, 2, 3) with short instruction (max 8 words)
       - Red (error), Green (success), Gray (neutral)
       - Illustrative mockup disclaimer
    2. BRIM flow overview SVG:
       - billable item > billing document > invoicing document > invoice
       - Affected stage red, successful stages green, neutral stages gray
    3. Verification screen mockup:
       - Window title bar: "Verification · <transaction code> · <screen name>"
       - Green success status and resolved values
    """

    COLORS = {
        "bg": "#0B0F19",
        "card_bg": "#151D30",
        "card_border": "#283553",
        "window_header": "#1E293B",
        "sap_blue": "#0A6ED1",
        "sap_header": "#004085",
        "text_primary": "#F8FAFC",
        "text_secondary": "#94A3B8",
        "text_muted": "#64748B",
        "text_field_bg": "#0F172A",
        "field_border": "#334155",
        "callout_orange": "#F59E0B",
        "ring_red": "#EF4444",
        "ring_green": "#10B981",
        "neutral_gray": "#64748B",
        "success_green": "#10B981",
        "error_red": "#EF4444",
        "pending_gray": "#475569",
    }

    @staticmethod
    def _escape(text: Any) -> str:
        return html.escape(str(text or ""), quote=True)

    @classmethod
    def build_brim_flow_overview_svg(cls, affected_stage: str = "billing_document") -> str:
        """
        Builds the BRIM Flow Overview SVG:
        billable item > billing document > invoicing document > invoice
        Affected stage red, successful stages green, downstream stages gray.
        """
        stages = [
            ("billable_item", "1. Billable Item (BIT)", "DFKKBIXBIT0 / FKKBIX_BIT_DISPLAY"),
            ("billing_document", "2. Billing Document", "DFKKBIX_BILLDOC_H / FKKBIX_BILL_M"),
            ("invoicing_document", "3. Invoicing Document", "DFKKINVDOC_H / FKKINV_M"),
            ("invoice", "4. FI-CA Invoice / Post", "DFKKOP / FPL9"),
        ]

        # Determine stage index
        aff_lower = affected_stage.lower()
        aff_idx = 1  # default to billing document
        for i, (key, _, _) in enumerate(stages):
            if key in aff_lower or aff_lower in key:
                aff_idx = i
                break
        if "bit" in aff_lower or "item" in aff_lower:
            aff_idx = 0
        elif "bill" in aff_lower:
            aff_idx = 1
        elif "inv" in aff_lower and "fica" not in aff_lower:
            aff_idx = 2
        elif "fica" in aff_lower or "account" in aff_lower or "clear" in aff_lower or "lock" in aff_lower:
            aff_idx = 3

        width = 680
        height = 180

        svg_parts = [
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="100%" height="100%">',
            f'<rect width="{width}" height="{height}" rx="10" fill="{cls.COLORS["bg"]}" stroke="{cls.COLORS["card_border"]}" stroke-width="1.5"/>',
            f'<text x="24" y="28" fill="{cls.COLORS["text_primary"]}" font-family="system-ui, sans-serif" font-size="13" font-weight="700">SAP BRIM Convergent Invoicing Flow Overview</text>',
            f'<text x="{width - 24}" y="28" fill="{cls.COLORS["text_muted"]}" font-family="system-ui, sans-serif" font-size="10" text-anchor="end">Illustrative Process Map</text>',
            f'<line x1="24" y1="40" x2="{width - 24}" y2="40" stroke="{cls.COLORS["card_border"]}" stroke-width="1"/>',
        ]

        stage_w = 135
        stage_h = 75
        start_x = 28
        spacing_x = 160
        y = 58

        for idx, (key, title, subtitle) in enumerate(stages):
            x = start_x + idx * spacing_x

            # Determine color state: Red = error, Green = success, Gray = neutral
            if idx < aff_idx:
                status_color = cls.COLORS["success_green"]
                status_text = "COMPLETED"
                status_bg = "#064E3B"
            elif idx == aff_idx:
                status_color = cls.COLORS["error_red"]
                status_text = "AFFECTED (ISSUE)"
                status_bg = "#4C0519"
            else:
                status_color = cls.COLORS["pending_gray"]
                status_text = "PENDING"
                status_bg = "#1E293B"

            # Connecting arrow
            if idx > 0:
                arrow_start = x - 25
                arrow_end = x - 5
                svg_parts.append(
                    f'<line x1="{arrow_start}" y1="{y + stage_h//2}" x2="{arrow_end}" y2="{y + stage_h//2}" '
                    f'stroke="{cls.COLORS["text_secondary"]}" stroke-width="2" stroke-dasharray="3,3"/>'
                    f'<polygon points="{arrow_end},{y + stage_h//2 - 4} {arrow_end + 6},{y + stage_h//2} {arrow_end},{y + stage_h//2 + 4}" fill="{cls.COLORS["text_secondary"]}"/>'
                )

            # Stage Box
            svg_parts.append(
                f'<rect x="{x}" y="{y}" width="{stage_w}" height="{stage_h}" rx="6" fill="{cls.COLORS["card_bg"]}" stroke="{status_color}" stroke-width="{2 if idx == aff_idx else 1}"/>'
                f'<rect x="{x}" y="{y}" width="{stage_w}" height="20" rx="6" fill="{status_bg}"/>'
                f'<text x="{x + stage_w//2}" y="{y + 14}" fill="{status_color}" font-family="system-ui, sans-serif" font-size="9" font-weight="700" text-anchor="middle">{status_text}</text>'
                f'<text x="{x + 8}" y="{y + 38}" fill="{cls.COLORS["text_primary"]}" font-family="system-ui, sans-serif" font-size="10.5" font-weight="600">{cls._escape(title)}</text>'
                f'<text x="{x + 8}" y="{y + 54}" fill="{cls.COLORS["text_secondary"]}" font-family="system-ui, sans-serif" font-size="8.5">{cls._escape(subtitle[:24])}</text>'
                f'<text x="{x + 8}" y="{y + 66}" fill="{cls.COLORS["text_muted"]}" font-family="system-ui, sans-serif" font-size="8">{cls._escape(subtitle[24:45])}</text>'
            )

        # Bottom note
        svg_parts.append(
            f'<text x="{width//2}" y="{height - 14}" fill="{cls.COLORS["text_muted"]}" font-family="system-ui, sans-serif" font-size="9.5" text-anchor="middle">'
            f'Red = affected stage with error · Green = successful prior stages · Gray = downstream pending</text>'
        )
        svg_parts.append('</svg>')
        return "\n".join(svg_parts)

    @classmethod
    def build_sap_gui_screen_svg(
        cls,
        step_num: Any = 1,
        tcode: str = "FKKBIX_BIT_DISPLAY",
        screen_name: str = "Display Billable Items",
        fields: Optional[List[Tuple[str, str]]] = None,
        highlight_field: str = "",
        callouts: Optional[List[Tuple[int, str]]] = None,
        is_verification: bool = False,
        status: str = "neutral",
    ) -> str:
        """
        Builds a simplified SAP GUI screen window mockup SVG:
        - Window title bar: "Step N · <tcode> · <screen name>" or "Verification · <tcode> · <screen name>"
        - SAP GUI menu bar, command line box with tcode
        - Fields table with realistic sample values
        - Ring around the highlight_field
        - Numbered callout circles (1, 2, 3) with short instructions (max 8 words)
        - Illustrative mockup disclaimer
        """
        width = 680
        height = 340

        # Step title format: "Step N · <tcode> · <screen name>" or "Verification · <tcode> · <screen name>"
        if is_verification or str(step_num).lower() == "verification":
            header_prefix = "Verification"
            ring_color = cls.COLORS["ring_green"]
            accent_color = cls.COLORS["ring_green"]
        else:
            header_prefix = f"Step {step_num}"
            ring_color = cls.COLORS["ring_red"] if status == "error" else cls.COLORS["callout_orange"]
            accent_color = cls.COLORS["sap_blue"]

        title_bar_text = f"{header_prefix} · {tcode} · {screen_name}"

        # Default fields if none provided
        if not fields:
            fields = [
                ("Contract Account", "10029482 (Example)"),
                ("Billable Item Class", "TEL1 (Voice/SMS)"),
                ("BIT Status", "2 - Billable / Clarification (Example)"),
                ("Source Transaction", "CIT-902148201"),
                ("Target Status", "4 - Billed"),
            ]

        if callouts is None:
            callouts = [(1, "Check BIT Status field")]

        svg_parts = [
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="100%" height="100%">',
            # Window Outer Shell
            f'<rect width="{width}" height="{height}" rx="10" fill="{cls.COLORS["bg"]}" stroke="{cls.COLORS["card_border"]}" stroke-width="1.5"/>',
            
            # Title Bar
            f'<rect width="{width}" height="32" rx="10" fill="{cls.COLORS["window_header"]}"/>',
            f'<rect y="22" width="{width}" height="10" fill="{cls.COLORS["window_header"]}"/>',
            # Window Controls (Minimize, Maximize, Close)
            '<circle cx="20" cy="16" r="4.5" fill="#EF4444"/>',
            '<circle cx="34" cy="16" r="4.5" fill="#F59E0B"/>',
            '<circle cx="48" cy="16" r="4.5" fill="#10B981"/>',
            f'<text x="68" y="21" fill="{cls.COLORS["text_primary"]}" font-family="system-ui, sans-serif" font-size="11.5" font-weight="700">{cls._escape(title_bar_text)}</text>',

            # SAP GUI Menu / Toolbar Strip
            f'<rect y="32" width="{width}" height="28" fill="{cls.COLORS["card_bg"]}" stroke="{cls.COLORS["card_border"]}" stroke-width="1"/>',
            f'<text x="20" y="50" fill="{cls.COLORS["text_secondary"]}" font-family="system-ui, sans-serif" font-size="10.5">Menu   Edit   Goto   Extras   Environment   System   Help</text>',

            # SAP Command Field Box
            f'<rect x="{width - 190}" y="36" width="140" height="20" rx="3" fill="{cls.COLORS["text_field_bg"]}" stroke="{cls.COLORS["field_border"]}" stroke-width="1"/>',
            f'<text x="{width - 182}" y="50" fill="{cls.COLORS["text_primary"]}" font-family="monospace" font-size="10.5">/n{cls._escape(tcode)}</text>',
            f'<rect x="{width - 44}" y="36" width="24" height="20" rx="3" fill="{accent_color}"/>',
            f'<text x="{width - 32}" y="50" fill="#FFFFFF" font-family="system-ui, sans-serif" font-size="11" font-weight="bold" text-anchor="middle">✓</text>',

            # Screen Header / Subtitle
            f'<text x="20" y="82" fill="{cls.COLORS["text_muted"]}" font-family="system-ui, sans-serif" font-size="10" font-weight="600">PROGRAM: SAPL{cls._escape(tcode[:8])} · SCREEN: 1000</text>',
            f'<text x="20" y="100" fill="{cls.COLORS["text_primary"]}" font-family="system-ui, sans-serif" font-size="14" font-weight="700">{cls._escape(screen_name)}</text>',
            f'<line x1="20" y1="108" x2="{width - 20}" y2="108" stroke="{cls.COLORS["card_border"]}" stroke-width="1"/>',
        ]

        # Render Form / Table Fields
        form_x = 24
        form_y = 120
        row_height = 28
        label_width = 170
        input_width = 250

        ring_applied = False
        target_highlight = (highlight_field or "").lower()

        for idx, (f_label, f_val) in enumerate(fields[:5]):
            cur_y = form_y + idx * row_height
            is_target = target_highlight and (target_highlight in f_label.lower() or target_highlight in f_val.lower())
            
            # If no highlight matched and this is the first field, highlight it if not already
            if not target_highlight and idx == 0:
                is_target = True

            # Field Label
            svg_parts.append(
                f'<text x="{form_x}" y="{cur_y + 16}" fill="{cls.COLORS["text_secondary"]}" font-family="system-ui, sans-serif" font-size="11">{cls._escape(f_label)}</text>'
            )

            # Field Input Box
            border_color = ring_color if is_target else cls.COLORS["field_border"]
            stroke_width = 2.5 if is_target else 1
            svg_parts.append(
                f'<rect x="{form_x + label_width}" y="{cur_y}" width="{input_width}" height="22" rx="3" fill="{cls.COLORS["text_field_bg"]}" stroke="{border_color}" stroke-width="{stroke_width}"/>'
                f'<text x="{form_x + label_width + 8}" y="{cur_y + 15}" fill="{cls.COLORS["text_primary"]}" font-family="monospace" font-size="10.5">{cls._escape(f_val)}</text>'
            )

            # Highlight Ring on Target Element
            if is_target and not ring_applied:
                ring_applied = True
                svg_parts.append(
                    f'<rect x="{form_x + label_width - 4}" y="{cur_y - 4}" width="{input_width + 8}" height="30" rx="5" fill="none" stroke="{ring_color}" stroke-width="2" stroke-dasharray="4,2"/>'
                )

        # Numbered Callouts Section (Right panel)
        callout_x = form_x + label_width + input_width + 30
        callout_y = form_y

        svg_parts.append(
            f'<text x="{callout_x}" y="{callout_y + 10}" fill="{cls.COLORS["callout_orange"]}" font-family="system-ui, sans-serif" font-size="11" font-weight="700">ACTION CALLOUTS:</text>'
        )

        for c_idx, (c_num, c_text) in enumerate(callouts[:3]):
            c_row_y = callout_y + 24 + c_idx * 36
            # Limit callout instruction to max 8 words
            words = str(c_text).split()
            short_c_text = " ".join(words[:8])

            svg_parts.append(
                f'<circle cx="{callout_x + 10}" cy="{c_row_y + 8}" r="9" fill="{cls.COLORS["callout_orange"]}"/>'
                f'<text x="{callout_x + 10}" y="{c_row_y + 12}" fill="#0B0F19" font-family="system-ui, sans-serif" font-size="10.5" font-weight="900" text-anchor="middle">{c_num}</text>'
                f'<text x="{callout_x + 26}" y="{c_row_y + 12}" fill="{cls.COLORS["text_primary"]}" font-family="system-ui, sans-serif" font-size="10.5" font-weight="500">{cls._escape(short_c_text)}</text>'
            )

        # Footer Status bar & illustrative mockup disclaimer
        footer_y = height - 32
        svg_parts.append(
            f'<rect y="{footer_y}" width="{width}" height="32" rx="10" fill="{cls.COLORS["window_header"]}"/>'
            f'<rect y="{footer_y}" width="{width}" height="10" fill="{cls.COLORS["window_header"]}"/>'
            f'<text x="20" y="{footer_y + 18}" fill="{cls.COLORS["text_secondary"]}" font-family="system-ui, sans-serif" font-size="10">System: S4H · Client: 100 · User: CONSULTANT · Mode: READ-ONLY DIAGNOSTIC</text>'
            f'<text x="{width - 20}" y="{footer_y + 18}" fill="{cls.COLORS["text_muted"]}" font-family="system-ui, sans-serif" font-size="9.5" text-anchor="end">Illustrative mockup · Not an actual system screenshot</text>'
        )

        svg_parts.append('</svg>')
        return "\n".join(svg_parts)


sap_gui_svg_builder = SapGuiSvgBuilder()
