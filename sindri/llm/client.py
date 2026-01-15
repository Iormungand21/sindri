"""Async Ollama client wrapper."""

import ollama
from dataclasses import dataclass, field
from typing import AsyncIterator, Optional, Callable
import structlog

log = structlog.get_logger()


@dataclass
class Message:
    role: str
    content: str
    tool_calls: Optional[list] = None


@dataclass
class Response:
    message: Message
    model: str
    done: bool


@dataclass
class StreamingResponse:
    """Response from streaming chat, accumulated over time."""
    content: str = ""
    tool_calls: Optional[list] = None
    model: str = ""
    done: bool = False

    def to_response(self) -> Response:
        """Convert to a standard Response object."""
        return Response(
            message=Message(
                role="assistant",
                content=self.content,
                tool_calls=self.tool_calls
            ),
            model=self.model,
            done=self.done
        )


class OllamaClient:
    """Wrapper around Ollama with async support."""

    def __init__(self, host: str = "http://localhost:11434"):
        self.host = host
        self._client = ollama.Client(host=host)
        self._async_client = ollama.AsyncClient(host=host)

    async def chat(
        self,
        model: str,
        messages: list[dict],
        tools: list[dict] = None
    ) -> Response:
        """Send chat request to Ollama."""

        kwargs = {
            "model": model,
            "messages": messages,
        }
        if tools:
            kwargs["tools"] = tools

        log.info("ollama_chat_request", model=model, num_messages=len(messages))

        response = await self._async_client.chat(**kwargs)

        log.debug("ollama_response_keys", keys=list(response.keys()) if isinstance(response, dict) else "not_dict")
        log.debug("ollama_message_keys", keys=list(response.get("message", {}).keys()) if isinstance(response, dict) else "not_dict")

        tool_calls = response["message"].get("tool_calls")
        log.info("ollama_tool_calls", tool_calls=tool_calls)

        return Response(
            message=Message(
                role=response["message"]["role"],
                content=response["message"].get("content", ""),
                tool_calls=tool_calls
            ),
            model=response["model"],
            done=response.get("done", True)
        )

    async def stream(
        self,
        model: str,
        messages: list[dict]
    ) -> AsyncIterator[str]:
        """Stream response tokens."""

        async for chunk in await self._async_client.chat(
            model=model,
            messages=messages,
            stream=True
        ):
            if chunk.get("message", {}).get("content"):
                yield chunk["message"]["content"]

    async def chat_stream(
        self,
        model: str,
        messages: list[dict],
        tools: list[dict] = None,
        on_token: Optional[Callable[[str], None]] = None
    ) -> StreamingResponse:
        """Stream chat response with tool support.

        Args:
            model: Model name to use
            messages: Conversation messages
            tools: Tool definitions (optional)
            on_token: Callback called for each token (optional)

        Returns:
            StreamingResponse with accumulated content and tool calls
        """
        kwargs = {
            "model": model,
            "messages": messages,
            "stream": True
        }
        if tools:
            kwargs["tools"] = tools

        log.info("ollama_stream_request", model=model, num_messages=len(messages))

        result = StreamingResponse(model=model)

        async for chunk in await self._async_client.chat(**kwargs):
            # Accumulate content
            token = chunk.get("message", {}).get("content", "")
            if token:
                result.content += token
                if on_token:
                    on_token(token)

            # Check for tool calls (usually in final chunk)
            tool_calls = chunk.get("message", {}).get("tool_calls")
            if tool_calls:
                result.tool_calls = tool_calls

            # Check if done
            if chunk.get("done", False):
                result.done = True
                result.model = chunk.get("model", model)

        log.info("ollama_stream_complete",
                 model=model,
                 content_length=len(result.content),
                 has_tool_calls=result.tool_calls is not None)

        return result

    def list_models(self) -> list[str]:
        """List available models."""
        response = self._client.list()
        return [m.model for m in response.models]
