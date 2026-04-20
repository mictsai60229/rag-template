"""Unit tests for src/providers/llm_provider.py.

All openai SDK calls are mocked — no real API calls are made.
"""

import sys
from unittest.mock import MagicMock, patch

import pytest

from src.exceptions.domain import ExternalServiceError
from src.models import Chunk


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_chunk(content: str, chunk_id: str = "c1") -> Chunk:
    return Chunk(
        chunk_id=chunk_id,
        doc_id="d1",
        content=content,
        source="doc.pdf",
        doc_type="pdf",
        page_number=None,
        chunk_index=0,
        ingested_at="2024-01-01",
        score=0.9,
    )


def _make_provider(api_response_content: str = "The answer is 42.") -> "tuple[object, MagicMock]":
    """Create an OpenAIChatProvider with mocked openai module and return both."""
    from src.providers.llm_provider import OpenAIChatProvider

    mock_openai_mod = MagicMock()

    # Set up mock response chain
    mock_response = MagicMock()
    mock_response.choices[0].message.content = api_response_content
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_response
    mock_openai_mod.OpenAI.return_value = mock_client

    provider = OpenAIChatProvider.__new__(OpenAIChatProvider)
    provider._openai = mock_openai_mod
    provider._api_key = "sk-test"
    provider._model = "gpt-4o-mini"

    # Build the real prompt template (langchain-core is available)
    from langchain_core.prompts import ChatPromptTemplate

    provider._prompt_template = ChatPromptTemplate.from_messages(
        [
            ("system", OpenAIChatProvider._SYSTEM_MESSAGE),
            ("human", "Context:\n{context}\n\nQuestion: {question}"),
        ]
    )

    return provider, mock_client


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestOpenAIChatProvider:
    def test_generate_returns_mocked_answer(self) -> None:
        """generate() returns choices[0].message.content from the mock response."""
        provider, _ = _make_provider("The answer is 42.")
        chunks = [_make_chunk("Python is a programming language.")]

        result = provider.generate("What is Python?", chunks)

        assert result == "The answer is 42."

    def test_generate_builds_numbered_context(self) -> None:
        """generate() includes chunk contents as a numbered list in the user message."""
        provider, mock_client = _make_provider()
        chunks = [
            _make_chunk("First chunk content.", "c1"),
            _make_chunk("Second chunk content.", "c2"),
        ]

        provider.generate("query", chunks)

        call_args = mock_client.chat.completions.create.call_args
        messages = call_args.kwargs["messages"] if call_args.kwargs else call_args[1]["messages"]
        user_message = next(m for m in messages if m["role"] == "user")
        assert "1. First chunk content." in user_message["content"]
        assert "2. Second chunk content." in user_message["content"]

    def test_generate_empty_chunks_shows_no_context_message(self) -> None:
        """When chunks is empty, context section says so."""
        provider, mock_client = _make_provider()

        provider.generate("query with no context", [])

        call_args = mock_client.chat.completions.create.call_args
        messages = call_args.kwargs["messages"] if call_args.kwargs else call_args[1]["messages"]
        user_message = next(m for m in messages if m["role"] == "user")
        assert "No context retrieved" in user_message["content"]

    def test_generate_passes_system_message(self) -> None:
        """generate() includes a system message in the API call."""
        provider, mock_client = _make_provider()

        provider.generate("query", [])

        call_args = mock_client.chat.completions.create.call_args
        messages = call_args.kwargs["messages"] if call_args.kwargs else call_args[1]["messages"]
        system_message = next((m for m in messages if m["role"] == "system"), None)
        assert system_message is not None
        assert "helpful assistant" in system_message["content"]

    def test_api_error_wrapped_as_external_service_error(self) -> None:
        """openai.APIError is caught and re-raised as ExternalServiceError."""
        provider, mock_client = _make_provider()

        # Create a subclass of APIError that openai uses
        api_error_cls = type("APIError", (Exception,), {})
        provider._openai.APIError = api_error_cls
        mock_client.chat.completions.create.side_effect = api_error_cls("API failed")

        with pytest.raises(ExternalServiceError, match="chat completion failed"):
            provider.generate("query", [_make_chunk("content")])

    def test_generate_uses_configured_model(self) -> None:
        """generate() passes the configured model name to the API."""
        provider, mock_client = _make_provider()

        provider.generate("query", [])

        call_args = mock_client.chat.completions.create.call_args
        model_used = call_args.kwargs["model"] if call_args.kwargs else call_args[1]["model"]
        assert model_used == "gpt-4o-mini"
