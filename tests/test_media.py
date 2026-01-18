"""Tests for video and audio processing tools."""

import asyncio
import json
import os
import shutil
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sindri.tools.media import (
    FFMPEG_AVAILABLE,
    WHISPER_AVAILABLE,
    TTS_AVAILABLE,
    AudioTranscribeTool,
    VideoExtractAudioTool,
    VideoTranscribeTool,
    VideoGenerateSubtitlesTool,
    AudioConvertTool,
    VideoConvertTool,
    VideoTrimTool,
    VideoThumbnailTool,
    VideoConcatTool,
    TtsGenerateTool,
    VideoAddSubtitlesTool,
    _format_timestamp_srt,
    _format_timestamp_vtt,
    _parse_time,
    _human_readable_size,
    _human_readable_duration,
)


# =============================================================================
# Helper function tests
# =============================================================================


class TestHelperFunctions:
    """Tests for helper utility functions."""

    def test_format_timestamp_srt(self):
        """Test SRT timestamp formatting."""
        assert _format_timestamp_srt(0) == "00:00:00,000"
        assert _format_timestamp_srt(1.5) == "00:00:01,500"
        # Use exact float to avoid precision issues
        assert _format_timestamp_srt(61.125) == "00:01:01,125"
        assert _format_timestamp_srt(3662.0) == "01:01:02,000"

    def test_format_timestamp_vtt(self):
        """Test WebVTT timestamp formatting."""
        assert _format_timestamp_vtt(0) == "00:00:00.000"
        assert _format_timestamp_vtt(1.5) == "00:00:01.500"
        # Use exact float to avoid precision issues
        assert _format_timestamp_vtt(61.125) == "00:01:01.125"
        assert _format_timestamp_vtt(3662.0) == "01:01:02.000"

    def test_parse_time_seconds(self):
        """Test parsing time from seconds."""
        assert _parse_time("10") == 10.0
        assert _parse_time("30.5") == 30.5
        assert _parse_time(45) == 45.0
        assert _parse_time(90.25) == 90.25

    def test_parse_time_mm_ss(self):
        """Test parsing MM:SS format."""
        assert _parse_time("01:30") == 90.0
        assert _parse_time("10:00") == 600.0
        assert _parse_time("00:45") == 45.0

    def test_parse_time_hh_mm_ss(self):
        """Test parsing HH:MM:SS format."""
        assert _parse_time("01:00:00") == 3600.0
        assert _parse_time("00:01:30") == 90.0
        assert _parse_time("01:30:45") == 5445.0

    def test_parse_time_invalid(self):
        """Test parsing invalid time format."""
        with pytest.raises(ValueError):
            _parse_time("invalid")

    def test_human_readable_size(self):
        """Test human-readable size formatting."""
        assert _human_readable_size(512) == "512.0 B"
        assert _human_readable_size(1024) == "1.0 KB"
        assert _human_readable_size(1536) == "1.5 KB"
        assert _human_readable_size(1048576) == "1.0 MB"
        assert _human_readable_size(1073741824) == "1.0 GB"

    def test_human_readable_duration(self):
        """Test human-readable duration formatting."""
        assert _human_readable_duration(30) == "30.0s"
        assert _human_readable_duration(90) == "1m 30s"
        assert _human_readable_duration(3661) == "1h 1m"


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def temp_dir():
    """Create a temporary directory for test files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def sample_audio_file(temp_dir):
    """Create a sample audio file placeholder."""
    audio_path = os.path.join(temp_dir, "test.wav")
    # Create a minimal WAV file (just header, no real audio)
    with open(audio_path, "wb") as f:
        # RIFF header
        f.write(b"RIFF")
        f.write((36).to_bytes(4, "little"))  # file size - 8
        f.write(b"WAVE")
        # fmt chunk
        f.write(b"fmt ")
        f.write((16).to_bytes(4, "little"))  # chunk size
        f.write((1).to_bytes(2, "little"))  # PCM
        f.write((1).to_bytes(2, "little"))  # mono
        f.write((16000).to_bytes(4, "little"))  # sample rate
        f.write((32000).to_bytes(4, "little"))  # byte rate
        f.write((2).to_bytes(2, "little"))  # block align
        f.write((16).to_bytes(2, "little"))  # bits per sample
        # data chunk
        f.write(b"data")
        f.write((0).to_bytes(4, "little"))  # data size
    return audio_path


@pytest.fixture
def sample_video_file(temp_dir):
    """Create a sample video file placeholder."""
    video_path = os.path.join(temp_dir, "test.mp4")
    # Create a minimal file (just placeholder)
    with open(video_path, "wb") as f:
        f.write(b"\x00" * 100)
    return video_path


@pytest.fixture
def sample_subtitle_file(temp_dir):
    """Create a sample SRT subtitle file."""
    srt_path = os.path.join(temp_dir, "test.srt")
    content = """1
00:00:01,000 --> 00:00:04,000
Hello, this is a test subtitle.

2
00:00:05,000 --> 00:00:08,000
This is the second line.
"""
    with open(srt_path, "w") as f:
        f.write(content)
    return srt_path


# =============================================================================
# AudioTranscribeTool Tests
# =============================================================================


class TestAudioTranscribeTool:
    """Tests for AudioTranscribeTool."""

    @pytest.fixture
    def tool(self):
        return AudioTranscribeTool()

    @pytest.mark.asyncio
    async def test_missing_whisper(self, tool, sample_audio_file):
        """Test error when Whisper is not available."""
        with patch("sindri.tools.media.WHISPER_AVAILABLE", False):
            tool_no_whisper = AudioTranscribeTool()
            result = await tool_no_whisper.execute(input=sample_audio_file)
            assert not result.success
            assert "Whisper not available" in result.error

    @pytest.mark.asyncio
    async def test_file_not_found(self, tool):
        """Test error when input file doesn't exist."""
        result = await tool.execute(input="/nonexistent/audio.wav")
        assert not result.success
        assert "does not exist" in result.error

    @pytest.mark.asyncio
    @pytest.mark.skipif(not WHISPER_AVAILABLE, reason="Whisper not available")
    async def test_transcribe_audio_mocked(self, tool, sample_audio_file):
        """Test transcription with mocked Whisper."""
        mock_result = MagicMock()
        mock_result.text = "Hello world"
        mock_result.language = "en"
        mock_result.confidence = 0.95
        mock_result.duration_seconds = 2.5
        mock_result.processing_time_ms = 500
        mock_result.segments = [
            {"start": 0, "end": 2.5, "text": "Hello world"}
        ]

        with patch("sindri.tools.media.SpeechToText") as MockSTT:
            mock_stt = MagicMock()
            mock_stt.load_model = AsyncMock()
            mock_stt.unload_model = AsyncMock()
            mock_stt.transcribe_file = AsyncMock(return_value=mock_result)
            MockSTT.return_value = mock_stt

            result = await tool.execute(input=sample_audio_file)
            assert result.success
            assert "Hello world" in result.output


# =============================================================================
# VideoExtractAudioTool Tests
# =============================================================================


class TestVideoExtractAudioTool:
    """Tests for VideoExtractAudioTool."""

    @pytest.fixture
    def tool(self):
        return VideoExtractAudioTool()

    @pytest.mark.asyncio
    async def test_missing_ffmpeg(self, tool, sample_video_file):
        """Test error when FFmpeg is not available."""
        with patch("sindri.tools.media.FFMPEG_AVAILABLE", False):
            tool_no_ffmpeg = VideoExtractAudioTool()
            result = await tool_no_ffmpeg.execute(input=sample_video_file)
            assert not result.success
            assert "FFmpeg not found" in result.error

    @pytest.mark.asyncio
    async def test_file_not_found(self, tool):
        """Test error when input file doesn't exist."""
        result = await tool.execute(input="/nonexistent/video.mp4")
        assert not result.success
        assert "does not exist" in result.error

    @pytest.mark.asyncio
    @pytest.mark.skipif(not FFMPEG_AVAILABLE, reason="FFmpeg not available")
    async def test_extract_audio_mocked(self, tool, sample_video_file, temp_dir):
        """Test audio extraction with mocked FFmpeg."""
        output_path = os.path.join(temp_dir, "output.mp3")

        with patch("sindri.tools.media._run_ffmpeg_async") as mock_ffmpeg:
            # Create output file
            with open(output_path, "wb") as f:
                f.write(b"\x00" * 1000)

            mock_ffmpeg.return_value = (0, "", "")

            result = await tool.execute(
                input=sample_video_file,
                output=output_path,
                format="mp3"
            )

            assert result.success
            assert str(result.metadata["output_path"]) == output_path
            assert result.metadata["format"] == "mp3"


# =============================================================================
# VideoTranscribeTool Tests
# =============================================================================


class TestVideoTranscribeTool:
    """Tests for VideoTranscribeTool."""

    @pytest.fixture
    def tool(self):
        return VideoTranscribeTool()

    @pytest.mark.asyncio
    async def test_missing_ffmpeg(self, tool, sample_video_file):
        """Test error when FFmpeg is not available."""
        with patch("sindri.tools.media.FFMPEG_AVAILABLE", False):
            tool_no_ffmpeg = VideoTranscribeTool()
            result = await tool_no_ffmpeg.execute(input=sample_video_file)
            assert not result.success
            assert "FFmpeg not found" in result.error

    @pytest.mark.asyncio
    async def test_missing_whisper(self, tool, sample_video_file):
        """Test error when Whisper is not available."""
        with patch("sindri.tools.media.WHISPER_AVAILABLE", False):
            tool_no_whisper = VideoTranscribeTool()
            result = await tool_no_whisper.execute(input=sample_video_file)
            assert not result.success
            assert "Whisper not available" in result.error

    @pytest.mark.asyncio
    async def test_file_not_found(self, tool):
        """Test error when input file doesn't exist."""
        result = await tool.execute(input="/nonexistent/video.mp4")
        assert not result.success
        assert "does not exist" in result.error


# =============================================================================
# VideoGenerateSubtitlesTool Tests
# =============================================================================


class TestVideoGenerateSubtitlesTool:
    """Tests for VideoGenerateSubtitlesTool."""

    @pytest.fixture
    def tool(self):
        return VideoGenerateSubtitlesTool()

    @pytest.mark.asyncio
    async def test_missing_whisper(self, tool, sample_video_file):
        """Test error when Whisper is not available."""
        with patch("sindri.tools.media.WHISPER_AVAILABLE", False):
            tool_no_whisper = VideoGenerateSubtitlesTool()
            result = await tool_no_whisper.execute(input=sample_video_file)
            assert not result.success
            assert "Whisper not available" in result.error

    @pytest.mark.asyncio
    async def test_file_not_found(self, tool):
        """Test error when input file doesn't exist."""
        result = await tool.execute(input="/nonexistent/file.mp4")
        assert not result.success
        assert "does not exist" in result.error

    def test_generate_srt_format(self, tool):
        """Test SRT subtitle generation."""
        segments = [
            {"start": 0, "end": 2.5, "text": "Hello world"},
            {"start": 3.0, "end": 5.5, "text": "Second line"},
        ]
        srt = tool._generate_srt(segments)
        assert "1" in srt
        assert "00:00:00,000 --> 00:00:02,500" in srt
        assert "Hello world" in srt
        assert "2" in srt
        assert "00:00:03,000 --> 00:00:05,500" in srt
        assert "Second line" in srt

    def test_generate_vtt_format(self, tool):
        """Test WebVTT subtitle generation."""
        segments = [
            {"start": 0, "end": 2.5, "text": "Hello world"},
            {"start": 3.0, "end": 5.5, "text": "Second line"},
        ]
        vtt = tool._generate_vtt(segments)
        assert "WEBVTT" in vtt
        assert "00:00:00.000 --> 00:00:02.500" in vtt
        assert "Hello world" in vtt


# =============================================================================
# AudioConvertTool Tests
# =============================================================================


class TestAudioConvertTool:
    """Tests for AudioConvertTool."""

    @pytest.fixture
    def tool(self):
        return AudioConvertTool()

    @pytest.mark.asyncio
    async def test_missing_ffmpeg(self, tool, sample_audio_file):
        """Test error when FFmpeg is not available."""
        with patch("sindri.tools.media.FFMPEG_AVAILABLE", False):
            tool_no_ffmpeg = AudioConvertTool()
            result = await tool_no_ffmpeg.execute(
                input=sample_audio_file, format="mp3"
            )
            assert not result.success
            assert "FFmpeg not found" in result.error

    @pytest.mark.asyncio
    async def test_file_not_found(self, tool):
        """Test error when input file doesn't exist."""
        result = await tool.execute(input="/nonexistent/audio.wav", format="mp3")
        assert not result.success
        assert "does not exist" in result.error

    @pytest.mark.asyncio
    @pytest.mark.skipif(not FFMPEG_AVAILABLE, reason="FFmpeg not available")
    async def test_convert_audio_mocked(self, tool, sample_audio_file, temp_dir):
        """Test audio conversion with mocked FFmpeg."""
        output_path = os.path.join(temp_dir, "converted.mp3")

        with patch("sindri.tools.media._run_ffmpeg_async") as mock_ffmpeg:
            # Create output file
            with open(output_path, "wb") as f:
                f.write(b"\x00" * 500)

            mock_ffmpeg.return_value = (0, "", "")

            result = await tool.execute(
                input=sample_audio_file,
                output=output_path,
                format="mp3",
                bitrate="192k"
            )

            assert result.success
            assert result.metadata["format"] == "mp3"


# =============================================================================
# VideoConvertTool Tests
# =============================================================================


class TestVideoConvertTool:
    """Tests for VideoConvertTool."""

    @pytest.fixture
    def tool(self):
        return VideoConvertTool()

    @pytest.mark.asyncio
    async def test_missing_ffmpeg(self, tool, sample_video_file):
        """Test error when FFmpeg is not available."""
        with patch("sindri.tools.media.FFMPEG_AVAILABLE", False):
            tool_no_ffmpeg = VideoConvertTool()
            result = await tool_no_ffmpeg.execute(
                input=sample_video_file, format="webm"
            )
            assert not result.success
            assert "FFmpeg not found" in result.error

    @pytest.mark.asyncio
    async def test_file_not_found(self, tool):
        """Test error when input file doesn't exist."""
        result = await tool.execute(input="/nonexistent/video.mp4", format="webm")
        assert not result.success
        assert "does not exist" in result.error

    @pytest.mark.asyncio
    @pytest.mark.skipif(not FFMPEG_AVAILABLE, reason="FFmpeg not available")
    async def test_convert_video_mocked(self, tool, sample_video_file, temp_dir):
        """Test video conversion with mocked FFmpeg."""
        output_path = os.path.join(temp_dir, "converted.webm")

        with patch("sindri.tools.media._run_ffmpeg_async") as mock_ffmpeg:
            # Create output file
            with open(output_path, "wb") as f:
                f.write(b"\x00" * 1000)

            mock_ffmpeg.return_value = (0, "", "")

            result = await tool.execute(
                input=sample_video_file,
                output=output_path,
                format="webm"
            )

            assert result.success
            assert result.metadata["format"] == "webm"


# =============================================================================
# VideoTrimTool Tests
# =============================================================================


class TestVideoTrimTool:
    """Tests for VideoTrimTool."""

    @pytest.fixture
    def tool(self):
        return VideoTrimTool()

    @pytest.mark.asyncio
    async def test_missing_ffmpeg(self, tool, sample_video_file):
        """Test error when FFmpeg is not available."""
        with patch("sindri.tools.media.FFMPEG_AVAILABLE", False):
            tool_no_ffmpeg = VideoTrimTool()
            result = await tool_no_ffmpeg.execute(
                input=sample_video_file, start="0", end="10"
            )
            assert not result.success
            assert "FFmpeg not found" in result.error

    @pytest.mark.asyncio
    async def test_file_not_found(self, tool):
        """Test error when input file doesn't exist."""
        result = await tool.execute(
            input="/nonexistent/video.mp4", start="0", end="10"
        )
        assert not result.success
        assert "does not exist" in result.error

    @pytest.mark.asyncio
    async def test_missing_end_and_duration(self, tool, sample_video_file):
        """Test error when neither end nor duration is specified."""
        result = await tool.execute(input=sample_video_file, start="0")
        assert not result.success
        assert "Either 'end' or 'duration' must be specified" in result.error

    @pytest.mark.asyncio
    @pytest.mark.skipif(not FFMPEG_AVAILABLE, reason="FFmpeg not available")
    async def test_trim_video_mocked(self, tool, sample_video_file, temp_dir):
        """Test video trimming with mocked FFmpeg."""
        output_path = os.path.join(temp_dir, "trimmed.mp4")

        with patch("sindri.tools.media._run_ffmpeg_async") as mock_ffmpeg:
            # Create output file
            with open(output_path, "wb") as f:
                f.write(b"\x00" * 500)

            mock_ffmpeg.return_value = (0, "", "")

            result = await tool.execute(
                input=sample_video_file,
                output=output_path,
                start="10",
                end="30"
            )

            assert result.success
            assert result.metadata["start"] == "10"
            assert result.metadata["end"] == "30"


# =============================================================================
# VideoThumbnailTool Tests
# =============================================================================


class TestVideoThumbnailTool:
    """Tests for VideoThumbnailTool."""

    @pytest.fixture
    def tool(self):
        return VideoThumbnailTool()

    @pytest.mark.asyncio
    async def test_missing_ffmpeg(self, tool, sample_video_file):
        """Test error when FFmpeg is not available."""
        with patch("sindri.tools.media.FFMPEG_AVAILABLE", False):
            tool_no_ffmpeg = VideoThumbnailTool()
            result = await tool_no_ffmpeg.execute(input=sample_video_file)
            assert not result.success
            assert "FFmpeg not found" in result.error

    @pytest.mark.asyncio
    async def test_file_not_found(self, tool):
        """Test error when input file doesn't exist."""
        result = await tool.execute(input="/nonexistent/video.mp4")
        assert not result.success
        assert "does not exist" in result.error

    @pytest.mark.asyncio
    @pytest.mark.skipif(not FFMPEG_AVAILABLE, reason="FFmpeg not available")
    async def test_thumbnail_mocked(self, tool, sample_video_file, temp_dir):
        """Test thumbnail generation with mocked FFmpeg."""
        output_path = os.path.join(temp_dir, "thumb.jpg")

        with patch("sindri.tools.media._run_ffmpeg_async") as mock_ffmpeg:
            # Create output file
            with open(output_path, "wb") as f:
                f.write(b"\x00" * 1000)

            mock_ffmpeg.return_value = (0, "", "")

            result = await tool.execute(
                input=sample_video_file,
                output=output_path,
                timestamp="5"
            )

            assert result.success
            assert result.metadata["timestamp"] == "5"


# =============================================================================
# VideoConcatTool Tests
# =============================================================================


class TestVideoConcatTool:
    """Tests for VideoConcatTool."""

    @pytest.fixture
    def tool(self):
        return VideoConcatTool()

    @pytest.mark.asyncio
    async def test_missing_ffmpeg(self, tool, sample_video_file, temp_dir):
        """Test error when FFmpeg is not available."""
        video2 = os.path.join(temp_dir, "video2.mp4")
        with open(video2, "wb") as f:
            f.write(b"\x00" * 100)

        with patch("sindri.tools.media.FFMPEG_AVAILABLE", False):
            tool_no_ffmpeg = VideoConcatTool()
            result = await tool_no_ffmpeg.execute(
                inputs=[sample_video_file, video2],
                output=os.path.join(temp_dir, "output.mp4")
            )
            assert not result.success
            assert "FFmpeg not found" in result.error

    @pytest.mark.asyncio
    async def test_not_enough_inputs(self, tool, sample_video_file, temp_dir):
        """Test error when fewer than 2 inputs provided."""
        result = await tool.execute(
            inputs=[sample_video_file],
            output=os.path.join(temp_dir, "output.mp4")
        )
        assert not result.success
        assert "At least 2 input files required" in result.error

    @pytest.mark.asyncio
    async def test_file_not_found(self, tool, temp_dir):
        """Test error when an input file doesn't exist."""
        result = await tool.execute(
            inputs=["/nonexistent/v1.mp4", "/nonexistent/v2.mp4"],
            output=os.path.join(temp_dir, "output.mp4")
        )
        assert not result.success
        assert "does not exist" in result.error

    @pytest.mark.asyncio
    @pytest.mark.skipif(not FFMPEG_AVAILABLE, reason="FFmpeg not available")
    async def test_concat_mocked(self, tool, temp_dir):
        """Test video concatenation with mocked FFmpeg."""
        # Create two video files
        video1 = os.path.join(temp_dir, "video1.mp4")
        video2 = os.path.join(temp_dir, "video2.mp4")
        output = os.path.join(temp_dir, "output.mp4")

        with open(video1, "wb") as f:
            f.write(b"\x00" * 100)
        with open(video2, "wb") as f:
            f.write(b"\x00" * 100)

        with patch("sindri.tools.media._run_ffmpeg_async") as mock_ffmpeg:
            # Create output file
            with open(output, "wb") as f:
                f.write(b"\x00" * 200)

            mock_ffmpeg.return_value = (0, "", "")

            result = await tool.execute(
                inputs=[video1, video2],
                output=output
            )

            assert result.success
            assert result.metadata["input_count"] == 2


# =============================================================================
# TtsGenerateTool Tests
# =============================================================================


class TestTtsGenerateTool:
    """Tests for TtsGenerateTool."""

    @pytest.fixture
    def tool(self):
        return TtsGenerateTool()

    @pytest.mark.asyncio
    async def test_missing_tts(self, tool, temp_dir):
        """Test error when TTS is not available."""
        with patch("sindri.tools.media.TTS_AVAILABLE", False):
            tool_no_tts = TtsGenerateTool()
            result = await tool_no_tts.execute(
                text="Hello world",
                output=os.path.join(temp_dir, "speech.wav")
            )
            assert not result.success
            assert "TTS not available" in result.error

    @pytest.mark.asyncio
    @pytest.mark.skipif(not TTS_AVAILABLE, reason="TTS not available")
    async def test_tts_mocked(self, tool, temp_dir):
        """Test TTS with mocked engine."""
        output_path = os.path.join(temp_dir, "speech.wav")

        with patch("sindri.tools.media.TextToSpeech") as MockTTS:
            mock_tts = MagicMock()
            mock_tts.set_rate = MagicMock()
            mock_tts.set_volume = MagicMock()
            mock_tts.set_voice = MagicMock()

            def create_file(text, path):
                with open(path, "wb") as f:
                    f.write(b"\x00" * 1000)

            mock_tts.synthesize_to_file = create_file
            MockTTS.return_value = mock_tts

            result = await tool.execute(
                text="Hello world",
                output=output_path,
                rate=150
            )

            assert result.success
            assert result.metadata["text_length"] == 11


# =============================================================================
# VideoAddSubtitlesTool Tests
# =============================================================================


class TestVideoAddSubtitlesTool:
    """Tests for VideoAddSubtitlesTool."""

    @pytest.fixture
    def tool(self):
        return VideoAddSubtitlesTool()

    @pytest.mark.asyncio
    async def test_missing_ffmpeg(self, tool, sample_video_file, sample_subtitle_file):
        """Test error when FFmpeg is not available."""
        with patch("sindri.tools.media.FFMPEG_AVAILABLE", False):
            tool_no_ffmpeg = VideoAddSubtitlesTool()
            result = await tool_no_ffmpeg.execute(
                input=sample_video_file,
                subtitles=sample_subtitle_file
            )
            assert not result.success
            assert "FFmpeg not found" in result.error

    @pytest.mark.asyncio
    async def test_video_not_found(self, tool, sample_subtitle_file):
        """Test error when video file doesn't exist."""
        result = await tool.execute(
            input="/nonexistent/video.mp4",
            subtitles=sample_subtitle_file
        )
        assert not result.success
        assert "does not exist" in result.error

    @pytest.mark.asyncio
    async def test_subtitle_not_found(self, tool, sample_video_file):
        """Test error when subtitle file doesn't exist."""
        result = await tool.execute(
            input=sample_video_file,
            subtitles="/nonexistent/subs.srt"
        )
        assert not result.success
        assert "does not exist" in result.error

    def test_color_to_ass(self, tool):
        """Test color conversion to ASS format."""
        assert tool._color_to_ass("white") == "FFFFFF"
        assert tool._color_to_ass("black") == "000000"
        assert tool._color_to_ass("red") == "0000FF"  # BGR format
        assert tool._color_to_ass("unknown") == "FFFFFF"  # default

    @pytest.mark.asyncio
    @pytest.mark.skipif(not FFMPEG_AVAILABLE, reason="FFmpeg not available")
    async def test_add_subtitles_mocked(
        self, tool, sample_video_file, sample_subtitle_file, temp_dir
    ):
        """Test adding subtitles with mocked FFmpeg."""
        output_path = os.path.join(temp_dir, "subtitled.mp4")

        with patch("sindri.tools.media._run_ffmpeg_async") as mock_ffmpeg:
            # Create output file
            with open(output_path, "wb") as f:
                f.write(b"\x00" * 1000)

            mock_ffmpeg.return_value = (0, "", "")

            result = await tool.execute(
                input=sample_video_file,
                subtitles=sample_subtitle_file,
                output=output_path
            )

            assert result.success
            assert result.metadata["font_size"] == 24


# =============================================================================
# Integration Tests (require real FFmpeg)
# =============================================================================


@pytest.mark.skipif(not FFMPEG_AVAILABLE, reason="FFmpeg not available")
class TestFFmpegIntegration:
    """Integration tests that require real FFmpeg installation."""

    @pytest.mark.asyncio
    async def test_ffmpeg_timeout_handling(self, temp_dir):
        """Test timeout handling in FFmpeg execution."""
        from sindri.tools.media import _run_ffmpeg_async

        # This should timeout (non-existent input will still fail fast)
        with pytest.raises(Exception):
            await _run_ffmpeg_async(
                ["-i", "/nonexistent", "output.mp4"],
                timeout=0.001
            )


# =============================================================================
# Parameter Validation Tests
# =============================================================================


class TestParameterSchemas:
    """Tests for tool parameter schemas."""

    def test_audio_transcribe_schema(self):
        """Test AudioTranscribeTool parameter schema."""
        tool = AudioTranscribeTool()
        schema = tool.parameters
        assert schema["type"] == "object"
        assert "input" in schema["properties"]
        assert "model" in schema["properties"]
        assert "input" in schema["required"]

    def test_video_convert_schema(self):
        """Test VideoConvertTool parameter schema."""
        tool = VideoConvertTool()
        schema = tool.parameters
        assert "input" in schema["properties"]
        assert "format" in schema["properties"]
        assert "crf" in schema["properties"]
        assert "input" in schema["required"]
        assert "format" in schema["required"]

    def test_video_trim_schema(self):
        """Test VideoTrimTool parameter schema."""
        tool = VideoTrimTool()
        schema = tool.parameters
        assert "start" in schema["properties"]
        assert "end" in schema["properties"]
        assert "duration" in schema["properties"]

    def test_tts_generate_schema(self):
        """Test TtsGenerateTool parameter schema."""
        tool = TtsGenerateTool()
        schema = tool.parameters
        assert "text" in schema["properties"]
        assert "output" in schema["properties"]
        assert "rate" in schema["properties"]
        assert "text" in schema["required"]
        assert "output" in schema["required"]


# =============================================================================
# Error Handling Tests
# =============================================================================


class TestErrorHandling:
    """Tests for error handling scenarios."""

    @pytest.mark.asyncio
    async def test_ffmpeg_command_failure(self, temp_dir):
        """Test handling of FFmpeg command failure."""
        tool = VideoConvertTool()
        video = os.path.join(temp_dir, "test.mp4")
        with open(video, "wb") as f:
            f.write(b"\x00" * 100)

        with patch("sindri.tools.media._run_ffmpeg_async") as mock_ffmpeg:
            mock_ffmpeg.return_value = (1, "", "Error: Invalid input")

            result = await tool.execute(
                input=video,
                format="webm",
                output=os.path.join(temp_dir, "out.webm")
            )

            assert not result.success
            assert "failed" in result.error.lower()

    @pytest.mark.asyncio
    async def test_invalid_time_format(self):
        """Test handling of invalid time format in trim."""
        tool = VideoTrimTool()

        with pytest.raises(ValueError):
            _parse_time("invalid:time:format:extra")
