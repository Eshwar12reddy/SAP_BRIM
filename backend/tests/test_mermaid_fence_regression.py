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