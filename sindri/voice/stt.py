"""Speech-to-text module using Whisper for local inference.

Supports multiple Whisper model sizes for different speed/accuracy trade-offs.
Uses faster-whisper for efficient CPU/GPU inference.
"""

import asyncio
import io
import os
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import AsyncIterator, Callable, Optional, Union

import structlog

log = structlog.get_logger()


class WhisperModel(Enum):
    """Available Whisper model sizes."""

    TINY = "tiny"           # ~39M params, fastest
    BASE = "base"           # ~74M params
    SMALL = "small"         # ~244M params
    MEDIUM = "medium"       # ~769M params
    LARGE = "large-v3"      # ~1.55B params, most accurate

    @property
    def vram_mb(self) -> int:
        """Estimated VRAM usage in MB."""
        vram_map = {
            "tiny": 390,
            "base": 500,
            "small": 1000,
            "medium": 2600,
            "large-v3": 4000,
        }
        return vram_map.get(self.value, 1000)


@dataclass
class TranscriptionResult:
    """Result from speech-to-text transcription."""

    text: str
    language: str = "en"
    confidence: float = 1.0
    duration_seconds: float = 0.0
    segments: list = field(default_factory=list)
    processing_time_ms: float = 0.0

    @property
    def is_empty(self) -> bool:
        """Check if transcription is empty or silence."""
        return not self.text.strip()


@dataclass
class AudioConfig:
    """Configuration for audio capture."""

    sample_rate: int = 16000  # Whisper expects 16kHz
    channels: int = 1         # Mono
    chunk_duration_ms: int = 30  # Chunk size for streaming
    vad_threshold: float = 0.5   # Voice activity detection threshold
    silence_duration_ms: int = 1500  # Silence before stopping
    max_duration_seconds: float = 30.0  # Maximum recording length


class SpeechToText:
    """Speech-to-text transcription using Whisper.

    This class provides:
    - Local Whisper inference via faster-whisper
    - Multiple model sizes for speed/accuracy trade-offs
    - Streaming transcription support
    - Voice activity detection
    - Language detection

    Example:
        stt = SpeechToText(model=WhisperModel.BASE)
        await stt.load_model()

        result = await stt.transcribe_file("audio.wav")
        print(result.text)

        # Or with microphone
        result = await stt.record_and_transcribe()
    """

    def __init__(
        self,
        model: WhisperModel = WhisperModel.BASE,
        device: str = "auto",
        compute_type: str = "auto",
        language: Optional[str] = None,
    ):
        """Initialize STT with model configuration.

        Args:
            model: Whisper model size to use
            device: Device to run on ("cpu", "cuda", "auto")
            compute_type: Precision ("float16", "int8", "auto")
            language: Force specific language, or None for auto-detect
        """
        self.model_size = model
        self.device = device
        self.compute_type = compute_type
        self.language = language
        self._model = None
        self._audio_config = AudioConfig()

    async def load_model(self) -> bool:
        """Load the Whisper model.

        Returns:
            True if model loaded successfully
        """
        try:
            # Import faster-whisper (optional dependency)
            from faster_whisper import WhisperModel as FasterWhisper

            # Determine device
            device = self.device
            if device == "auto":
                try:
                    import torch
                    device = "cuda" if torch.cuda.is_available() else "cpu"
                except ImportError:
                    device = "cpu"

            # Determine compute type
            compute_type = self.compute_type
            if compute_type == "auto":
                compute_type = "float16" if device == "cuda" else "int8"

            log.info(
                "loading_whisper_model",
                model=self.model_size.value,
                device=device,
                compute_type=compute_type,
            )

            # Load model (runs in thread pool to avoid blocking)
            loop = asyncio.get_event_loop()
            self._model = await loop.run_in_executor(
                None,
                lambda: FasterWhisper(
                    self.model_size.value,
                    device=device,
                    compute_type=compute_type,
                )
            )

            log.info("whisper_model_loaded", model=self.model_size.value)
            return True

        except ImportError:
            log.error(
                "faster_whisper_not_installed",
                help="Install with: pip install faster-whisper",
            )
            return False
        except Exception as e:
            log.error("whisper_load_failed", error=str(e))
            return False

    async def unload_model(self) -> None:
        """Unload the model to free memory."""
        if self._model is not None:
            del self._model
            self._model = None
            log.info("whisper_model_unloaded")

    @property
    def is_loaded(self) -> bool:
        """Check if model is loaded."""
        return self._model is not None

    async def transcribe_file(
        self,
        audio_path: Union[str, Path],
        task: str = "transcribe",
    ) -> TranscriptionResult:
        """Transcribe an audio file.

        Args:
            audio_path: Path to audio file (wav, mp3, etc.)
            task: "transcribe" or "translate" (to English)

        Returns:
            TranscriptionResult with text and metadata
        """
        if not self.is_loaded:
            await self.load_model()

        start_time = datetime.now()

        try:
            # Run transcription in thread pool
            loop = asyncio.get_event_loop()

            def do_transcribe():
                segments, info = self._model.transcribe(
                    str(audio_path),
                    language=self.language,
                    task=task,
                    beam_size=5,
                    vad_filter=True,
                )
                return list(segments), info

            segments, info = await loop.run_in_executor(None, do_transcribe)

            # Build result
            text_parts = []
            segment_data = []

            for segment in segments:
                text_parts.append(segment.text)
                segment_data.append({
                    "start": segment.start,
                    "end": segment.end,
                    "text": segment.text,
                    "confidence": segment.avg_logprob,
                })

            processing_time = (datetime.now() - start_time).total_seconds() * 1000

            return TranscriptionResult(
                text=" ".join(text_parts).strip(),
                language=info.language,
                confidence=sum(s.avg_logprob for s in segments) / len(segments) if segments else 0,
                duration_seconds=info.duration,
                segments=segment_data,
                processing_time_ms=processing_time,
            )

        except Exception as e:
            log.error("transcription_failed", error=str(e))
            return TranscriptionResult(text="", confidence=0)

    async def transcribe_audio(
        self,
        audio_data: bytes,
        sample_rate: int = 16000,
        task: str = "transcribe",
    ) -> TranscriptionResult:
        """Transcribe raw audio data.

        Args:
            audio_data: Raw PCM audio bytes (16-bit, mono)
            sample_rate: Audio sample rate
            task: "transcribe" or "translate"

        Returns:
            TranscriptionResult
        """
        # Write to temporary file for faster-whisper
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            temp_path = f.name

            # Write WAV header and data
            import wave
            with wave.open(f, "wb") as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)  # 16-bit
                wav.setframerate(sample_rate)
                wav.writeframes(audio_data)

        try:
            result = await self.transcribe_file(temp_path, task)
            return result
        finally:
            os.unlink(temp_path)

    async def record_and_transcribe(
        self,
        max_duration: Optional[float] = None,
        on_listening: Optional[Callable[[], None]] = None,
        on_speech_detected: Optional[Callable[[], None]] = None,
        on_silence: Optional[Callable[[], None]] = None,
    ) -> TranscriptionResult:
        """Record from microphone and transcribe.

        Args:
            max_duration: Maximum recording duration in seconds
            on_listening: Callback when listening starts
            on_speech_detected: Callback when speech is detected
            on_silence: Callback when silence is detected

        Returns:
            TranscriptionResult
        """
        max_duration = max_duration or self._audio_config.max_duration_seconds

        try:
            # Import pyaudio (optional dependency)
            import pyaudio
        except ImportError:
            log.error(
                "pyaudio_not_installed",
                help="Install with: pip install pyaudio",
            )
            return TranscriptionResult(text="", confidence=0)

        # Audio capture configuration
        chunk_size = int(
            self._audio_config.sample_rate *
            self._audio_config.chunk_duration_ms / 1000
        )

        audio = pyaudio.PyAudio()

        try:
            stream = audio.open(
                format=pyaudio.paInt16,
                channels=self._audio_config.channels,
                rate=self._audio_config.sample_rate,
                input=True,
                frames_per_buffer=chunk_size,
            )

            if on_listening:
                on_listening()

            log.info("recording_started")

            # Record audio with simple energy-based VAD
            frames = []
            silence_chunks = 0
            speech_detected = False
            max_chunks = int(
                max_duration * 1000 / self._audio_config.chunk_duration_ms
            )
            silence_threshold_chunks = int(
                self._audio_config.silence_duration_ms /
                self._audio_config.chunk_duration_ms
            )

            for _ in range(max_chunks):
                data = stream.read(chunk_size, exception_on_overflow=False)
                frames.append(data)

                # Simple energy-based VAD
                import array
                audio_array = array.array('h', data)
                energy = sum(abs(x) for x in audio_array) / len(audio_array)

                # Adaptive threshold
                is_speech = energy > 500  # Simple threshold

                if is_speech:
                    if not speech_detected:
                        speech_detected = True
                        if on_speech_detected:
                            on_speech_detected()
                    silence_chunks = 0
                else:
                    silence_chunks += 1

                # Stop after sustained silence (only after speech detected)
                if speech_detected and silence_chunks >= silence_threshold_chunks:
                    if on_silence:
                        on_silence()
                    break

            stream.stop_stream()
            stream.close()

            log.info("recording_stopped", frames=len(frames))

            # Combine frames and transcribe
            audio_data = b"".join(frames)
            return await self.transcribe_audio(
                audio_data,
                self._audio_config.sample_rate,
            )

        finally:
            audio.terminate()

    async def stream_transcription(
        self,
        audio_stream: AsyncIterator[bytes],
    ) -> AsyncIterator[TranscriptionResult]:
        """Stream transcription from audio chunks.

        Yields partial transcriptions as audio comes in.

        Args:
            audio_stream: Async iterator yielding audio chunks

        Yields:
            TranscriptionResult for each processed segment
        """
        if not self.is_loaded:
            await self.load_model()

        buffer = b""
        buffer_duration_target = 2.0  # Process every 2 seconds
        bytes_per_second = self._audio_config.sample_rate * 2  # 16-bit mono

        async for chunk in audio_stream:
            buffer += chunk

            # Process when we have enough audio
            buffer_duration = len(buffer) / bytes_per_second
            if buffer_duration >= buffer_duration_target:
                result = await self.transcribe_audio(buffer)
                if not result.is_empty:
                    yield result
                buffer = b""

        # Process remaining buffer
        if buffer:
            result = await self.transcribe_audio(buffer)
            if not result.is_empty:
                yield result
