"""LLM provider abstract base class and OpenAI Chat Completions implementation.

This is the only file in ``src/`` that imports ``openai`` for chat completions.
Prompt assembly uses ``langchain-core`` ``ChatPromptTemplate``.

Usage::

    provider = OpenAIChatProvider(api_key="sk-...", model="gpt-4o-mini")
    answer = provider.generate(query="What is Python?", chunks=[chunk1, chunk2])
"""

from abc import ABC, abstractmethod

from src.exceptions.domain import ExternalServiceError
from src.models import Chunk


class LLMProvider(ABC):
    """Abstract base class for LLM response generation providers."""

    @abstractmethod
    def generate(self, query: str, chunks: list[Chunk]) -> str:
        """Generate an answer for ``query`` grounded in the provided ``chunks``.

        Args:
            query: The natural-language question from the caller.
            chunks: Retrieved context chunks to include in the prompt.

        Returns:
            The LLM-generated answer string.
        """
        ...


class OpenAIChatProvider(LLMProvider):
    """LLM provider backed by the OpenAI Chat Completions API.

    Builds a prompt from a ``langchain-core`` ``ChatPromptTemplate``, formats
    the context as a numbered list of chunk contents, and calls the OpenAI
    chat completions endpoint.

    System message instructs the model to use only the provided context.
    If the context does not contain the answer, the model is told to say so.
    """

    _SYSTEM_MESSAGE = (
        "You are a helpful assistant. Use only the provided context to answer "
        "the user's question. If the context does not contain the answer, say so."
    )

    def __init__(self, api_key: str, model: str) -> None:
        """Initialise the OpenAI chat provider.

        Args:
            api_key: OpenAI API key.
            model: Chat model name (e.g. ``"gpt-4o-mini"``).
        """
        import openai  # lazy import — keeps the module optional at import time

        self._openai = openai
        self._api_key = api_key
        self._model = model

        from langchain_core.prompts import ChatPromptTemplate

        self._prompt_template = ChatPromptTemplate.from_messages(
            [
                ("system", self._SYSTEM_MESSAGE),
                ("human", "Context:\n{context}\n\nQuestion: {question}"),
            ]
        )

    def generate(self, query: str, chunks: list[Chunk]) -> str:
        """Build the prompt, call the LLM, and return the answer.

        Args:
            query: The natural-language question.
            chunks: Retrieved context chunks.

        Returns:
            The LLM answer string.

        Raises:
            ExternalServiceError: On any ``openai.APIError``.
        """
        context = self._format_context(chunks)
        messages = self._prompt_template.format_messages(context=context, question=query)

        # Convert LangChain message objects to the dict format expected by openai SDK
        openai_messages = [{"role": m.type if m.type != "human" else "user", "content": m.content}
                           for m in messages]

        try:
            client = self._openai.OpenAI(api_key=self._api_key)
            response = client.chat.completions.create(
                model=self._model,
                messages=openai_messages,
            )
            return str(response.choices[0].message.content)
        except self._openai.APIError as exc:
            raise ExternalServiceError(f"OpenAI chat completion failed: {exc}") from exc

    @staticmethod
    def _format_context(chunks: list[Chunk]) -> str:
        """Format retrieved chunks as a numbered list for the prompt.

        Args:
            chunks: Chunks to include in the prompt context.

        Returns:
            A string with each chunk's content on a numbered line.
        """
        if not chunks:
            return "(No context retrieved.)"
        lines = [f"{i + 1}. {chunk.content}" for i, chunk in enumerate(chunks)]
        return "\n".join(lines)
