"""Voice interface module for Sindri.

This module provides infrastructure for:
- Speech-to-text using Whisper (local inference)
- Text-to-speech using pyttsx3/piper (local inference)
- Voice-controlled interaction with agents
"""

from sindri.voice.stt import (
    SpeechToText,
    WhisperModel,
    TranscriptionResult,
)
from sindri.voice.tts import (
    TextToSpeech,
    TTSEngine,
    VoiceConfig,
)
from sindri.voice.interface import (
    VoiceInterface,
    VoiceMode,
    VoiceSession,
)

__all__ = [
    # STT
    "SpeechToText",
    "WhisperModel",
    "TranscriptionResult",
    # TTS
    "TextToSpeech",
    "TTSEngine",
    "VoiceConfig",
    # Interface
    "VoiceInterface",
    "VoiceMode",
    "VoiceSession",
]
