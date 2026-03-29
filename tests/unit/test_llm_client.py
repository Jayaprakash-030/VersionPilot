from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import anthropic
import pytest

from app.agents.llm_client import LLMClient


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
    with patch("app.agents.llm_client.anthropic.AnthropicVertex") as MockVertex:
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
    assert client.last_model_used == LLMClient.DEFAULT_MODEL


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

    with patch("app.agents.llm_client.time.sleep"):
        result = client.call("sys", "user")

    assert result == "recovered"
    assert mock_vertex.messages.create.call_count == 2


def test_call_falls_back_to_gemini_on_quota_error():
    client, mock_vertex = _make_client()
    mock_vertex.messages.create.side_effect = anthropic.RateLimitError(
        message="quota exceeded", response=MagicMock(status_code=429), body={}
    )

    with patch.object(client, "_call_gemini", return_value="gemini response") as mock_gemini:
        result = client.call("sys", "user")

    assert result == "gemini response"
    assert client.last_model_used == LLMClient.GEMINI_MODEL
    mock_gemini.assert_called_once_with("sys", "user", 1024)
    # Claude should only be called once — no retries on quota errors
    assert mock_vertex.messages.create.call_count == 1


def test_call_falls_back_to_gemini_after_max_retries():
    client, mock_vertex = _make_client()
    mock_vertex.messages.create.side_effect = RuntimeError("always fails")

    with patch("app.agents.llm_client.time.sleep"):
        with patch.object(client, "_call_gemini", return_value="gemini response") as mock_gemini:
            result = client.call("sys", "user")

    assert result == "gemini response"
    assert mock_vertex.messages.create.call_count == LLMClient.MAX_RETRIES
    mock_gemini.assert_called_once()


def test_call_raises_when_both_claude_and_gemini_fail():
    client, mock_vertex = _make_client()
    mock_vertex.messages.create.side_effect = anthropic.RateLimitError(
        message="quota exceeded", response=MagicMock(status_code=429), body={}
    )

    with patch.object(client, "_call_gemini", side_effect=RuntimeError("gemini also down")):
        with pytest.raises(RuntimeError, match="Both Claude and Gemini failed"):
            client.call("sys", "user")
