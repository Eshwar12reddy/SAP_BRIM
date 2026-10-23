import html
from typing import Dict, Any, List, Optional


class SVGRenderer:
    """
    Deterministic, pure-Python SVG diagram renderer for SAP architecture,
    process flows, document relationships, decision paths, and comparisons.
    
    Security & Accuracy:
    - Pure XML SVG (no scripts, foreignObjects, or external references).
    - All text safely escaped.
    - Mandatory watermark: "AI-generated illustration - not an SAP screenshot".
    """

    # Color Palette matching Clyptus Enterprise UI
    COLORS = {
        "bg": "#0B0F19",
        "card_bg": "#151D30",
        "card_border": "#283553",
        "header_bg": "#1E293B",
        "text_primary": "#F1F5F9",
        "text_secondary": "#94A3B8",
        "text_muted": "#64748B",
        "accent_orange": "#F97316",
        "accent_blue": "#38BDF8",
        "accent_emerald": "#34D399",
        "accent_purple": "#A855F7",
        "accent_amber": "#FBBF24",
        "arrow": "#60A5FA",
        "branch_yes": "#34D399",
        "branch_no": "#F87171",
        "badge_bg": "#1E293B",
        "badge_border": "#334155"
    }

    @classmethod
    def render_spec(cls, spec: Dict[str, Any]) -> str:
        """Render a validated diagram specification to safe SVG string."""
        v_type = spec.get("type", "flow_diagram")
        if v_type in ("architecture", "system_landscape"):
            return cls._render_architecture(spec)
        elif v_type in ("document_flow", "lifecycle"):
            return cls._render_lifecycle_flow(spec)
        elif v_type in ("decision_tree", "troubleshooting_path"):
            return cls._render_decision_tree(spec)
        elif v_type in ("sequence", "interaction"):
            return cls._render_sequence(spec)
        elif v_type in ("comparison",):
            return cls._render_comparison(spec)
        else:
            return cls._render_flow_diagram(spec)

    @classmethod
    def render_svg(cls, spec: Dict[str, Any]) -> str:
        return cls.render_spec(spec)

    @classmethod
    def _escape(cls, text: Any) -> str:
        return html.escape(str(text or ""), quote=True)

    @classmethod
    def _render_flow_diagram(cls, spec: Dict[str, Any]) -> str:
        title = spec.get("title", "SAP Process Flow")
        caption = spec.get("caption", "")
        nodes = spec.get("nodes", [])
        edges = spec.get("edges", [])

        width = 680
        node_width = 460
        node_height = 54
        start_y = 70
        spacing_y = 80
        total_height = max(340, start_y + len(nodes) * spacing_y + 60)

        svg_parts = [
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {total_height}" width="100%" height="100%">',
            cls._defs(),
            f'<rect width="{width}" height="{total_height}" rx="12" fill="{cls.COLORS["bg"]}"/>',
            cls._render_header(title, width),
        ]

        node_positions = {}
        for idx, node in enumerate(nodes):
            x = (width - node_width) // 2
            y = start_y + idx * spacing_y
            node_id = str(node.get("id", idx))
            node_positions[node_id] = (x + node_width // 2, y + node_height)

            label = cls._escape(node.get("label", f"Step {idx+1}"))
            sub = cls._escape(node.get("description", node.get("tcode", "")))
            step_tag = cls._escape(node.get("step_id", f"STEP {idx+1}"))

            # Draw connector line from previous node
            if idx > 0:
                prev_x = width // 2
                prev_y = start_y + (idx - 1) * spacing_y + node_height
                svg_parts.append(
                    f'<line x1="{prev_x}" y1="{prev_y}" x2="{prev_x}" y2="{y}" stroke="{cls.COLORS["arrow"]}" stroke-width="2" marker-end="url(#arrow)"/>'
                )

            # Node card
            border_color = cls.COLORS["accent_orange"] if idx == 0 else cls.COLORS["card_border"]
            svg_parts.append(
                f'<rect x="{x}" y="{y}" width="{node_width}" height="{node_height}" rx="8" fill="{cls.COLORS["card_bg"]}" stroke="{border_color}" stroke-width="1.5"/>'
            )
            # Step badge
            svg_parts.append(
                f'<rect x="{x+10}" y="{y+14}" width="65" height="24" rx="4" fill="{cls.COLORS["header_bg"]}" stroke="{cls.COLORS["badge_border"]}"/>'
                f'<text x="{x+42}" y="{y+30}" fill="{cls.COLORS["accent_orange"]}" font-family="system-ui, sans-serif" font-size="11" font-weight="700" text-anchor="middle">{step_tag}</text>'
            )
            # Label
            svg_parts.append(
                f'<text x="{x+86}" y="{y+26}" fill="{cls.COLORS["text_primary"]}" font-family="system-ui, sans-serif" font-size="13" font-weight="600">{label}</text>'
            )
            # Subtitle / description / tcode
            if sub:
                svg_parts.append(
                    f'<text x="{x+86}" y="{y+42}" fill="{cls.COLORS["text_secondary"]}" font-family="system-ui, sans-serif" font-size="11">{sub}</text>'
                )

        svg_parts.append(cls._render_disclaimer(width, total_height))
        svg_parts.append('</svg>')
        return "".join(svg_parts)

    @classmethod
    def _render_architecture(cls, spec: Dict[str, Any]) -> str:
        title = spec.get("title", "SAP Architecture Landscape")
        nodes = spec.get("nodes", [])

        width = 720
        start_y = 70
        cols = 3
        card_w = 200
        card_h = 90
        gap_x = 30
        gap_y = 35

        rows = (len(nodes) + cols - 1) // cols
        total_height = max(360, start_y + rows * (card_h + gap_y) + 70)

        svg_parts = [
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {total_height}" width="100%" height="100%">',
            cls._defs(),
            f'<rect width="{width}" height="{total_height}" rx="12" fill="{cls.COLORS["bg"]}"/>',
            cls._render_header(title, width),
        ]

        for idx, node in enumerate(nodes):
            r = idx // cols
            c = idx % cols
            x = 45 + c * (card_w + gap_x)
            y = start_y + r * (card_h + gap_y)

            label = cls._escape(node.get("label", "Component"))
            role = cls._escape(node.get("role", node.get("type", "SAP Module")))
            tcode = cls._escape(node.get("tcode", node.get("details", "")))

            color_accent = cls.COLORS["accent_blue"] if "SOM" in label.upper() else (
                cls.COLORS["accent_purple"] if "CC" in label.upper() else (
                    cls.COLORS["accent_emerald"] if "CI" in label.upper() else (
                        cls.COLORS["accent_orange"] if "FI-CA" in label.upper() else cls.COLORS["accent_amber"]
                    )
                )
            )

            # Node Box
            svg_parts.append(
                f'<rect x="{x}" y="{y}" width="{card_w}" height="{card_h}" rx="8" fill="{cls.COLORS["card_bg"]}" stroke="{cls.COLORS["card_border"]}" stroke-width="1.5"/>'
                f'<rect x="{x}" y="{y}" width="5" height="{card_h}" rx="2" fill="{color_accent}"/>'
                f'<text x="{x+16}" y="{y+26}" fill="{cls.COLORS["text_primary"]}" font-family="system-ui, sans-serif" font-size="14" font-weight="700">{label}</text>'
                f'<text x="{x+16}" y="{y+46}" fill="{cls.COLORS["text_secondary"]}" font-family="system-ui, sans-serif" font-size="11">{role}</text>'
            )
            if tcode:
                svg_parts.append(
                    f'<rect x="{x+16}" y="{y+56}" width="{min(170, len(tcode)*7 + 12)}" height="20" rx="4" fill="{cls.COLORS["header_bg"]}"/>'
                    f'<text x="{x+22}" y="{y+70}" fill="{color_accent}" font-family="monospace" font-size="10">{tcode}</text>'
                )

            # Connect horizontally if not end of row
            if c < cols - 1 and idx + 1 < len(nodes):
                next_x = x + card_w
                svg_parts.append(
                    f'<line x1="{next_x}" y1="{y+card_h//2}" x2="{next_x+gap_x}" y2="{y+card_h//2}" stroke="{cls.COLORS["arrow"]}" stroke-width="2" marker-end="url(#arrow)"/>'
                )

        svg_parts.append(cls._render_disclaimer(width, total_height))
        svg_parts.append('</svg>')
        return "".join(svg_parts)

    @classmethod
    def _render_lifecycle_flow(cls, spec: Dict[str, Any]) -> str:
        title = spec.get("title", "Document & Lifecycle Flow")
        nodes = spec.get("nodes", [])

        width = 720
        node_count = max(1, len(nodes))
        spacing = (width - 60) // node_count
        card_w = min(150, spacing - 20)
        card_h = 100
        start_y = 90
        total_height = 260

        svg_parts = [
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {total_height}" width="100%" height="100%">',
            cls._defs(),
            f'<rect width="{width}" height="{total_height}" rx="12" fill="{cls.COLORS["bg"]}"/>',
            cls._render_header(title, width),
        ]

        for idx, node in enumerate(nodes):
            x = 30 + idx * spacing
            y = start_y
            label = cls._escape(node.get("label", f"Step {idx+1}"))
            sub = cls._escape(node.get("description", ""))
            doc_type = cls._escape(node.get("doc_type", f"Doc {idx+1}"))

            svg_parts.append(
                f'<rect x="{x}" y="{y}" width="{card_w}" height="{card_h}" rx="8" fill="{cls.COLORS["card_bg"]}" stroke="{cls.COLORS["card_border"]}" stroke-width="1.5"/>'
                f'<circle cx="{x+20}" cy="{y+22}" r="10" fill="{cls.COLORS["accent_orange"]}"/>'
                f'<text x="{x+20}" y="{y+26}" fill="#FFFFFF" font-family="system-ui, sans-serif" font-size="11" font-weight="700" text-anchor="middle">{idx+1}</text>'
                f'<text x="{x+36}" y="{y+25}" fill="{cls.COLORS["accent_blue"]}" font-family="system-ui, sans-serif" font-size="11" font-weight="600">{doc_type}</text>'
                f'<text x="{x+12}" y="{y+55}" fill="{cls.COLORS["text_primary"]}" font-family="system-ui, sans-serif" font-size="12" font-weight="700">{label}</text>'
            )
            if sub:
                svg_parts.append(
                    f'<text x="{x+12}" y="{y+75}" fill="{cls.COLORS["text_secondary"]}" font-family="system-ui, sans-serif" font-size="10">{sub}</text>'
                )

            # Connect arrow
            if idx < len(nodes) - 1:
                next_x = x + card_w
                target_x = 30 + (idx + 1) * spacing
                mid_y = y + card_h // 2
                svg_parts.append(
                    f'<line x1="{next_x}" y1="{mid_y}" x2="{target_x}" y2="{mid_y}" stroke="{cls.COLORS["arrow"]}" stroke-width="2" marker-end="url(#arrow)"/>'
                )

        svg_parts.append(cls._render_disclaimer(width, total_height))
        svg_parts.append('</svg>')
        return "".join(svg_parts)

    @classmethod
    def _render_decision_tree(cls, spec: Dict[str, Any]) -> str:
        title = spec.get("title", "Decision & Troubleshooting Tree")
        nodes = spec.get("nodes", [])

        width = 680
        total_height = 420
        svg_parts = [
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {total_height}" width="100%" height="100%">',
            cls._defs(),
            f'<rect width="{width}" height="{total_height}" rx="12" fill="{cls.COLORS["bg"]}"/>',
            cls._render_header(title, width),
        ]

        # Top Question Box
        root_label = cls._escape(spec.get("root_question", (nodes[0]["label"] if nodes else "Confirm Symptom")))
        svg_parts.append(
            f'<rect x="190" y="70" width="300" height="50" rx="8" fill="{cls.COLORS["card_bg"]}" stroke="{cls.COLORS["accent_orange"]}" stroke-width="1.5"/>'
            f'<text x="340" y="100" fill="{cls.COLORS["text_primary"]}" font-family="system-ui, sans-serif" font-size="13" font-weight="700" text-anchor="middle">{root_label}</text>'
        )

        # Split connectors
        svg_parts.append(
            # Line down from root
            f'<line x1="340" y1="120" x2="340" y2="150" stroke="{cls.COLORS["arrow"]}" stroke-width="2"/>'
            # Horizontal split bar
            f'<line x1="180" y1="150" x2="500" y2="150" stroke="{cls.COLORS["arrow"]}" stroke-width="2"/>'
            # Left YES branch
            f'<line x1="180" y1="150" x2="180" y2="190" stroke="{cls.COLORS["branch_yes"]}" stroke-width="2" marker-end="url(#arrow)"/>'
            f'<rect x="150" y="160" width="60" height="18" rx="4" fill="{cls.COLORS["header_bg"]}"/>'
            f'<text x="180" y="173" fill="{cls.COLORS["branch_yes"]}" font-family="system-ui, sans-serif" font-size="11" font-weight="700" text-anchor="middle">YES</text>'
            # Right NO branch
            f'<line x1="500" y1="150" x2="500" y2="190" stroke="{cls.COLORS["branch_no"]}" stroke-width="2" marker-end="url(#arrow)"/>'
            f'<rect x="470" y="160" width="60" height="18" rx="4" fill="{cls.COLORS["header_bg"]}"/>'
            f'<text x="500" y="173" fill="{cls.COLORS["branch_no"]}" font-family="system-ui, sans-serif" font-size="11" font-weight="700" text-anchor="middle">NO</text>'
        )

        # Branch Cards
        yes_label = cls._escape(spec.get("yes_action", (nodes[1]["label"] if len(nodes) > 1 else "Action Path A")))
        no_label = cls._escape(spec.get("no_action", (nodes[2]["label"] if len(nodes) > 2 else "Action Path B")))

        svg_parts.append(
            f'<rect x="60" y="190" width="240" height="80" rx="8" fill="{cls.COLORS["card_bg"]}" stroke="{cls.COLORS["branch_yes"]}" stroke-width="1.5"/>'
            f'<text x="180" y="225" fill="{cls.COLORS["text_primary"]}" font-family="system-ui, sans-serif" font-size="12" font-weight="600" text-anchor="middle">{yes_label}</text>'
            f'<rect x="380" y="190" width="240" height="80" rx="8" fill="{cls.COLORS["card_bg"]}" stroke="{cls.COLORS["branch_no"]}" stroke-width="1.5"/>'
            f'<text x="500" y="225" fill="{cls.COLORS["text_primary"]}" font-family="system-ui, sans-serif" font-size="12" font-weight="600" text-anchor="middle">{no_label}</text>'
        )

        # Convergence to Verification Box
        svg_parts.append(
            f'<line x1="180" y1="270" x2="180" y2="300" stroke="{cls.COLORS["arrow"]}" stroke-width="2"/>'
            f'<line x1="500" y1="270" x2="500" y2="300" stroke="{cls.COLORS["arrow"]}" stroke-width="2"/>'
            f'<line x1="180" y1="300" x2="500" y2="300" stroke="{cls.COLORS["arrow"]}" stroke-width="2"/>'
            f'<line x1="340" y1="300" x2="340" y2="330" stroke="{cls.COLORS["arrow"]}" stroke-width="2" marker-end="url(#arrow)"/>'
            f'<rect x="190" y="330" width="300" height="48" rx="8" fill="{cls.COLORS["card_bg"]}" stroke="{cls.COLORS["accent_blue"]}" stroke-width="1.5"/>'
            f'<text x="340" y="360" fill="{cls.COLORS["text_primary"]}" font-family="system-ui, sans-serif" font-size="12" font-weight="700" text-anchor="middle">Verify Resolution &amp; Logs</text>'
        )

        svg_parts.append(cls._render_disclaimer(width, total_height))
        svg_parts.append('</svg>')
        return "".join(svg_parts)

    @classmethod
    def _render_sequence(cls, spec: Dict[str, Any]) -> str:
        title = spec.get("title", "Sequence Interaction")
        actors = spec.get("actors", ["Client / SOM", "CC Rating", "CI Billing", "FI-CA"])
        messages = spec.get("messages", spec.get("steps", []))

        width = 680
        total_height = max(360, 100 + len(messages) * 55 + 60)
        svg_parts = [
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {total_height}" width="100%" height="100%">',
            cls._defs(),
            f'<rect width="{width}" height="{total_height}" rx="12" fill="{cls.COLORS["bg"]}"/>',
            cls._render_header(title, width),
        ]

        actor_count = len(actors)
        spacing = width // (actor_count + 1)
        actor_x = {}

        for i, actor in enumerate(actors):
            x = (i + 1) * spacing
            actor_x[i] = x
            label = cls._escape(actor)
            svg_parts.append(
                f'<rect x="{x-60}" y="65" width="120" height="32" rx="6" fill="{cls.COLORS["card_bg"]}" stroke="{cls.COLORS["card_border"]}"/>'
                f'<text x="{x}" y="85" fill="{cls.COLORS["accent_blue"]}" font-family="system-ui, sans-serif" font-size="11" font-weight="700" text-anchor="middle">{label}</text>'
                f'<line x1="{x}" y1="97" x2="{x}" y2="{total_height-45}" stroke="{cls.COLORS["card_border"]}" stroke-width="1.5" stroke-dasharray="4 4"/>'
            )

        for idx, m in enumerate(messages):
            from_idx = m.get("from_idx", max(0, idx % actor_count))
            to_idx = m.get("to_idx", min(actor_count - 1, (from_idx + 1) % actor_count))
            x1 = actor_x.get(from_idx, spacing)
            x2 = actor_x.get(to_idx, spacing * 2)
            y = 125 + idx * 50
            label = cls._escape(m.get("label", f"Call {idx+1}"))

            svg_parts.append(
                f'<line x1="{x1}" y1="{y}" x2="{x2}" y2="{y}" stroke="{cls.COLORS["accent_orange"]}" stroke-width="1.5" marker-end="url(#arrow)"/>'
                f'<text x="{(x1+x2)//2}" y="{y-6}" fill="{cls.COLORS["text_primary"]}" font-family="system-ui, sans-serif" font-size="11" font-weight="500" text-anchor="middle">{label}</text>'
            )

        svg_parts.append(cls._render_disclaimer(width, total_height))
        svg_parts.append('</svg>')
        return "".join(svg_parts)

    @classmethod
    def _render_comparison(cls, spec: Dict[str, Any]) -> str:
        title = spec.get("title", "Architectural Comparison")
        columns = spec.get("columns", ["Model A", "Model B"])
        rows = spec.get("rows", [])

        width = 680
        total_height = max(340, 90 + len(rows) * 55 + 50)
        col_w = (width - 60) // len(columns)

        svg_parts = [
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {total_height}" width="100%" height="100%">',
            cls._defs(),
            f'<rect width="{width}" height="{total_height}" rx="12" fill="{cls.COLORS["bg"]}"/>',
            cls._render_header(title, width),
        ]

        # Column Headers
        for i, col in enumerate(columns):
            x = 30 + i * col_w
            label = cls._escape(col)
            svg_parts.append(
                f'<rect x="{x}" y="65" width="{col_w-15}" height="36" rx="6" fill="{cls.COLORS["card_bg"]}" stroke="{cls.COLORS["accent_orange"] if i==0 else cls.COLORS["accent_blue"]}"/>'
                f'<text x="{x + col_w//2 - 8}" y="88" fill="{cls.COLORS["text_primary"]}" font-family="system-ui, sans-serif" font-size="13" font-weight="700" text-anchor="middle">{label}</text>'
            )

        # Rows
        for r_idx, r in enumerate(rows):
            y = 115 + r_idx * 55
            vals = r.get("values", [r.get("left", ""), r.get("right", "")])
            for c_idx, val in enumerate(vals[:len(columns)]):
                x = 30 + c_idx * col_w
                text_val = cls._escape(val)
                svg_parts.append(
                    f'<rect x="{x}" y="{y}" width="{col_w-15}" height="45" rx="6" fill="{cls.COLORS["card_bg"]}" stroke="{cls.COLORS["card_border"]}"/>'
                    f'<text x="{x+14}" y="{y+26}" fill="{cls.COLORS["text_secondary"]}" font-family="system-ui, sans-serif" font-size="11">{text_val}</text>'
                )

        svg_parts.append(cls._render_disclaimer(width, total_height))
        svg_parts.append('</svg>')
        return "".join(svg_parts)

    @classmethod
    def _defs(cls) -> str:
        return (
            '<defs>'
            f'<marker id="arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">'
            f'<path d="M 0 1 L 10 5 L 0 9 z" fill="{cls.COLORS["arrow"]}"/>'
            '</marker>'
            '</defs>'
        )

    @classmethod
    def _render_header(cls, title: str, width: int) -> str:
        escaped_title = cls._escape(title)
        return (
            f'<rect x="0" y="0" width="{width}" height="48" rx="12" fill="{cls.COLORS["header_bg"]}"/>'
            f'<circle cx="26" cy="24" r="5" fill="{cls.COLORS["accent_orange"]}"/>'
            f'<text x="42" y="29" fill="{cls.COLORS["text_primary"]}" font-family="system-ui, sans-serif" font-size="15" font-weight="700">{escaped_title}</text>'
        )

    @classmethod
    def _render_disclaimer(cls, width: int, height: int) -> str:
        # Mandatory disclaimer label
        return (
            f'<rect x="0" y="{height-28}" width="{width}" height="28" fill="{cls.COLORS["header_bg"]}"/>'
            f'<text x="{width//2}" y="{height-10}" fill="{cls.COLORS["text_muted"]}" font-family="system-ui, sans-serif" font-size="10" font-weight="600" text-anchor="middle">'
            'AI-generated illustration - not an SAP screenshot'
            '</text>'
        )


def render_svg(spec: Dict[str, Any]) -> str:
    """Render a validated diagram specification to safe SVG string."""
    return SVGRenderer.render_spec(spec)
