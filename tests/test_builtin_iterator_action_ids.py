import json

from jaw.config import BUILTIN_ACTION_LABELS, DEFAULT_MATRIX_BASE, DEFAULT_SEQUENCES
from jaw.userdata import DEFAULT_USER_TEMPLATE_PATH


def test_builtin_iterators_use_semantic_action_ids():
    assert set(DEFAULT_SEQUENCES) == {
        "iterate_contact",
        "iterate_address",
        "iterate_links",
    }
    assert DEFAULT_MATRIX_BASE["P11"] == "iterate_contact"
    assert DEFAULT_MATRIX_BASE["P14"] == "iterate_links"
    assert DEFAULT_MATRIX_BASE["P21"] == "iterate_address"
    assert BUILTIN_ACTION_LABELS["iterate_contact"] == "Contact"
    assert BUILTIN_ACTION_LABELS["iterate_address"] == "Address"
    assert BUILTIN_ACTION_LABELS["iterate_links"] == "Links"


def test_default_user_contains_no_legacy_sequence_action_ids():
    data = json.loads(DEFAULT_USER_TEMPLATE_PATH.read_text(encoding="utf-8"))
    serialized = json.dumps(data)
    assert "sequence:q" not in serialized
    assert "sequence:a" not in serialized
    assert "sequence:links" not in serialized
