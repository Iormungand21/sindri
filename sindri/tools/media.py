"""Video and audio processing tools for Sindri.

Phase 12 Tier 3 - Universal Tool Expansion.

Provides tools for:
- Audio/video transcription using Whisper
- Subtitle generation (SRT/VTT)
- Format conversion
- Video editing (trim, concat, thumbnails)
- Text-to-speech synthesis
"""

import asyncio
import os
import shutil
import tempfile
from datetime import timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

import structlog

from sindri.tools.base import Tool, ToolResult

if TYPE_CHECKING:
    pass

logger = structlog.get_logger()

# Check for FFmpeg availability (system binary)
FFMPEG_AVAILABLE = shutil.which("ffmpeg") is not None
FFPROBE_AVAILABLE = shutil.which("ffprobe") is not None

# Check for ffmpeg-python library
try:
    import ffmpeg

    FFMPEG_PYTHON_AVAILABLE = True
except ImportError:
    FFMPEG_PYTHON_AVAILABLE = False
    ffmpeg = None  # type: ignore

# Check for Whisper (via voice module)
try:
    from sindri.voice.stt import SpeechToText, TranscriptionResult, WhisperModel

    WHISPER_AVAILABLE = True
except ImportError:
    WHISPER_AVAILABLE = False
    SpeechToText = None  # type: ignore
    TranscriptionResult = None  # type: ignore
    WhisperModel = None  # type: ignore

# Check for TTS (via voice module)
try:
    from sindri.voice.tts import TextToSpeech

    TTS_AVAILABLE = True
except ImportError:
    TTS_AVAILABLE = False
    TextToSpeech = None  # type: ignore

# Supported formats
AUDIO_FORMATS = ["mp3", "wav", "flac", "ogg", "aac", "m4a", "wma", "opus"]
VIDEO_FORMATS = ["mp4", "mkv", "webm", "avi", "mov", "wmv", "flv", "m4v"]
SUBTITLE_FORMATS = ["srt", "vtt"]


def _format_timestamp_srt(seconds: float) -> str:
    """Format seconds as SRT timestamp (HH:MM:SS,mmm)."""
    td = timedelta(seconds=seconds)
    hours = int(td.total_seconds() // 3600)
    minutes = int((td.total_seconds() % 3600) // 60)
    secs = int(td.total_seconds() % 60)
    millis = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def _format_timestamp_vtt(seconds: float) -> str:
    """Format seconds as WebVTT timestamp (HH:MM:SS.mmm)."""
    td = timedelta(seconds=seconds)
    hours = int(td.total_seconds() // 3600)
    minutes = int((td.total_seconds() % 3600) // 60)
    secs = int(td.total_seconds() % 60)
    millis = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}.{millis:03d}"


def _parse_time(time_str: str) -> float:
    """Parse time string to seconds. Accepts HH:MM:SS, MM:SS, or seconds."""
    if isinstance(time_str, (int, float)):
        return float(time_str)

    time_str = str(time_str).strip()

    # Try parsing as float first (seconds)
    try:
        return float(time_str)
    except ValueError:
        pass

    # Parse HH:MM:SS or MM:SS
    parts = time_str.split(":")
    if len(parts) == 3:
        hours, minutes, seconds = parts
        return int(hours) * 3600 + int(minutes) * 60 + float(seconds)
    elif len(parts) == 2:
        minutes, seconds = parts
        return int(minutes) * 60 + float(seconds)
    else:
        raise ValueError(f"Invalid time format: {time_str}")


def _get_file_extension(path: str) -> str:
    """Get lowercase file extension without dot."""
    return os.path.splitext(path)[1].lower().lstrip(".")


def _human_readable_size(size_bytes: int) -> str:
    """Convert bytes to human-readable string."""
    for unit in ["B", "KB", "MB", "GB"]:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


def _human_readable_duration(seconds: float) -> str:
    """Convert seconds to human-readable duration."""
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        minutes = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{minutes}m {secs}s"
    else:
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        return f"{hours}h {minutes}m"


async def _run_ffmpeg_async(
    args: list[str], timeout: float = 300.0
) -> tuple[int, str, str]:
    """Run FFmpeg command asynchronously."""
    cmd = ["ffmpeg", "-y"] + args  # -y to overwrite output

    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    try:
        stdout, stderr = await asyncio.wait_for(
            process.communicate(), timeout=timeout
        )
        return process.returncode or 0, stdout.decode(), stderr.decode()
    except asyncio.TimeoutError:
        process.kill()
        await process.wait()
        raise TimeoutError(f"FFmpeg command timed out after {timeout}s")


async def _get_media_info(path: str) -> dict[str, Any]:
    """Get media file information using ffprobe."""
    if not FFPROBE_AVAILABLE:
        return {}

    cmd = [
        "ffprobe",
        "-v",
        "quiet",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        path,
    ]

    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    stdout, _ = await process.communicate()

    try:
        import json

        return json.loads(stdout.decode())
    except Exception:
        return {}


class AudioTranscribeTool(Tool):
    """Transcribe audio files to text using Whisper."""

    name = "audio_transcribe"
    description = """Transcribe audio file to text using local Whisper model.

Examples:
- Transcribe audio: audio_transcribe(input="speech.mp3")
- With specific model: audio_transcribe(input="audio.wav", model="medium")
- Translate to English: audio_transcribe(input="french.mp3", translate=true)
"""
    parameters = {
        "type": "object",
        "properties": {
            "input": {
                "type": "string",
                "description": "Path to audio file (WAV, MP3, FLAC, OGG, M4A)",
            },
            "model": {
                "type": "string",
                "description": "Whisper model size: tiny, base, small, medium, large (default: base)",
                "enum": ["tiny", "base", "small", "medium", "large"],
            },
            "translate": {
                "type": "boolean",
                "description": "Translate to English instead of transcribing (default: false)",
            },
            "language": {
                "type": "string",
                "description": "Source language code (e.g., 'en', 'es', 'fr'). Auto-detected if not specified.",
            },
        },
        "required": ["input"],
    }

    async def execute(
        self,
        input: str,
        model: str = "base",
        translate: bool = False,
        language: Optional[str] = None,
        **kwargs: Any,
    ) -> ToolResult:
        """Execute audio transcription."""
        if not WHISPER_AVAILABLE:
            return ToolResult(
                success=False,
                output="",
                error="Whisper not available. Install with: pip install 'sindri[voice]'",
            )

        input_path = self._resolve_path(input)

        if not os.path.exists(input_path):
            return ToolResult(
                success=False,
                output="",
                error=f"Input file does not exist: {input}",
            )

        try:
            # Map model name to enum
            model_map = {
                "tiny": WhisperModel.TINY,
                "base": WhisperModel.BASE,
                "small": WhisperModel.SMALL,
                "medium": WhisperModel.MEDIUM,
                "large": WhisperModel.LARGE,
            }
            whisper_model = model_map.get(model, WhisperModel.BASE)

            # Create STT instance
            stt = SpeechToText(model=whisper_model, language=language)
            await stt.load_model()

            try:
                # Transcribe
                task = "translate" if translate else "transcribe"
                result = await stt.transcribe_file(str(input_path), task=task)

                # Build segment info for metadata
                segments = []
                for seg in result.segments:
                    segments.append(
                        {
                            "start": seg.get("start", 0),
                            "end": seg.get("end", 0),
                            "text": seg.get("text", ""),
                        }
                    )

                return ToolResult(
                    success=True,
                    output=result.text,
                    metadata={
                        "language": result.language,
                        "confidence": result.confidence,
                        "duration_seconds": result.duration_seconds,
                        "processing_time_ms": result.processing_time_ms,
                        "segments": segments,
                        "model": model,
                    },
                )
            finally:
                await stt.unload_model()

        except Exception as e:
            logger.error("audio_transcribe_error", error=str(e), input=input)
            return ToolResult(
                success=False,
                output="",
                error=f"Transcription failed: {str(e)}",
            )


class VideoExtractAudioTool(Tool):
    """Extract audio track from video file."""

    name = "video_extract_audio"
    description = """Extract audio track from a video file.

Examples:
- Extract as MP3: video_extract_audio(input="video.mp4", output="audio.mp3")
- Extract as WAV: video_extract_audio(input="movie.mkv", format="wav")
- High quality MP3: video_extract_audio(input="video.mp4", format="mp3", bitrate="320k")
"""
    parameters = {
        "type": "object",
        "properties": {
            "input": {
                "type": "string",
                "description": "Path to video file",
            },
            "output": {
                "type": "string",
                "description": "Output audio file path (optional, auto-generated if not specified)",
            },
            "format": {
                "type": "string",
                "description": "Output audio format: mp3, wav, flac, aac, ogg (default: mp3)",
                "enum": ["mp3", "wav", "flac", "aac", "ogg"],
            },
            "bitrate": {
                "type": "string",
                "description": "Audio bitrate (e.g., '128k', '192k', '320k'). Default: 192k",
            },
        },
        "required": ["input"],
    }

    async def execute(
        self,
        input: str,
        output: Optional[str] = None,
        format: str = "mp3",
        bitrate: str = "192k",
        **kwargs: Any,
    ) -> ToolResult:
        """Execute audio extraction."""
        if not FFMPEG_AVAILABLE:
            return ToolResult(
                success=False,
                output="",
                error="FFmpeg not found. Install with: pacman -S ffmpeg (or apt install ffmpeg)",
            )

        input_path = self._resolve_path(input)

        if not os.path.exists(input_path):
            return ToolResult(
                success=False,
                output="",
                error=f"Input file does not exist: {input}",
            )

        # Generate output path if not specified
        if output:
            output_path = self._resolve_path(output)
        else:
            base = os.path.splitext(input_path)[0]
            output_path = f"{base}_audio.{format}"

        # Ensure output directory exists
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

        try:
            # Build FFmpeg command
            codec_map = {
                "mp3": "libmp3lame",
                "wav": "pcm_s16le",
                "flac": "flac",
                "aac": "aac",
                "ogg": "libvorbis",
            }
            codec = codec_map.get(format, "libmp3lame")

            args = [
                "-i",
                str(input_path),
                "-vn",  # No video
                "-acodec",
                codec,
            ]

            # Add bitrate for lossy formats
            if format in ["mp3", "aac", "ogg"]:
                args.extend(["-b:a", bitrate])

            args.append(str(output_path))

            returncode, stdout, stderr = await _run_ffmpeg_async(args)

            if returncode != 0:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"FFmpeg failed: {stderr[:500]}",
                )

            # Get output file info
            file_size = os.path.getsize(output_path)

            return ToolResult(
                success=True,
                output=f"Extracted audio to: {output_path}",
                metadata={
                    "output_path": output_path,
                    "format": format,
                    "bitrate": bitrate,
                    "size": file_size,
                    "size_human": _human_readable_size(file_size),
                },
            )

        except TimeoutError as e:
            return ToolResult(success=False, output="", error=str(e))
        except Exception as e:
            logger.error("video_extract_audio_error", error=str(e), input=input)
            return ToolResult(
                success=False,
                output="",
                error=f"Audio extraction failed: {str(e)}",
            )


class VideoTranscribeTool(Tool):
    """Transcribe speech from video files."""

    name = "video_transcribe"
    description = """Transcribe speech from video file using Whisper.

Examples:
- Transcribe video: video_transcribe(input="lecture.mp4")
- With larger model: video_transcribe(input="video.mkv", model="medium")
"""
    parameters = {
        "type": "object",
        "properties": {
            "input": {
                "type": "string",
                "description": "Path to video file",
            },
            "model": {
                "type": "string",
                "description": "Whisper model size: tiny, base, small, medium, large (default: base)",
                "enum": ["tiny", "base", "small", "medium", "large"],
            },
            "translate": {
                "type": "boolean",
                "description": "Translate to English instead of transcribing (default: false)",
            },
            "language": {
                "type": "string",
                "description": "Source language code. Auto-detected if not specified.",
            },
        },
        "required": ["input"],
    }

    async def execute(
        self,
        input: str,
        model: str = "base",
        translate: bool = False,
        language: Optional[str] = None,
        **kwargs: Any,
    ) -> ToolResult:
        """Execute video transcription."""
        if not FFMPEG_AVAILABLE:
            return ToolResult(
                success=False,
                output="",
                error="FFmpeg not found. Install with: pacman -S ffmpeg",
            )

        if not WHISPER_AVAILABLE:
            return ToolResult(
                success=False,
                output="",
                error="Whisper not available. Install with: pip install 'sindri[voice]'",
            )

        input_path = self._resolve_path(input)

        if not os.path.exists(input_path):
            return ToolResult(
                success=False,
                output="",
                error=f"Input file does not exist: {input}",
            )

        # Create temp file for extracted audio
        temp_audio = None
        try:
            # Extract audio to temp WAV file
            with tempfile.NamedTemporaryFile(
                suffix=".wav", delete=False
            ) as tmp:
                temp_audio = tmp.name

            # Extract audio
            args = [
                "-i",
                str(input_path),
                "-vn",
                "-acodec",
                "pcm_s16le",
                "-ar",
                "16000",  # Whisper expects 16kHz
                "-ac",
                "1",  # Mono
                temp_audio,
            ]

            returncode, stdout, stderr = await _run_ffmpeg_async(args)

            if returncode != 0:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Audio extraction failed: {stderr[:500]}",
                )

            # Transcribe the extracted audio
            audio_tool = AudioTranscribeTool(work_dir=self.work_dir)
            result = await audio_tool.execute(
                input=temp_audio,
                model=model,
                translate=translate,
                language=language,
            )

            # Add video-specific metadata
            if result.success and result.metadata:
                result.metadata["source_video"] = str(input_path)

            return result

        finally:
            # Cleanup temp file
            if temp_audio and os.path.exists(temp_audio):
                os.unlink(temp_audio)


class VideoGenerateSubtitlesTool(Tool):
    """Generate subtitle files from video/audio."""

    name = "video_generate_subtitles"
    description = """Generate SRT or VTT subtitle file from video/audio speech.

Examples:
- Generate SRT: video_generate_subtitles(input="video.mp4")
- Generate VTT: video_generate_subtitles(input="audio.mp3", format="vtt")
- Custom output: video_generate_subtitles(input="video.mp4", output="captions.srt")
"""
    parameters = {
        "type": "object",
        "properties": {
            "input": {
                "type": "string",
                "description": "Path to video or audio file",
            },
            "output": {
                "type": "string",
                "description": "Output subtitle file path (optional)",
            },
            "format": {
                "type": "string",
                "description": "Subtitle format: srt or vtt (default: srt)",
                "enum": ["srt", "vtt"],
            },
            "model": {
                "type": "string",
                "description": "Whisper model size (default: base)",
                "enum": ["tiny", "base", "small", "medium", "large"],
            },
            "language": {
                "type": "string",
                "description": "Source language code. Auto-detected if not specified.",
            },
        },
        "required": ["input"],
    }

    async def execute(
        self,
        input: str,
        output: Optional[str] = None,
        format: str = "srt",
        model: str = "base",
        language: Optional[str] = None,
        **kwargs: Any,
    ) -> ToolResult:
        """Generate subtitles."""
        if not WHISPER_AVAILABLE:
            return ToolResult(
                success=False,
                output="",
                error="Whisper not available. Install with: pip install 'sindri[voice]'",
            )

        input_path = self._resolve_path(input)

        if not os.path.exists(input_path):
            return ToolResult(
                success=False,
                output="",
                error=f"Input file does not exist: {input}",
            )

        # Determine if input is video or audio
        ext = _get_file_extension(input_path)
        is_video = ext in VIDEO_FORMATS

        try:
            # Get transcription with segments
            if is_video:
                if not FFMPEG_AVAILABLE:
                    return ToolResult(
                        success=False,
                        output="",
                        error="FFmpeg required for video files",
                    )
                # Extract audio first
                video_tool = VideoTranscribeTool(work_dir=self.work_dir)
                result = await video_tool.execute(
                    input=input, model=model, language=language
                )
            else:
                audio_tool = AudioTranscribeTool(work_dir=self.work_dir)
                result = await audio_tool.execute(
                    input=input, model=model, language=language
                )

            if not result.success:
                return result

            segments = result.metadata.get("segments", [])

            if not segments:
                return ToolResult(
                    success=False,
                    output="",
                    error="No speech segments found in media",
                )

            # Generate subtitle content
            if format == "srt":
                subtitle_content = self._generate_srt(segments)
            else:
                subtitle_content = self._generate_vtt(segments)

            # Determine output path
            if output:
                output_path = self._resolve_path(output)
            else:
                base = os.path.splitext(input_path)[0]
                output_path = f"{base}.{format}"

            # Write subtitle file
            os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(subtitle_content)

            return ToolResult(
                success=True,
                output=f"Generated {format.upper()} subtitles: {output_path}",
                metadata={
                    "output_path": output_path,
                    "format": format,
                    "segment_count": len(segments),
                    "language": result.metadata.get("language", "unknown"),
                    "duration_seconds": result.metadata.get("duration_seconds", 0),
                },
            )

        except Exception as e:
            logger.error("video_generate_subtitles_error", error=str(e))
            return ToolResult(
                success=False,
                output="",
                error=f"Subtitle generation failed: {str(e)}",
            )

    def _generate_srt(self, segments: list[dict]) -> str:
        """Generate SRT format subtitles."""
        lines = []
        for i, seg in enumerate(segments, 1):
            start = _format_timestamp_srt(seg.get("start", 0))
            end = _format_timestamp_srt(seg.get("end", 0))
            text = seg.get("text", "").strip()
            lines.append(f"{i}")
            lines.append(f"{start} --> {end}")
            lines.append(text)
            lines.append("")
        return "\n".join(lines)

    def _generate_vtt(self, segments: list[dict]) -> str:
        """Generate WebVTT format subtitles."""
        lines = ["WEBVTT", ""]
        for i, seg in enumerate(segments, 1):
            start = _format_timestamp_vtt(seg.get("start", 0))
            end = _format_timestamp_vtt(seg.get("end", 0))
            text = seg.get("text", "").strip()
            lines.append(f"{i}")
            lines.append(f"{start} --> {end}")
            lines.append(text)
            lines.append("")
        return "\n".join(lines)


class AudioConvertTool(Tool):
    """Convert audio files between formats."""

    name = "audio_convert"
    description = """Convert audio file to different format.

Examples:
- Convert to MP3: audio_convert(input="audio.wav", format="mp3")
- High quality conversion: audio_convert(input="audio.ogg", format="flac")
- Custom bitrate: audio_convert(input="audio.wav", format="mp3", bitrate="320k")
"""
    parameters = {
        "type": "object",
        "properties": {
            "input": {
                "type": "string",
                "description": "Path to input audio file",
            },
            "output": {
                "type": "string",
                "description": "Output file path (optional)",
            },
            "format": {
                "type": "string",
                "description": "Output format: mp3, wav, flac, ogg, aac, m4a, opus",
                "enum": ["mp3", "wav", "flac", "ogg", "aac", "m4a", "opus"],
            },
            "bitrate": {
                "type": "string",
                "description": "Audio bitrate (e.g., '128k', '192k', '320k')",
            },
            "sample_rate": {
                "type": "integer",
                "description": "Sample rate in Hz (e.g., 44100, 48000)",
            },
        },
        "required": ["input", "format"],
    }

    async def execute(
        self,
        input: str,
        format: str,
        output: Optional[str] = None,
        bitrate: Optional[str] = None,
        sample_rate: Optional[int] = None,
        **kwargs: Any,
    ) -> ToolResult:
        """Execute audio conversion."""
        if not FFMPEG_AVAILABLE:
            return ToolResult(
                success=False,
                output="",
                error="FFmpeg not found. Install with: pacman -S ffmpeg",
            )

        input_path = self._resolve_path(input)

        if not os.path.exists(input_path):
            return ToolResult(
                success=False,
                output="",
                error=f"Input file does not exist: {input}",
            )

        # Determine output path
        if output:
            output_path = self._resolve_path(output)
        else:
            base = os.path.splitext(input_path)[0]
            output_path = f"{base}_converted.{format}"

        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

        try:
            # Build FFmpeg command
            codec_map = {
                "mp3": "libmp3lame",
                "wav": "pcm_s16le",
                "flac": "flac",
                "ogg": "libvorbis",
                "aac": "aac",
                "m4a": "aac",
                "opus": "libopus",
            }
            codec = codec_map.get(format, "copy")

            args = ["-i", str(input_path), "-acodec", codec]

            if bitrate and format in ["mp3", "aac", "ogg", "opus", "m4a"]:
                args.extend(["-b:a", bitrate])

            if sample_rate:
                args.extend(["-ar", str(sample_rate)])

            args.append(str(output_path))

            returncode, stdout, stderr = await _run_ffmpeg_async(args)

            if returncode != 0:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Conversion failed: {stderr[:500]}",
                )

            # Get output info
            file_size = os.path.getsize(output_path)
            input_size = os.path.getsize(input_path)

            return ToolResult(
                success=True,
                output=f"Converted audio to: {output_path}",
                metadata={
                    "output_path": output_path,
                    "format": format,
                    "input_size": input_size,
                    "output_size": file_size,
                    "size_human": _human_readable_size(file_size),
                    "compression_ratio": round(file_size / input_size, 2)
                    if input_size > 0
                    else 1.0,
                },
            )

        except Exception as e:
            logger.error("audio_convert_error", error=str(e))
            return ToolResult(
                success=False,
                output="",
                error=f"Audio conversion failed: {str(e)}",
            )


class VideoConvertTool(Tool):
    """Convert video files between formats."""

    name = "video_convert"
    description = """Convert video file to different format.

Examples:
- Convert to MP4: video_convert(input="video.mkv", format="mp4")
- Convert to WebM: video_convert(input="video.avi", format="webm")
- Custom quality: video_convert(input="video.mov", format="mp4", crf=23)
"""
    parameters = {
        "type": "object",
        "properties": {
            "input": {
                "type": "string",
                "description": "Path to input video file",
            },
            "output": {
                "type": "string",
                "description": "Output file path (optional)",
            },
            "format": {
                "type": "string",
                "description": "Output format: mp4, mkv, webm, avi, mov",
                "enum": ["mp4", "mkv", "webm", "avi", "mov"],
            },
            "crf": {
                "type": "integer",
                "description": "Quality (0-51, lower=better). Default: 23",
            },
            "resolution": {
                "type": "string",
                "description": "Output resolution (e.g., '1920x1080', '1280x720')",
            },
            "audio_bitrate": {
                "type": "string",
                "description": "Audio bitrate (e.g., '128k', '192k')",
            },
        },
        "required": ["input", "format"],
    }

    async def execute(
        self,
        input: str,
        format: str,
        output: Optional[str] = None,
        crf: int = 23,
        resolution: Optional[str] = None,
        audio_bitrate: Optional[str] = None,
        **kwargs: Any,
    ) -> ToolResult:
        """Execute video conversion."""
        if not FFMPEG_AVAILABLE:
            return ToolResult(
                success=False,
                output="",
                error="FFmpeg not found. Install with: pacman -S ffmpeg",
            )

        input_path = self._resolve_path(input)

        if not os.path.exists(input_path):
            return ToolResult(
                success=False,
                output="",
                error=f"Input file does not exist: {input}",
            )

        # Determine output path
        if output:
            output_path = self._resolve_path(output)
        else:
            base = os.path.splitext(input_path)[0]
            output_path = f"{base}_converted.{format}"

        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

        try:
            # Build FFmpeg command based on format
            if format == "mp4":
                args = ["-i", str(input_path), "-c:v", "libx264", "-crf", str(crf)]
            elif format == "webm":
                args = ["-i", str(input_path), "-c:v", "libvpx-vp9", "-crf", str(crf)]
            elif format == "mkv":
                args = ["-i", str(input_path), "-c:v", "libx264", "-crf", str(crf)]
            else:
                args = ["-i", str(input_path)]

            # Add resolution scaling if specified
            if resolution:
                args.extend(["-vf", f"scale={resolution.replace('x', ':')}"])

            # Add audio settings
            if audio_bitrate:
                args.extend(["-b:a", audio_bitrate])
            else:
                args.extend(["-c:a", "aac", "-b:a", "192k"])

            args.append(str(output_path))

            returncode, stdout, stderr = await _run_ffmpeg_async(args, timeout=600.0)

            if returncode != 0:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Conversion failed: {stderr[:500]}",
                )

            # Get output info
            file_size = os.path.getsize(output_path)
            input_size = os.path.getsize(input_path)

            return ToolResult(
                success=True,
                output=f"Converted video to: {output_path}",
                metadata={
                    "output_path": output_path,
                    "format": format,
                    "input_size": input_size,
                    "output_size": file_size,
                    "size_human": _human_readable_size(file_size),
                    "compression_ratio": round(file_size / input_size, 2)
                    if input_size > 0
                    else 1.0,
                },
            )

        except TimeoutError as e:
            return ToolResult(success=False, output="", error=str(e))
        except Exception as e:
            logger.error("video_convert_error", error=str(e))
            return ToolResult(
                success=False,
                output="",
                error=f"Video conversion failed: {str(e)}",
            )


class VideoTrimTool(Tool):
    """Trim video to specified time range."""

    name = "video_trim"
    description = """Cut video to specified time range.

Examples:
- Trim 10s-30s: video_trim(input="video.mp4", start="10", end="30")
- Trim with timestamps: video_trim(input="video.mp4", start="00:01:30", end="00:02:45")
- First 60 seconds: video_trim(input="video.mp4", start="0", end="60")
"""
    parameters = {
        "type": "object",
        "properties": {
            "input": {
                "type": "string",
                "description": "Path to input video file",
            },
            "output": {
                "type": "string",
                "description": "Output file path (optional)",
            },
            "start": {
                "type": "string",
                "description": "Start time (seconds or HH:MM:SS)",
            },
            "end": {
                "type": "string",
                "description": "End time (seconds or HH:MM:SS)",
            },
            "duration": {
                "type": "string",
                "description": "Duration instead of end time (alternative to 'end')",
            },
        },
        "required": ["input", "start"],
    }

    async def execute(
        self,
        input: str,
        start: str,
        end: Optional[str] = None,
        duration: Optional[str] = None,
        output: Optional[str] = None,
        **kwargs: Any,
    ) -> ToolResult:
        """Execute video trimming."""
        if not FFMPEG_AVAILABLE:
            return ToolResult(
                success=False,
                output="",
                error="FFmpeg not found. Install with: pacman -S ffmpeg",
            )

        input_path = self._resolve_path(input)

        if not os.path.exists(input_path):
            return ToolResult(
                success=False,
                output="",
                error=f"Input file does not exist: {input}",
            )

        if not end and not duration:
            return ToolResult(
                success=False,
                output="",
                error="Either 'end' or 'duration' must be specified",
            )

        # Determine output path
        ext = _get_file_extension(input_path)
        if output:
            output_path = self._resolve_path(output)
        else:
            base = os.path.splitext(input_path)[0]
            output_path = f"{base}_trimmed.{ext}"

        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

        try:
            # Parse times
            start_sec = _parse_time(start)

            args = ["-ss", str(start_sec), "-i", str(input_path)]

            if end:
                end_sec = _parse_time(end)
                duration_sec = end_sec - start_sec
                args.extend(["-t", str(duration_sec)])
            elif duration:
                duration_sec = _parse_time(duration)
                args.extend(["-t", str(duration_sec)])

            # Use stream copy for fast trimming
            args.extend(["-c", "copy", str(output_path)])

            returncode, stdout, stderr = await _run_ffmpeg_async(args)

            if returncode != 0:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Trimming failed: {stderr[:500]}",
                )

            file_size = os.path.getsize(output_path)

            return ToolResult(
                success=True,
                output=f"Trimmed video to: {output_path}",
                metadata={
                    "output_path": output_path,
                    "start": start,
                    "end": end or f"{start_sec + duration_sec}s",
                    "duration": _human_readable_duration(
                        duration_sec if duration else (end_sec - start_sec)
                    ),
                    "size": file_size,
                    "size_human": _human_readable_size(file_size),
                },
            )

        except ValueError as e:
            return ToolResult(
                success=False,
                output="",
                error=f"Invalid time format: {str(e)}",
            )
        except Exception as e:
            logger.error("video_trim_error", error=str(e))
            return ToolResult(
                success=False,
                output="",
                error=f"Video trimming failed: {str(e)}",
            )


class VideoThumbnailTool(Tool):
    """Generate thumbnail from video at specified timestamp."""

    name = "video_thumbnail"
    description = """Generate thumbnail image from video at specific timestamp.

Examples:
- Thumbnail at 5s: video_thumbnail(input="video.mp4", timestamp="5")
- At specific time: video_thumbnail(input="video.mp4", timestamp="00:01:30")
- Custom output: video_thumbnail(input="video.mp4", timestamp="10", output="thumb.jpg")
"""
    parameters = {
        "type": "object",
        "properties": {
            "input": {
                "type": "string",
                "description": "Path to input video file",
            },
            "output": {
                "type": "string",
                "description": "Output image path (optional, default: video_thumbnail.jpg)",
            },
            "timestamp": {
                "type": "string",
                "description": "Timestamp for thumbnail (seconds or HH:MM:SS). Default: 0",
            },
            "width": {
                "type": "integer",
                "description": "Output width in pixels (maintains aspect ratio)",
            },
            "format": {
                "type": "string",
                "description": "Output format: jpg or png (default: jpg)",
                "enum": ["jpg", "png"],
            },
        },
        "required": ["input"],
    }

    async def execute(
        self,
        input: str,
        output: Optional[str] = None,
        timestamp: str = "0",
        width: Optional[int] = None,
        format: str = "jpg",
        **kwargs: Any,
    ) -> ToolResult:
        """Generate video thumbnail."""
        if not FFMPEG_AVAILABLE:
            return ToolResult(
                success=False,
                output="",
                error="FFmpeg not found. Install with: pacman -S ffmpeg",
            )

        input_path = self._resolve_path(input)

        if not os.path.exists(input_path):
            return ToolResult(
                success=False,
                output="",
                error=f"Input file does not exist: {input}",
            )

        # Determine output path
        if output:
            output_path = self._resolve_path(output)
        else:
            base = os.path.splitext(input_path)[0]
            output_path = f"{base}_thumbnail.{format}"

        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

        try:
            time_sec = _parse_time(timestamp)

            args = ["-ss", str(time_sec), "-i", str(input_path), "-vframes", "1"]

            # Add scaling if width specified
            if width:
                args.extend(["-vf", f"scale={width}:-1"])

            # Set quality for JPEG
            if format == "jpg":
                args.extend(["-q:v", "2"])

            args.append(str(output_path))

            returncode, stdout, stderr = await _run_ffmpeg_async(args)

            if returncode != 0:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Thumbnail generation failed: {stderr[:500]}",
                )

            file_size = os.path.getsize(output_path)

            return ToolResult(
                success=True,
                output=f"Generated thumbnail: {output_path}",
                metadata={
                    "output_path": output_path,
                    "timestamp": timestamp,
                    "format": format,
                    "size": file_size,
                    "size_human": _human_readable_size(file_size),
                },
            )

        except ValueError as e:
            return ToolResult(
                success=False,
                output="",
                error=f"Invalid timestamp: {str(e)}",
            )
        except Exception as e:
            logger.error("video_thumbnail_error", error=str(e))
            return ToolResult(
                success=False,
                output="",
                error=f"Thumbnail generation failed: {str(e)}",
            )


class VideoConcatTool(Tool):
    """Concatenate multiple videos into one."""

    name = "video_concat"
    description = """Join multiple video files into one.

Examples:
- Concat videos: video_concat(inputs=["part1.mp4", "part2.mp4"], output="full.mp4")
- Multiple parts: video_concat(inputs=["a.mp4", "b.mp4", "c.mp4"], output="combined.mp4")
"""
    parameters = {
        "type": "object",
        "properties": {
            "inputs": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of video file paths to concatenate (in order)",
            },
            "output": {
                "type": "string",
                "description": "Output video file path",
            },
        },
        "required": ["inputs", "output"],
    }

    async def execute(
        self, inputs: list[str], output: str, **kwargs: Any
    ) -> ToolResult:
        """Concatenate videos."""
        if not FFMPEG_AVAILABLE:
            return ToolResult(
                success=False,
                output="",
                error="FFmpeg not found. Install with: pacman -S ffmpeg",
            )

        if not inputs or len(inputs) < 2:
            return ToolResult(
                success=False,
                output="",
                error="At least 2 input files required for concatenation",
            )

        # Resolve all input paths
        input_paths = []
        for inp in inputs:
            path = self._resolve_path(inp)
            if not os.path.exists(path):
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Input file does not exist: {inp}",
                )
            input_paths.append(path)

        output_path = self._resolve_path(output)
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

        # Create concat list file
        list_file = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".txt", delete=False
            ) as f:
                list_file = f.name
                for path in input_paths:
                    # Escape single quotes in path
                    escaped_path = str(path).replace("'", "'\\''")
                    f.write(f"file '{escaped_path}'\n")

            # Run concat
            args = [
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                list_file,
                "-c",
                "copy",
                str(output_path),
            ]

            returncode, stdout, stderr = await _run_ffmpeg_async(args, timeout=600.0)

            if returncode != 0:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Concatenation failed: {stderr[:500]}",
                )

            file_size = os.path.getsize(output_path)

            return ToolResult(
                success=True,
                output=f"Concatenated {len(inputs)} videos to: {output_path}",
                metadata={
                    "output_path": output_path,
                    "input_count": len(inputs),
                    "inputs": inputs,
                    "size": file_size,
                    "size_human": _human_readable_size(file_size),
                },
            )

        except Exception as e:
            logger.error("video_concat_error", error=str(e))
            return ToolResult(
                success=False,
                output="",
                error=f"Video concatenation failed: {str(e)}",
            )
        finally:
            if list_file and os.path.exists(list_file):
                os.unlink(list_file)


class TtsGenerateTool(Tool):
    """Generate speech audio from text."""

    name = "tts_generate"
    description = """Generate speech audio from text using text-to-speech.

Examples:
- Generate speech: tts_generate(text="Hello world", output="greeting.wav")
- Adjust speed: tts_generate(text="Hello", output="slow.wav", rate=100)
- Different voice: tts_generate(text="Hello", output="out.wav", voice="female")
"""
    parameters = {
        "type": "object",
        "properties": {
            "text": {
                "type": "string",
                "description": "Text to convert to speech",
            },
            "output": {
                "type": "string",
                "description": "Output audio file path",
            },
            "rate": {
                "type": "integer",
                "description": "Speech rate (words per minute). Default: 150",
            },
            "volume": {
                "type": "number",
                "description": "Volume level (0.0-1.0). Default: 1.0",
            },
            "voice": {
                "type": "string",
                "description": "Voice selection (engine-specific). Default: system default",
            },
        },
        "required": ["text", "output"],
    }

    async def execute(
        self,
        text: str,
        output: str,
        rate: int = 150,
        volume: float = 1.0,
        voice: Optional[str] = None,
        **kwargs: Any,
    ) -> ToolResult:
        """Generate TTS audio."""
        if not TTS_AVAILABLE:
            return ToolResult(
                success=False,
                output="",
                error="TTS not available. Install with: pip install 'sindri[voice]'",
            )

        output_path = self._resolve_path(output)
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

        try:
            # Create TTS instance and configure
            loop = asyncio.get_event_loop()
            tts = TextToSpeech()

            # Configure voice settings
            await loop.run_in_executor(None, lambda: tts.set_rate(rate))
            await loop.run_in_executor(None, lambda: tts.set_volume(volume))

            if voice:
                await loop.run_in_executor(None, lambda: tts.set_voice(voice))

            # Synthesize to file
            await loop.run_in_executor(
                None, lambda: tts.synthesize_to_file(text, str(output_path))
            )

            if not os.path.exists(output_path):
                return ToolResult(
                    success=False,
                    output="",
                    error="TTS synthesis did not produce output file",
                )

            file_size = os.path.getsize(output_path)

            return ToolResult(
                success=True,
                output=f"Generated speech audio: {output_path}",
                metadata={
                    "output_path": output_path,
                    "text_length": len(text),
                    "rate": rate,
                    "volume": volume,
                    "size": file_size,
                    "size_human": _human_readable_size(file_size),
                },
            )

        except Exception as e:
            logger.error("tts_generate_error", error=str(e))
            return ToolResult(
                success=False,
                output="",
                error=f"TTS generation failed: {str(e)}",
            )


class VideoAddSubtitlesTool(Tool):
    """Burn subtitles into video (hardcode)."""

    name = "video_add_subtitles"
    description = """Burn subtitles into video file (hardcoded/embedded).

Examples:
- Add SRT subtitles: video_add_subtitles(input="video.mp4", subtitles="captions.srt")
- Custom output: video_add_subtitles(input="video.mp4", subtitles="subs.vtt", output="captioned.mp4")
"""
    parameters = {
        "type": "object",
        "properties": {
            "input": {
                "type": "string",
                "description": "Path to input video file",
            },
            "subtitles": {
                "type": "string",
                "description": "Path to subtitle file (SRT or VTT)",
            },
            "output": {
                "type": "string",
                "description": "Output video file path (optional)",
            },
            "font_size": {
                "type": "integer",
                "description": "Subtitle font size. Default: 24",
            },
            "font_color": {
                "type": "string",
                "description": "Subtitle font color (hex or name). Default: white",
            },
        },
        "required": ["input", "subtitles"],
    }

    async def execute(
        self,
        input: str,
        subtitles: str,
        output: Optional[str] = None,
        font_size: int = 24,
        font_color: str = "white",
        **kwargs: Any,
    ) -> ToolResult:
        """Add subtitles to video."""
        if not FFMPEG_AVAILABLE:
            return ToolResult(
                success=False,
                output="",
                error="FFmpeg not found. Install with: pacman -S ffmpeg",
            )

        input_path = self._resolve_path(input)
        subtitle_path = self._resolve_path(subtitles)

        if not os.path.exists(input_path):
            return ToolResult(
                success=False,
                output="",
                error=f"Input video does not exist: {input}",
            )

        if not os.path.exists(subtitle_path):
            return ToolResult(
                success=False,
                output="",
                error=f"Subtitle file does not exist: {subtitles}",
            )

        # Determine output path
        ext = _get_file_extension(input_path)
        if output:
            output_path = self._resolve_path(output)
        else:
            base = os.path.splitext(input_path)[0]
            output_path = f"{base}_subtitled.{ext}"

        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

        try:
            # Escape the subtitle path for FFmpeg filter
            # Need to escape colons, backslashes, and single quotes
            escaped_sub = str(subtitle_path).replace("\\", "\\\\")
            escaped_sub = escaped_sub.replace(":", "\\:")
            escaped_sub = escaped_sub.replace("'", "\\'")

            # Build subtitles filter with styling
            sub_filter = f"subtitles='{escaped_sub}':force_style='FontSize={font_size},PrimaryColour=&H{self._color_to_ass(font_color)}&'"

            args = [
                "-i",
                str(input_path),
                "-vf",
                sub_filter,
                "-c:a",
                "copy",
                str(output_path),
            ]

            returncode, stdout, stderr = await _run_ffmpeg_async(args, timeout=600.0)

            if returncode != 0:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Subtitle burning failed: {stderr[:500]}",
                )

            file_size = os.path.getsize(output_path)

            return ToolResult(
                success=True,
                output=f"Added subtitles to video: {output_path}",
                metadata={
                    "output_path": output_path,
                    "subtitle_file": str(subtitle_path),
                    "font_size": font_size,
                    "font_color": font_color,
                    "size": file_size,
                    "size_human": _human_readable_size(file_size),
                },
            )

        except Exception as e:
            logger.error("video_add_subtitles_error", error=str(e))
            return ToolResult(
                success=False,
                output="",
                error=f"Subtitle burning failed: {str(e)}",
            )

    def _color_to_ass(self, color: str) -> str:
        """Convert color name to ASS format (BGR hex)."""
        color_map = {
            "white": "FFFFFF",
            "black": "000000",
            "red": "0000FF",
            "green": "00FF00",
            "blue": "FF0000",
            "yellow": "00FFFF",
            "cyan": "FFFF00",
            "magenta": "FF00FF",
        }
        return color_map.get(color.lower(), "FFFFFF")
