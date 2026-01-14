"""Local embeddings using Ollama's nomic-embed-text."""

import ollama
from typing import Optional
import numpy as np
import structlog

log = structlog.get_logger()


class LocalEmbedder:
    """Generate embeddings locally via Ollama."""

    def __init__(
        self,
        model: str = "nomic-embed-text",
        host: str = "http://localhost:11434"
    ):
        self.model = model
        self.client = ollama.Client(host=host)
        self._dimension: Optional[int] = None

    @property
    def dimension(self) -> int:
        """Get embedding dimension (768 for nomic-embed-text)."""
        if self._dimension is None:
            # Get dimension from a test embedding
            test = self.embed("test")
            self._dimension = len(test)
            log.info("embedder_dimension_detected", dimension=self._dimension)
        return self._dimension

    def embed(self, text: str) -> list[float]:
        """Embed a single text."""
        try:
            response = self.client.embeddings(
                model=self.model,
                prompt=text
            )
            return response["embedding"]
        except Exception as e:
            log.error("embedding_failed", error=str(e))
            raise

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed multiple texts.

        Note: Ollama doesn't support batching yet, so this is sequential.
        """
        return [self.embed(t) for t in texts]

    def similarity(self, a: list[float], b: list[float]) -> float:
        """Cosine similarity between two embeddings."""
        a_arr = np.array(a)
        b_arr = np.array(b)
        return float(
            np.dot(a_arr, b_arr) / (np.linalg.norm(a_arr) * np.linalg.norm(b_arr))
        )
