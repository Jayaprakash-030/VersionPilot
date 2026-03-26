from __future__ import annotations

from unittest.mock import MagicMock

from app.tools.rules_extractor import RulesExtractor


def _mock_llm(response_text: str) -> MagicMock:
    llm = MagicMock()
    llm.call.return_value = response_text
    return llm


CANNED_RULES = [
    {
        "symbol": "flask.ext",
        "replacement": "flask_extension",
        "severity": "high",
        "note": "Removed in Flask 1.0",
    },
    {
        "symbol": "flask.signals.Namespace",
        "replacement": "blinker.Namespace",
        "severity": "medium",
        "note": "Deprecated in Flask 0.11",
    },
]


# ---------------------------------------------------------------------------
# extract_rules
# ---------------------------------------------------------------------------

def test_extract_rules_returns_list_from_llm():
    import json
    extractor = RulesExtractor(llm_client=_mock_llm(json.dumps(CANNED_RULES)))
    result = extractor.extract_rules("flask", "Flask 1.0 removed flask.ext")
    assert result == CANNED_RULES


def test_extract_rules_returns_empty_when_llm_unavailable():
    extractor = RulesExtractor(llm_client=None)
    result = extractor.extract_rules("flask", "Flask 1.0 removed flask.ext")
    assert result == []


def test_extract_rules_returns_empty_for_blank_notes():
    extractor = RulesExtractor(llm_client=_mock_llm("[]"))
    result = extractor.extract_rules("flask", "   ")
    assert result == []
    extractor.llm.call.assert_not_called()


def test_extract_rules_returns_empty_on_malformed_json():
    extractor = RulesExtractor(llm_client=_mock_llm("not valid json {{{"))
    result = extractor.extract_rules("flask", "some notes")
    assert result == []


def test_extract_rules_returns_empty_when_llm_returns_non_list():
    extractor = RulesExtractor(llm_client=_mock_llm('{"symbol": "flask.ext"}'))
    result = extractor.extract_rules("flask", "some notes")
    assert result == []


# ---------------------------------------------------------------------------
# build_rules_dict
# ---------------------------------------------------------------------------

def test_build_rules_dict_produces_correct_schema():
    import json
    extractor = RulesExtractor(llm_client=_mock_llm(json.dumps(CANNED_RULES)))
    result = extractor.build_rules_dict("flask", "Flask 1.0 removed flask.ext")

    assert "flask" in result
    symbols = result["flask"]["deprecated_symbols"]
    assert "flask.ext" in symbols
    assert symbols["flask.ext"]["replacement"] == "flask_extension"
    assert symbols["flask.ext"]["severity"] == "high"
    assert "flask.signals.Namespace" in symbols


def test_build_rules_dict_returns_empty_when_no_rules():
    extractor = RulesExtractor(llm_client=_mock_llm("[]"))
    result = extractor.build_rules_dict("flask", "No deprecations here")
    assert result == {}


def test_build_rules_dict_skips_rules_missing_symbol():
    import json
    bad_rules = [{"replacement": "something", "severity": "high", "note": "missing symbol key"}]
    extractor = RulesExtractor(llm_client=_mock_llm(json.dumps(bad_rules)))
    result = extractor.build_rules_dict("flask", "some notes")
    assert result == {}
