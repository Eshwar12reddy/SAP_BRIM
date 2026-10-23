from backend.app.services.rag_service import rag_service

FENCE = chr(96) * 3


def _sanitized():
    answer = (
        FENCE + "mermaid\n"
        "flowchart TD\n"
        '    SOM["SAP SOM"] --> CC["SAP CC"]\n'
        '    CC --> CI["SAP CI"]\n'
        + FENCE + "\n\n### Explanation\n"
        "The flow uses FKKBIX_SAMPLE and FPVB_FAKE_99 as examples.\n"
    )
    return rag_service._sanitize_and_verify_identifiers(answer, [])


def test_closing_fence_stands_alone():
    out = _sanitized()
    assert ("\n" + FENCE + "\n\n### Explanation") in out
    assert (FENCE + " (unverified") not in out


def test_diagram_block_is_not_annotated():
    out = _sanitized()
    block = out.split(FENCE)[1]
    assert "unverified" not in block


def test_identifiers_annotated_in_prose_only():
    out = _sanitized()
    assert "FKKBIX_SAMPLE (unverified, confirm in your system)" in out


def test_fence_with_trailing_unverified_notice_moved_to_own_line():
    raw = (
        FENCE + "mermaid\n"
        "flowchart TD\n"
        '    A["SOM"] --> B["CC"]\n'
        + FENCE + " (unverified, confirm in your system)\n"
        "### Explanation\n"
        "Here is the detailed flow."
    )
    out = rag_service._sanitize_and_verify_identifiers(raw, [])
    assert FENCE + "\n\n_(Unverified, confirm in your system)_\n\n" in out
    assert "### Explanation" in out


def test_repair_mermaid_endpoint():
    from unittest.mock import patch
    from fastapi.testclient import TestClient
    from backend.app.main import app

    client = TestClient(app)
    with patch("backend.app.api.rag.llm_service.generate_completion") as mock_gen:
        mock_gen.return_value = 'flowchart TD\n    A["SOM"] --> B["CC"]'
        resp = client.post(
            "/api/rag/repair-mermaid",
            json={
                "chart": 'flowchart TD\n    D["FI\u2011CA Contract\n',
                "error": "Parse error on line 13",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert 'flowchart TD\n    A["SOM"] --> B["CC"]' in data["repaired"]
        assert mock_gen.called
        # Check prompt instructions
        prompt_arg = mock_gen.call_args[0][0]
        assert "Fix this Mermaid so it parses. Return only the corrected Mermaid code, ASCII only." in prompt_arg