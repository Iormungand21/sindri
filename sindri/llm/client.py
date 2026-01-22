"""Async Ollama client wrapper."""

import ollama
from dataclasses import dataclass
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
                role="assistant", content=self.content, tool_calls=self.tool_calls
            ),
            model=self.model,
            done=self.done,
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
        tools: list[dict] = None,
        images: list[str] = None,
        options: Optional[dict] = None,
    ) -> Response:
        """Send chat request to Ollama.

        Args:
            model: Model name to use
            messages: Conversation messages
            tools: Tool definitions (optional)
            images: Image paths or base64 data for vision models (optional).
                    Images are added to the last user message.
            options: Ollama options like num_ctx, temperature, etc. (optional)

        Returns:
            Response with message content and optional tool calls
        """
        # If images provided, add them to the last user message
        if images:
            messages = self._add_images_to_messages(messages, images)

        kwargs = {
            "model": model,
            "messages": messages,
        }
        if tools:
            kwargs["tools"] = tools
        if options:
            kwargs["options"] = options

        log.info(
            "ollama_chat_request",
            model=model,
            num_messages=len(messages),
            has_images=images is not None,
            options=options,
        )

        response = await self._async_client.chat(**kwargs)

        log.debug(
            "ollama_response_keys",
            keys=list(response.keys()) if isinstance(response, dict) else "not_dict",
        )
        log.debug(
            "ollama_message_keys",
            keys=(
                list(response.get("message", {}).keys())
                if isinstance(response, dict)
                else "not_dict"
            ),
        )

        tool_calls = response["message"].get("tool_calls")
        log.info("ollama_tool_calls", tool_calls=tool_calls)

        return Response(
            message=Message(
                role=response["message"]["role"],
                content=response["message"].get("content", ""),
                tool_calls=tool_calls,
            ),
            model=response["model"],
            done=response.get("done", True),
        )

    async def stream(self, model: str, messages: list[dict]) -> AsyncIterator[str]:
        """Stream response tokens."""

        async for chunk in await self._async_client.chat(
            model=model, messages=messages, stream=True
        ):
            if chunk.get("message", {}).get("content"):
                yield chunk["message"]["content"]

    async def chat_stream(
        self,
        model: str,
        messages: list[dict],
        tools: list[dict] = None,
        images: list[str] = None,
        on_token: Optional[Callable[[str], None]] = None,
        options: Optional[dict] = None,
    ) -> StreamingResponse:
        """Stream chat response with tool support.

        Args:
            model: Model name to use
            messages: Conversation messages
            tools: Tool definitions (optional)
            images: Image paths or base64 data for vision models (optional).
                    Images are added to the last user message.
            on_token: Callback called for each token (optional)
            options: Ollama options like num_ctx, temperature, etc. (optional)

        Returns:
            StreamingResponse with accumulated content and tool calls
        """
        # If images provided, add them to the last user message
        if images:
            messages = self._add_images_to_messages(messages, images)

        kwargs = {"model": model, "messages": messages, "stream": True}
        if tools:
            kwargs["tools"] = tools
        if options:
            kwargs["options"] = options

        log.info(
            "ollama_stream_request",
            model=model,
            num_messages=len(messages),
            has_images=images is not None,
            options=options,
        )

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

        log.info(
            "ollama_stream_complete",
            model=model,
            content_length=len(result.content),
            has_tool_calls=result.tool_calls is not None,
        )

        return result

    def _add_images_to_messages(
        self, messages: list[dict], images: list[str]
    ) -> list[dict]:
        """Add images to the last user message for vision models.

        Args:
            messages: Original conversation messages
            images: List of image paths or base64-encoded image data

        Returns:
            Copy of messages with images added to last user message
        """
        if not images or not messages:
            return messages

        # Create a copy to avoid modifying the original
        messages = [msg.copy() for msg in messages]

        # Find the last user message and add images
        for msg in reversed(messages):
            if msg.get("role") == "user":
                msg["images"] = images
                log.debug(
                    "added_images_to_message",
                    num_images=len(images),
                    message_index=messages.index(msg),
                )
                break

        return messages

    def list_models(self) -> list[str]:
        """List available models."""
        response = self._client.list()
        return [m.model for m in response.models]

    async def get_model_info(self, model: str) -> dict:
        """Get model information including context length.

        Args:
            model: Model name to query

        Returns:
            Dict with model info including 'context_length' key
        """
        try:
            response = await self._async_client.show(model)

            # Extract context length from model parameters or defaults
            # Ollama stores this in modelinfo or model_info
            model_info = response.get("modelinfo", response.get("model_info", {}))
            details = response.get("details", {})

            # Try to find context length in various locations
            context_length = None

            # Check model_info for context-related keys
            for key in model_info:
                if "context" in key.lower() and "length" in key.lower():
                    context_length = model_info[key]
                    break

            # Default context lengths by model family if not found
            if context_length is None:
                family = details.get("family", "").lower()
                param_size = details.get("parameter_size", "")

                # Common defaults based on model families
                if "qwen" in family or "qwen" in model.lower():
                    context_length = 32768
                elif "llama" in family or "llama" in model.lower():
                    context_length = 8192
                elif "deepseek" in family or "deepseek" in model.lower():
                    context_length = 16384
                elif "mistral" in family or "mistral" in model.lower():
                    context_length = 32768
                else:
                    # Conservative default
                    context_length = 4096

            log.info(
                "model_info_retrieved",
                model=model,
                context_length=context_length,
                family=details.get("family", "unknown"),
            )

            return {
                "name": model,
                "context_length": context_length,
                "family": details.get("family", "unknown"),
                "parameter_size": details.get("parameter_size", "unknown"),
                "quantization": details.get("quantization_level", "unknown"),
                "raw": response,
            }

        except Exception as e:
            log.warning("model_info_failed", model=model, error=str(e))
            # Return conservative defaults on error
            return {
                "name": model,
                "context_length": 4096,
                "family": "unknown",
                "parameter_size": "unknown",
                "quantization": "unknown",
                "raw": {},
            }
