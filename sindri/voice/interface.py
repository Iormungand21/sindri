"""Voice interface module for hands-free interaction with Sindri.

Provides a voice-controlled interface that:
- Listens for speech commands via Whisper
- Executes tasks through the agent system
- Responds with synthesized speech
- Supports wake words and continuous listening
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import AsyncIterator, Callable, Optional

import structlog

from sindri.voice.stt import SpeechToText, WhisperModel, TranscriptionResult
from sindri.voice.tts import TextToSpeech, VoiceConfig, TTSEngine

log = structlog.get_logger()


class VoiceMode(Enum):
    """Voice interface operating modes."""

    PUSH_TO_TALK = "push_to_talk"   # Manual activation
    WAKE_WORD = "wake_word"         # Activate on wake word
    CONTINUOUS = "continuous"        # Always listening


@dataclass
class VoiceSession:
    """Represents a voice interaction session."""

    id: str
    started_at: datetime = field(default_factory=datetime.now)
    mode: VoiceMode = VoiceMode.PUSH_TO_TALK
    turns: list = field(default_factory=list)
    wake_word: str = "sindri"

    @property
    def turn_count(self) -> int:
        return len(self.turns)


@dataclass
class VoiceTurn:
    """A single turn in voice interaction."""

    user_audio_path: Optional[str] = None
    user_text: str = ""
    response_text: str = ""
    response_audio_path: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)
    processing_time_ms: float = 0.0


class VoiceInterface:
    """Voice-controlled interface for Sindri.

    This class provides:
    - Wake word detection ("Hey Sindri")
    - Speech-to-text command recognition
    - Text-to-speech responses
    - Integration with agent execution

    Example:
        interface = VoiceInterface()
        await interface.start()

        # Listen for commands
        async for turn in interface.listen():
            print(f"User said: {turn.user_text}")
            print(f"Response: {turn.response_text}")

    Modes:
        - PUSH_TO_TALK: Call listen_once() to capture single command
        - WAKE_WORD: Listens for "Hey Sindri" to activate
        - CONTINUOUS: Always listening (use with caution)
    """

    def __init__(
        self,
        stt_model: WhisperModel = WhisperModel.BASE,
        tts_config: Optional[VoiceConfig] = None,
        mode: VoiceMode = VoiceMode.PUSH_TO_TALK,
        wake_word: str = "sindri",
        on_command: Optional[Callable[[str], str]] = None,
    ):
        """Initialize voice interface.

        Args:
            stt_model: Whisper model for speech recognition
            tts_config: Text-to-speech configuration
            mode: Operating mode (push_to_talk, wake_word, continuous)
            wake_word: Word/phrase to activate in wake_word mode
            on_command: Callback to execute commands, returns response
        """
        self.stt = SpeechToText(model=stt_model)
        self.tts = TextToSpeech(tts_config or VoiceConfig())
        self.mode = mode
        self.wake_word = wake_word.lower()
        self.on_command = on_command

        self._running = False
        self._session: Optional[VoiceSession] = None
        self._callbacks: dict[str, list[Callable]] = {
            "listening": [],
            "speech_detected": [],
            "transcribed": [],
            "responding": [],
            "error": [],
        }

    async def start(self) -> bool:
        """Start the voice interface.

        Loads models and initializes audio.

        Returns:
            True if started successfully
        """
        log.info("voice_interface_starting", mode=self.mode.value)

        # Initialize STT
        if not await self.stt.load_model():
            log.error("stt_init_failed")
            return False

        # Initialize TTS
        if not await self.tts.initialize():
            log.error("tts_init_failed")
            return False

        # Create session
        import uuid
        self._session = VoiceSession(
            id=str(uuid.uuid4()),
            mode=self.mode,
            wake_word=self.wake_word,
        )

        self._running = True
        log.info(
            "voice_interface_started",
            session_id=self._session.id,
            stt_model=self.stt.model_size.value,
            tts_engine=self.tts.config.engine.value,
        )

        # Announce ready
        await self.tts.speak("Voice interface ready")
        return True

    async def stop(self) -> None:
        """Stop the voice interface."""
        self._running = False

        # Unload models
        await self.stt.unload_model()

        log.info("voice_interface_stopped")

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def session(self) -> Optional[VoiceSession]:
        return self._session

    def on(self, event: str, callback: Callable) -> None:
        """Register callback for voice events.

        Events:
            - listening: When waiting for speech
            - speech_detected: When speech begins
            - transcribed: When transcription complete
            - responding: When generating response
            - error: When an error occurs
        """
        if event in self._callbacks:
            self._callbacks[event].append(callback)

    def _emit(self, event_name: str, *args) -> None:
        """Emit event to registered callbacks."""
        for callback in self._callbacks.get(event_name, []):
            try:
                callback(*args)
            except Exception as e:
                log.error("callback_error", event_name=event_name, error=str(e))

    async def listen_once(self) -> Optional[VoiceTurn]:
        """Listen for a single voice command.

        Returns:
            VoiceTurn with transcription and response, or None on error
        """
        if not self._running:
            await self.start()

        turn = VoiceTurn()
        start_time = datetime.now()

        # Record and transcribe
        self._emit("listening")

        result = await self.stt.record_and_transcribe(
            on_listening=lambda: self._emit("listening"),
            on_speech_detected=lambda: self._emit("speech_detected"),
        )

        if result.is_empty:
            log.debug("no_speech_detected")
            return None

        turn.user_text = result.text
        self._emit("transcribed", result.text)

        log.info(
            "voice_command_received",
            text=result.text,
            confidence=result.confidence,
        )

        # Execute command if handler provided
        if self.on_command:
            self._emit("responding")
            try:
                response = self.on_command(turn.user_text)
                turn.response_text = response

                # Speak response
                await self.tts.speak(response)

            except Exception as e:
                log.error("command_execution_failed", error=str(e))
                self._emit("error", str(e))
                turn.response_text = f"Sorry, there was an error: {e}"
                await self.tts.speak("Sorry, I encountered an error.")

        turn.processing_time_ms = (datetime.now() - start_time).total_seconds() * 1000

        # Add to session
        if self._session:
            self._session.turns.append(turn)

        return turn

    async def listen(self) -> AsyncIterator[VoiceTurn]:
        """Listen for voice commands continuously.

        Yields VoiceTurn for each interaction.
        Behavior depends on mode:
        - PUSH_TO_TALK: Yields after each listen_once call
        - WAKE_WORD: Yields after wake word detected
        - CONTINUOUS: Yields continuously

        Example:
            async for turn in interface.listen():
                print(f"You said: {turn.user_text}")
        """
        if not self._running:
            if not await self.start():
                return

        while self._running:
            try:
                if self.mode == VoiceMode.WAKE_WORD:
                    # Listen for wake word first
                    turn = await self._listen_for_wake_word()
                else:
                    # Direct listening
                    turn = await self.listen_once()

                if turn:
                    yield turn

                # Small delay between listens
                await asyncio.sleep(0.5)

            except asyncio.CancelledError:
                break
            except Exception as e:
                log.error("listen_error", error=str(e))
                self._emit("error", str(e))
                await asyncio.sleep(1.0)  # Back off on errors

    async def _listen_for_wake_word(self) -> Optional[VoiceTurn]:
        """Listen specifically for wake word activation."""
        log.debug("listening_for_wake_word", wake_word=self.wake_word)

        # Record short snippet
        result = await self.stt.record_and_transcribe(max_duration=3.0)

        if result.is_empty:
            return None

        text_lower = result.text.lower()

        # Check for wake word
        if self.wake_word in text_lower:
            # Extract command after wake word
            idx = text_lower.find(self.wake_word)
            command = result.text[idx + len(self.wake_word):].strip()

            if command:
                # Wake word with command
                log.info("wake_word_with_command", command=command)
                turn = VoiceTurn(user_text=command)

                if self.on_command:
                    response = self.on_command(command)
                    turn.response_text = response
                    await self.tts.speak(response)

                if self._session:
                    self._session.turns.append(turn)

                return turn
            else:
                # Just wake word, wait for command
                await self.tts.speak("Yes?")
                return await self.listen_once()

        return None

    async def speak(self, text: str) -> bool:
        """Speak text using TTS.

        Args:
            text: Text to speak

        Returns:
            True if successful
        """
        return await self.tts.speak(text)

    async def transcribe_file(self, audio_path: str) -> TranscriptionResult:
        """Transcribe an audio file.

        Args:
            audio_path: Path to audio file

        Returns:
            TranscriptionResult
        """
        if not self.stt.is_loaded:
            await self.stt.load_model()
        return await self.stt.transcribe_file(audio_path)


class VoiceCommand:
    """Decorator for voice command handlers."""

    _handlers: dict[str, Callable] = {}

    @classmethod
    def register(cls, trigger: str):
        """Register a voice command handler.

        Args:
            trigger: Phrase to trigger command (case-insensitive)
        """
        def decorator(func: Callable[[str], str]):
            cls._handlers[trigger.lower()] = func
            return func
        return decorator

    @classmethod
    def match(cls, text: str) -> Optional[tuple[Callable, str]]:
        """Match text to a command handler.

        Returns:
            (handler, remaining_text) or None
        """
        text_lower = text.lower()
        for trigger, handler in cls._handlers.items():
            if text_lower.startswith(trigger):
                remaining = text[len(trigger):].strip()
                return handler, remaining
        return None


# Built-in voice commands
@VoiceCommand.register("run")
def cmd_run(task: str) -> str:
    """Run a task with Sindri."""
    return f"I'll run the task: {task}"


@VoiceCommand.register("list agents")
def cmd_list_agents(_: str) -> str:
    """List available agents."""
    return "Available agents: Brokkr the orchestrator, Huginn the coder, Mimir the reviewer, and Ratatoskr the executor."


@VoiceCommand.register("stop")
def cmd_stop(_: str) -> str:
    """Stop current operation."""
    return "Stopping current operation."


@VoiceCommand.register("help")
def cmd_help(_: str) -> str:
    """Get help."""
    return (
        "Available voice commands: "
        "Say 'run' followed by a task, "
        "'list agents' to see agents, "
        "'stop' to cancel, "
        "or 'help' for this message."
    )
