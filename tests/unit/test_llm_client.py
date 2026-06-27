from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

from app.agents.llm_client import LLMClient


def _make_client(model: str | None = None) -> tuple[LLMClient, MagicMock]:
    """Return an LLMClient with the underlying OpenAI client mocked."""
    with patch("app.agents.llm_client.OpenAI") as mock_openai:
        client = LLMClient(model=model)
    mock_client = mock_openai.return_value
    client.client = mock_client
    return client, mock_client


def _mock_response(
    text: str,
    input_tokens: int = 10,
    output_tokens: int = 20,
) -> MagicMock:
    response = MagicMock()
    response.output_text = text
    response.usage.input_tokens = input_tokens
    response.usage.output_tokens = output_tokens
    return response


def test_is_available_returns_true_when_openai_key_set():
    with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
        assert LLMClient.is_available() is True


def test_is_available_returns_false_when_openai_key_missing():
    env = {key: value for key, value in os.environ.items() if key != "OPENAI_API_KEY"}
    with patch.dict(os.environ, env, clear=True):
        assert LLMClient.is_available() is False


def test_default_model_is_gpt_54_nano():
    client, _ = _make_client()

    assert client.model == "gpt-5.4-nano"


def test_model_can_be_overridden_by_constructor():
    client, _ = _make_client(model="gpt-5.4-mini")

    assert client.model == "gpt-5.4-mini"


def test_model_can_be_overridden_by_environment():
    with patch.dict(os.environ, {"OPENAI_MODEL": "gpt-5.4-mini"}):
        client, _ = _make_client()

    assert client.model == "gpt-5.4-mini"


def test_call_returns_output_text():
    client, mock_openai = _make_client()
    mock_openai.responses.create.return_value = _mock_response("hello")

    result = client.call("sys", "user")

    assert result == "hello"
    assert client.last_model_used == LLMClient.DEFAULT_MODEL


def test_call_accumulates_tokens_across_calls():
    client, mock_openai = _make_client()
    mock_openai.responses.create.return_value = _mock_response(
        "ok",
        input_tokens=5,
        output_tokens=10,
    )

    client.call("sys", "first")
    client.call("sys", "second")

    assert client.total_input_tokens == 10
    assert client.total_output_tokens == 20


def test_call_passes_expected_responses_api_params():
    client, mock_openai = _make_client()
    mock_openai.responses.create.return_value = _mock_response("ok")

    client.call("my-system", "my-user", max_tokens=512)

    mock_openai.responses.create.assert_called_once_with(
        model=client.model,
        instructions="my-system",
        input="my-user",
        max_output_tokens=512,
    )


def test_call_retries_on_transient_error_then_succeeds():
    client, mock_openai = _make_client()
    mock_openai.responses.create.side_effect = [
        RuntimeError("transient"),
        _mock_response("recovered"),
    ]

    with patch("app.agents.llm_client.time.sleep"):
        result = client.call("sys", "user")

    assert result == "recovered"
    assert mock_openai.responses.create.call_count == 2


def test_call_raises_after_max_retries():
    client, mock_openai = _make_client()
    mock_openai.responses.create.side_effect = RuntimeError("always fails")

    with patch("app.agents.llm_client.time.sleep"):
        with pytest.raises(RuntimeError, match="OpenAI call failed"):
            client.call("sys", "user")

    assert mock_openai.responses.create.call_count == LLMClient.MAX_RETRIES


def test_extract_text_falls_back_to_output_content_parts():
    client, _ = _make_client()
    content = MagicMock()
    content.text = "fallback text"
    item = MagicMock()
    item.content = [content]
    response = MagicMock()
    response.output_text = None
    response.output = [item]

    assert client._extract_text(response) == "fallback text"
