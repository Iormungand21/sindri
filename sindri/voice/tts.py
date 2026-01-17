"""Text-to-speech module with multiple engine support.

Supports:
- pyttsx3: Cross-platform, works offline (espeak/nsss/sapi5 backends)
- piper: High-quality neural TTS (optional, requires piper-tts)
- espeak-ng: Fast, lightweight synthesis (direct CLI)
"""

import asyncio
import importlib.util
import os
import shutil
import tempfile
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import AsyncIterator, Optional, Union

import structlog

log = structlog.get_logger()


class TTSEngine(Enum):
    """Available TTS engines."""

    PYTTSX3 = "pyttsx3"  # Cross-platform, uses system TTS
    PIPER = "piper"  # Neural TTS with piper-tts
    ESPEAK = "espeak"  # Fast, lightweight espeak-ng


@dataclass
class VoiceConfig:
    """Configuration for TTS voice."""

    engine: TTSEngine = TTSEngine.PYTTSX3
    voice_id: Optional[str] = None  # Engine-specific voice ID
    rate: int = 175  # Words per minute
    pitch: int = 50  # 0-100 scale
    volume: float = 1.0  # 0.0-1.0
    language: str = "en"  # ISO language code

    # Piper-specific
    piper_model: str = "en_US-lessac-medium"  # Default piper model

    @classmethod
    def fast(cls) -> "VoiceConfig":
        """Create config optimized for speed."""
        return cls(engine=TTSEngine.ESPEAK, rate=220)

    @classmethod
    def quality(cls) -> "VoiceConfig":
        """Create config optimized for quality."""
        return cls(engine=TTSEngine.PIPER, rate=160)


class TextToSpeech:
    """Text-to-speech synthesis with multiple backends.

    This class provides:
    - Multiple TTS engine support (pyttsx3, piper, espeak)
    - Async-friendly operation
    - Audio output to speakers or file
    - Voice customization

    Example:
        tts = TextToSpeech(VoiceConfig())
        await tts.speak("Hello, I am Sindri")

        # Or save to file
        await tts.synthesize_to_file("Hello", "output.wav")
    """

    def __init__(self, config: Optional[VoiceConfig] = None):
        """Initialize TTS with configuration.

        Args:
            config: Voice configuration (uses defaults if None)
        """
        self.config = config or VoiceConfig()
        self._engine = None
        self._available_engines: list[TTSEngine] = []

    async def initialize(self) -> bool:
        """Initialize the TTS engine.

        Returns:
            True if initialization successful
        """
        # Check available engines
        self._available_engines = await self._detect_available_engines()

        if not self._available_engines:
            log.error("no_tts_engines_available")
            return False

        # Use configured engine if available, else fall back
        if self.config.engine in self._available_engines:
            engine = self.config.engine
        else:
            engine = self._available_engines[0]
            log.warning(
                "tts_engine_fallback",
                requested=self.config.engine.value,
                using=engine.value,
            )
            self.config.engine = engine

        log.info(
            "tts_initialized",
            engine=engine.value,
            available=[e.value for e in self._available_engines],
        )
        return True

    async def _detect_available_engines(self) -> list[TTSEngine]:
        """Detect which TTS engines are available."""
        available = []

        # Check pyttsx3
        if importlib.util.find_spec("pyttsx3"):
            available.append(TTSEngine.PYTTSX3)

        # Check piper
        if shutil.which("piper"):
            available.append(TTSEngine.PIPER)

        # Check espeak-ng
        if shutil.which("espeak-ng") or shutil.which("espeak"):
            available.append(TTSEngine.ESPEAK)

        return available

    @property
    def available_engines(self) -> list[TTSEngine]:
        """Get list of available TTS engines."""
        return self._available_engines

    async def speak(self, text: str) -> bool:
        """Speak text through default audio output.

        Args:
            text: Text to speak

        Returns:
            True if successful
        """
        if not text.strip():
            return True

        log.debug("tts_speaking", text=text[:50], engine=self.config.engine.value)

        try:
            if self.config.engine == TTSEngine.PYTTSX3:
                return await self._speak_pyttsx3(text)
            elif self.config.engine == TTSEngine.PIPER:
                return await self._speak_piper(text)
            elif self.config.engine == TTSEngine.ESPEAK:
                return await self._speak_espeak(text)
            else:
                log.error("unknown_tts_engine", engine=self.config.engine.value)
                return False
        except Exception as e:
            log.error("tts_speak_failed", error=str(e))
            return False

    async def _speak_pyttsx3(self, text: str) -> bool:
        """Speak using pyttsx3."""
        try:
            import pyttsx3
        except ImportError:
            log.error("pyttsx3_not_installed")
            return False

        loop = asyncio.get_event_loop()

        def do_speak():
            engine = pyttsx3.init()

            # Apply settings
            engine.setProperty("rate", self.config.rate)
            engine.setProperty("volume", self.config.volume)

            # Set voice if specified
            if self.config.voice_id:
                engine.setProperty("voice", self.config.voice_id)

            engine.say(text)
            engine.runAndWait()
            engine.stop()

        await loop.run_in_executor(None, do_speak)
        return True

    async def _speak_piper(self, text: str) -> bool:
        """Speak using piper-tts."""
        # Synthesize to temp file, then play
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            temp_path = f.name

        try:
            success = await self.synthesize_to_file(text, temp_path)
            if not success:
                return False

            # Play the audio file
            return await self._play_audio(temp_path)
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)

    async def _speak_espeak(self, text: str) -> bool:
        """Speak using espeak-ng."""
        espeak_cmd = "espeak-ng" if shutil.which("espeak-ng") else "espeak"

        cmd = [
            espeak_cmd,
            "-s",
            str(self.config.rate),
            "-p",
            str(self.config.pitch),
            "-a",
            str(int(self.config.volume * 200)),  # espeak uses 0-200
            "-v",
            self.config.language,
            text,
        ]

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await process.wait()
        return process.returncode == 0

    async def synthesize_to_file(
        self,
        text: str,
        output_path: Union[str, Path],
    ) -> bool:
        """Synthesize speech to an audio file.

        Args:
            text: Text to synthesize
            output_path: Path to output WAV file

        Returns:
            True if successful
        """
        output_path = Path(output_path)

        try:
            if self.config.engine == TTSEngine.PYTTSX3:
                return await self._synthesize_pyttsx3(text, output_path)
            elif self.config.engine == TTSEngine.PIPER:
                return await self._synthesize_piper(text, output_path)
            elif self.config.engine == TTSEngine.ESPEAK:
                return await self._synthesize_espeak(text, output_path)
            else:
                log.error("unknown_tts_engine", engine=self.config.engine.value)
                return False
        except Exception as e:
            log.error("tts_synthesize_failed", error=str(e))
            return False

    async def _synthesize_pyttsx3(self, text: str, output_path: Path) -> bool:
        """Synthesize using pyttsx3."""
        try:
            import pyttsx3
        except ImportError:
            return False

        loop = asyncio.get_event_loop()

        def do_synthesize():
            engine = pyttsx3.init()
            engine.setProperty("rate", self.config.rate)
            engine.setProperty("volume", self.config.volume)
            if self.config.voice_id:
                engine.setProperty("voice", self.config.voice_id)
            engine.save_to_file(text, str(output_path))
            engine.runAndWait()
            engine.stop()

        await loop.run_in_executor(None, do_synthesize)
        return output_path.exists()

    async def _synthesize_piper(self, text: str, output_path: Path) -> bool:
        """Synthesize using piper-tts."""
        cmd = [
            "piper",
            "--model",
            self.config.piper_model,
            "--output_file",
            str(output_path),
        ]

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await process.communicate(input=text.encode())
        return process.returncode == 0 and output_path.exists()

    async def _synthesize_espeak(self, text: str, output_path: Path) -> bool:
        """Synthesize using espeak-ng."""
        espeak_cmd = "espeak-ng" if shutil.which("espeak-ng") else "espeak"

        cmd = [
            espeak_cmd,
            "-s",
            str(self.config.rate),
            "-p",
            str(self.config.pitch),
            "-a",
            str(int(self.config.volume * 200)),
            "-v",
            self.config.language,
            "-w",
            str(output_path),
            text,
        ]

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await process.wait()
        return process.returncode == 0 and output_path.exists()

    async def _play_audio(self, audio_path: Union[str, Path]) -> bool:
        """Play an audio file through default audio output."""
        audio_path = str(audio_path)

        # Try different audio players
        players = [
            ["aplay", audio_path],  # ALSA (Linux)
            ["paplay", audio_path],  # PulseAudio
            ["pw-play", audio_path],  # PipeWire
            ["afplay", audio_path],  # macOS
            ["ffplay", "-nodisp", "-autoexit", audio_path],  # FFmpeg
        ]

        for cmd in players:
            if shutil.which(cmd[0]):
                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                )
                await process.wait()
                if process.returncode == 0:
                    return True

        log.error("no_audio_player_found")
        return False

    async def list_voices(self) -> list[dict]:
        """List available voices for current engine.

        Returns:
            List of voice info dicts with id, name, language
        """
        if self.config.engine == TTSEngine.PYTTSX3:
            return await self._list_pyttsx3_voices()
        elif self.config.engine == TTSEngine.ESPEAK:
            return await self._list_espeak_voices()
        else:
            return []

    async def _list_pyttsx3_voices(self) -> list[dict]:
        """List pyttsx3 voices."""
        try:
            import pyttsx3
        except ImportError:
            return []

        loop = asyncio.get_event_loop()

        def get_voices():
            engine = pyttsx3.init()
            voices = engine.getProperty("voices")
            engine.stop()
            return [
                {
                    "id": v.id,
                    "name": v.name,
                    "languages": v.languages,
                    "gender": v.gender,
                }
                for v in voices
            ]

        return await loop.run_in_executor(None, get_voices)

    async def _list_espeak_voices(self) -> list[dict]:
        """List espeak voices."""
        espeak_cmd = "espeak-ng" if shutil.which("espeak-ng") else "espeak"

        process = await asyncio.create_subprocess_exec(
            espeak_cmd,
            "--voices",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await process.communicate()

        voices = []
        for line in stdout.decode().split("\n")[1:]:  # Skip header
            if line.strip():
                parts = line.split()
                if len(parts) >= 4:
                    voices.append(
                        {
                            "id": parts[4] if len(parts) > 4 else parts[3],
                            "name": parts[3],
                            "language": parts[1],
                        }
                    )
        return voices

    async def stream_speak(
        self,
        text_stream: AsyncIterator[str],
        sentence_mode: bool = True,
    ) -> None:
        """Stream speech as text comes in.

        Args:
            text_stream: Async iterator yielding text chunks
            sentence_mode: If True, buffer until sentence boundaries
        """
        buffer = ""
        sentence_ends = ".!?:;\n"

        async for chunk in text_stream:
            buffer += chunk

            if sentence_mode:
                # Check for sentence boundaries
                for i, char in enumerate(buffer):
                    if char in sentence_ends:
                        sentence = buffer[: i + 1].strip()
                        if sentence:
                            await self.speak(sentence)
                        buffer = buffer[i + 1 :]
                        break
            else:
                # Speak immediately
                if buffer.strip():
                    await self.speak(buffer)
                    buffer = ""

        # Speak remaining text
        if buffer.strip():
            await self.speak(buffer)
