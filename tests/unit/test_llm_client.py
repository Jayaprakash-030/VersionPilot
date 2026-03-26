from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

from app.llm_client import LLMClient


# ---------------------------------------------------------------------------
# is_available
# ---------------------------------------------------------------------------

def test_is_available_returns_true_when_env_set():
    with patch.dict(os.environ, {"GOOGLE_CLOUD_PROJECT": "my-project"}):
        assert LLMClient.is_available() is True


def test_is_available_returns_false_when_env_missing():
    env = {k: v for k, v in os.environ.items() if k != "GOOGLE_CLOUD_PROJECT"}
    with patch.dict(os.environ, env, clear=True):
        assert LLMClient.is_available() is False


# ---------------------------------------------------------------------------
# call — happy path
# ---------------------------------------------------------------------------

def _make_client() -> tuple[LLMClient, MagicMock]:
    """Return an LLMClient with the underlying Anthropic client mocked."""
    with patch("app.llm_client.anthropic.AnthropicVertex") as MockVertex:
        client = LLMClient()
    mock_vertex = MockVertex.return_value
    client.client = mock_vertex
    return client, mock_vertex


def _mock_response(text: str, input_tokens: int = 10, output_tokens: int = 20) -> MagicMock:
    response = MagicMock()
    response.content = [MagicMock(text=text)]
    response.usage.input_tokens = input_tokens
    response.usage.output_tokens = output_tokens
    return response


def test_call_returns_text():
    client, mock_vertex = _make_client()
    mock_vertex.messages.create.return_value = _mock_response("hello")
    result = client.call("sys", "user")
    assert result == "hello"


def test_call_accumulates_tokens_across_calls():
    client, mock_vertex = _make_client()
    mock_vertex.messages.create.return_value = _mock_response("a", input_tokens=5, output_tokens=10)

    client.call("sys", "first")
    client.call("sys", "second")

    assert client.total_input_tokens == 10
    assert client.total_output_tokens == 20


def test_call_passes_correct_params():
    client, mock_vertex = _make_client()
    mock_vertex.messages.create.return_value = _mock_response("ok")

    client.call("my-system", "my-user", max_tokens=512)

    mock_vertex.messages.create.assert_called_once_with(
        model=client.model,
        max_tokens=512,
        system="my-system",
        messages=[{"role": "user", "content": "my-user"}],
    )


# ---------------------------------------------------------------------------
# call — retry logic
# ---------------------------------------------------------------------------

def test_call_retries_on_transient_error_then_succeeds():
    client, mock_vertex = _make_client()
    mock_vertex.messages.create.side_effect = [
        RuntimeError("transient"),
        _mock_response("recovered"),
    ]

    with patch("app.llm_client.time.sleep"):
        result = client.call("sys", "user")

    assert result == "recovered"
    assert mock_vertex.messages.create.call_count == 2


def test_call_raises_after_max_retries():
    client, mock_vertex = _make_client()
    mock_vertex.messages.create.side_effect = RuntimeError("always fails")

    with patch("app.llm_client.time.sleep"):
        with pytest.raises(RuntimeError, match="failed after"):
            client.call("sys", "user")

    assert mock_vertex.messages.create.call_count == LLMClient.MAX_RETRIES
