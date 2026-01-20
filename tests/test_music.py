"""Tests for music composition tools."""

import base64
import os
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sindri.tools.music import (
    GenerateMIDITool,
    GenerateABCTool,
    HarmonizeTool,
    ArrangeTool,
    AnalyzeMusicTool,
    ExportAudioTool,
    MIDO_AVAILABLE,
    SCALES,
    PROGRESSIONS,
    parse_note,
    parse_key,
    get_scale_notes,
    get_chord_notes,
    duration_to_ticks,
    midi_to_note_name,
)


# ============================================================================
# Helper Function Tests
# ============================================================================


class TestParseNote:
    """Test note parsing helper function."""

    def test_parse_c4(self):
        """Test parsing C4 (middle C)."""
        midi_note, octave = parse_note("C4")
        assert midi_note == 60
        assert octave == 4

    def test_parse_a4(self):
        """Test parsing A4 (concert pitch)."""
        midi_note, octave = parse_note("A4")
        assert midi_note == 69
        assert octave == 4

    def test_parse_sharp(self):
        """Test parsing sharp note."""
        midi_note, octave = parse_note("F#5")
        assert midi_note == 78
        assert octave == 5

    def test_parse_flat(self):
        """Test parsing flat note."""
        midi_note, octave = parse_note("Bb3")
        assert midi_note == 58
        assert octave == 3

    def test_parse_default_octave(self):
        """Test parsing note without octave defaults to 4."""
        midi_note, octave = parse_note("C")
        assert midi_note == 60
        assert octave == 4

    def test_parse_lowercase(self):
        """Test parsing lowercase note."""
        midi_note, octave = parse_note("g3")
        assert midi_note == 55
        assert octave == 3

    def test_parse_invalid_note(self):
        """Test parsing invalid note raises error."""
        with pytest.raises(ValueError):
            parse_note("X4")

    def test_parse_empty_string(self):
        """Test parsing empty string raises error."""
        with pytest.raises(ValueError):
            parse_note("")


class TestParseKey:
    """Test key parsing helper function."""

    def test_parse_c_major(self):
        """Test parsing C major."""
        root, mode = parse_key("C")
        assert root == 0
        assert mode == "major"

    def test_parse_g_major(self):
        """Test parsing G major."""
        root, mode = parse_key("G")
        assert root == 7
        assert mode == "major"

    def test_parse_a_minor(self):
        """Test parsing A minor."""
        root, mode = parse_key("Am")
        assert root == 9
        assert mode == "minor"

    def test_parse_f_sharp_minor(self):
        """Test parsing F# minor."""
        root, mode = parse_key("F#m")
        assert root == 6
        assert mode == "minor"

    def test_parse_b_flat_major(self):
        """Test parsing Bb major."""
        root, mode = parse_key("Bb")
        assert root == 10
        assert mode == "major"


class TestGetScaleNotes:
    """Test scale note generation."""

    def test_c_major_scale(self):
        """Test C major scale notes."""
        notes = get_scale_notes(0, "major", octave=4)
        expected = [60, 62, 64, 65, 67, 69, 71]  # C D E F G A B
        assert notes == expected

    def test_a_minor_scale(self):
        """Test A minor scale notes."""
        notes = get_scale_notes(9, "minor", octave=4)
        # A minor: A B C D E F G
        expected = [69, 71, 72, 74, 76, 77, 79]
        assert notes == expected

    def test_pentatonic_scale(self):
        """Test pentatonic scale has 5 notes."""
        notes = get_scale_notes(0, "pentatonic_major", octave=4)
        assert len(notes) == 5

    def test_blues_scale(self):
        """Test blues scale has 6 notes."""
        notes = get_scale_notes(0, "blues", octave=4)
        assert len(notes) == 6

    def test_unknown_scale_raises(self):
        """Test unknown scale raises ValueError."""
        with pytest.raises(ValueError):
            get_scale_notes(0, "unknown_scale")


class TestGetChordNotes:
    """Test chord note generation."""

    def test_c_major_chord(self):
        """Test C major chord."""
        notes = get_chord_notes(0, "major", octave=4)
        expected = [60, 64, 67]  # C E G
        assert notes == expected

    def test_a_minor_chord(self):
        """Test A minor chord."""
        notes = get_chord_notes(9, "minor", octave=4)
        expected = [69, 72, 76]  # A C E
        assert notes == expected

    def test_seventh_chord(self):
        """Test dominant 7th chord has 4 notes."""
        notes = get_chord_notes(0, "7", octave=4)
        assert len(notes) == 4


class TestDurationToTicks:
    """Test duration conversion."""

    def test_quarter_note(self):
        """Test quarter note is one beat."""
        ticks = duration_to_ticks("quarter", 480)
        assert ticks == 480

    def test_half_note(self):
        """Test half note is two beats."""
        ticks = duration_to_ticks("half", 480)
        assert ticks == 960

    def test_eighth_note(self):
        """Test eighth note is half a beat."""
        ticks = duration_to_ticks("eighth", 480)
        assert ticks == 240

    def test_dotted_quarter(self):
        """Test dotted quarter note."""
        ticks = duration_to_ticks("dotted_quarter", 480)
        assert ticks == 720  # 1.5 beats


class TestMidiToNoteName:
    """Test MIDI to note name conversion."""

    def test_middle_c(self):
        """Test middle C."""
        name = midi_to_note_name(60)
        assert name == "C4"

    def test_concert_a(self):
        """Test concert A."""
        name = midi_to_note_name(69)
        assert name == "A4"

    def test_sharp_note(self):
        """Test sharp note."""
        name = midi_to_note_name(61)
        assert name == "C#4"


# ============================================================================
# GenerateMIDITool Tests
# ============================================================================


class TestGenerateMIDITool:
    """Test MIDI generation tool."""

    @pytest.fixture
    def tool(self):
        return GenerateMIDITool()

    @pytest.mark.asyncio
    @pytest.mark.skipif(not MIDO_AVAILABLE, reason="mido not available")
    async def test_generate_basic_midi(self, tool):
        """Test basic MIDI generation."""
        result = await tool.execute(
            description="Simple melody",
            tempo=120,
            key="C",
            scale="major",
            duration_bars=2,
        )
        assert result.success
        assert "midi_base64" in result.metadata or "output_file" in result.metadata

    @pytest.mark.asyncio
    @pytest.mark.skipif(not MIDO_AVAILABLE, reason="mido not available")
    async def test_generate_midi_with_notes(self, tool):
        """Test MIDI generation with explicit notes."""
        notes = [
            {"pitch": "C4", "duration": "quarter", "velocity": 80},
            {"pitch": "E4", "duration": "quarter", "velocity": 80},
            {"pitch": "G4", "duration": "half", "velocity": 80},
        ]
        result = await tool.execute(notes=notes)
        assert result.success

    @pytest.mark.asyncio
    @pytest.mark.skipif(not MIDO_AVAILABLE, reason="mido not available")
    async def test_generate_midi_with_progression(self, tool):
        """Test MIDI generation with chord progression."""
        result = await tool.execute(
            progression="pop",
            key="C",
            duration_bars=4,
        )
        assert result.success

    @pytest.mark.asyncio
    @pytest.mark.skipif(not MIDO_AVAILABLE, reason="mido not available")
    async def test_generate_midi_to_file(self, tool):
        """Test saving MIDI to file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_file = os.path.join(tmpdir, "test.mid")
            result = await tool.execute(
                key="G",
                scale="major",
                duration_bars=2,
                output_file=output_file,
            )
            assert result.success
            assert os.path.exists(output_file)
            assert "output_file" in result.metadata

    @pytest.mark.asyncio
    @pytest.mark.skipif(not MIDO_AVAILABLE, reason="mido not available")
    async def test_generate_midi_different_time_signatures(self, tool):
        """Test MIDI generation with different time signatures."""
        for time_sig in ["4/4", "3/4", "6/8"]:
            result = await tool.execute(
                time_signature=time_sig,
                duration_bars=2,
            )
            assert result.success
            assert result.metadata["time_signature"] == time_sig

    @pytest.mark.asyncio
    @pytest.mark.skipif(not MIDO_AVAILABLE, reason="mido not available")
    async def test_generate_midi_different_instruments(self, tool):
        """Test MIDI generation with different instruments."""
        for instrument in ["piano", "guitar", "violin"]:
            result = await tool.execute(
                instrument=instrument,
                duration_bars=1,
            )
            assert result.success

    @pytest.mark.asyncio
    @pytest.mark.skipif(not MIDO_AVAILABLE, reason="mido not available")
    async def test_generate_midi_tempo_in_metadata(self, tool):
        """Test that tempo is recorded in metadata."""
        result = await tool.execute(tempo=140, duration_bars=1)
        assert result.success
        assert result.metadata["tempo"] == 140

    @pytest.mark.asyncio
    async def test_generate_midi_without_mido(self, tool):
        """Test error when mido is not available."""
        with patch("sindri.tools.music.MIDO_AVAILABLE", False):
            tool_no_mido = GenerateMIDITool()
            result = await tool_no_mido.execute(duration_bars=1)
            assert not result.success
            assert "mido" in result.error.lower()


# ============================================================================
# GenerateABCTool Tests
# ============================================================================


class TestGenerateABCTool:
    """Test ABC notation generation tool."""

    @pytest.fixture
    def tool(self):
        return GenerateABCTool()

    @pytest.mark.asyncio
    async def test_generate_basic_abc(self, tool):
        """Test basic ABC generation."""
        result = await tool.execute(
            title="Test Tune",
            meter="4/4",
            key="C",
        )
        assert result.success
        assert "X:1" in result.output
        assert "T:Test Tune" in result.output
        assert "M:4/4" in result.output
        assert "K:C" in result.output

    @pytest.mark.asyncio
    async def test_generate_abc_with_notes(self, tool):
        """Test ABC generation with provided notes."""
        result = await tool.execute(
            title="Custom",
            notes="CDEF GABc",
            key="C",
        )
        assert result.success
        assert "CDEF GABc" in result.output

    @pytest.mark.asyncio
    async def test_generate_abc_with_progression(self, tool):
        """Test ABC generation with chord progression."""
        result = await tool.execute(
            title="Progression",
            progression="pop",
            key="C",
            bars=4,
        )
        assert result.success
        assert "abc" in result.output.lower()

    @pytest.mark.asyncio
    async def test_generate_abc_to_file(self, tool):
        """Test saving ABC to file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_file = os.path.join(tmpdir, "test.abc")
            result = await tool.execute(
                title="File Test",
                key="G",
                output_file=output_file,
            )
            assert result.success
            assert os.path.exists(output_file)
            content = Path(output_file).read_text()
            assert "T:File Test" in content

    @pytest.mark.asyncio
    async def test_generate_abc_metadata(self, tool):
        """Test ABC metadata is captured."""
        result = await tool.execute(
            title="Metadata Test",
            composer="Test Composer",
            meter="3/4",
            key="Am",
            tempo="100",
        )
        assert result.success
        assert result.metadata["title"] == "Metadata Test"
        assert result.metadata["key"] == "Am"
        assert result.metadata["meter"] == "3/4"

    @pytest.mark.asyncio
    async def test_generate_abc_different_styles(self, tool):
        """Test ABC generation with different styles."""
        for style in ["melody", "chords", "arpeggios"]:
            result = await tool.execute(
                title=f"Style {style}",
                style=style,
                progression="pop",
                bars=2,
            )
            assert result.success


# ============================================================================
# HarmonizeTool Tests
# ============================================================================


class TestHarmonizeTool:
    """Test harmonization tool."""

    @pytest.fixture
    def tool(self):
        return HarmonizeTool()

    @pytest.mark.asyncio
    async def test_harmonize_abc_melody(self, tool):
        """Test harmonizing ABC melody."""
        melody = "X:1\nT:Test\nM:4/4\nK:C\nCDEF GABc"
        result = await tool.execute(
            melody=melody,
            style="classical",
            voice_count=2,
            key="C",
        )
        assert result.success
        assert "abc" in result.output.lower()

    @pytest.mark.asyncio
    async def test_harmonize_different_styles(self, tool):
        """Test harmonization with different styles."""
        melody = "CDEF"
        for style in ["classical", "jazz", "pop", "folk"]:
            result = await tool.execute(
                melody=melody,
                style=style,
                voice_count=2,
            )
            assert result.success
            assert result.metadata["style"] == style

    @pytest.mark.asyncio
    async def test_harmonize_different_voice_counts(self, tool):
        """Test harmonization with different voice counts."""
        melody = "CDEF"
        for voice_count in [2, 3, 4]:
            result = await tool.execute(
                melody=melody,
                voice_count=voice_count,
            )
            assert result.success
            assert result.metadata["voice_count"] == voice_count

    @pytest.mark.asyncio
    async def test_harmonize_to_file(self, tool):
        """Test saving harmonized output to file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_file = os.path.join(tmpdir, "harmonized.abc")
            result = await tool.execute(
                melody="CDEF GABc",
                style="pop",
                output_file=output_file,
            )
            assert result.success
            assert os.path.exists(output_file)


# ============================================================================
# ArrangeTool Tests
# ============================================================================


class TestArrangeTool:
    """Test arrangement tool."""

    @pytest.fixture
    def tool(self):
        return ArrangeTool()

    @pytest.mark.asyncio
    @pytest.mark.skipif(not MIDO_AVAILABLE, reason="mido not available")
    async def test_arrange_basic(self, tool):
        """Test basic arrangement."""
        result = await tool.execute(
            source="CDEF GABc",
            style="quartet",
        )
        assert result.success
        assert "instruments" in result.metadata

    @pytest.mark.asyncio
    @pytest.mark.skipif(not MIDO_AVAILABLE, reason="mido not available")
    async def test_arrange_with_instruments(self, tool):
        """Test arrangement with specific instruments."""
        instruments = ["piano", "bass", "drums"]
        result = await tool.execute(
            source="CDEF",
            instruments=instruments,
            style="band",
        )
        assert result.success
        assert result.metadata["instruments"] == instruments

    @pytest.mark.asyncio
    @pytest.mark.skipif(not MIDO_AVAILABLE, reason="mido not available")
    async def test_arrange_different_styles(self, tool):
        """Test arrangement with different styles."""
        for style in ["orchestral", "band", "quartet", "solo"]:
            result = await tool.execute(
                source="CDEF",
                style=style,
            )
            assert result.success
            assert result.metadata["style"] == style

    @pytest.mark.asyncio
    @pytest.mark.skipif(not MIDO_AVAILABLE, reason="mido not available")
    async def test_arrange_to_file(self, tool):
        """Test saving arrangement to file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_file = os.path.join(tmpdir, "arranged.mid")
            result = await tool.execute(
                source="CDEF GABc",
                style="quartet",
                output_file=output_file,
            )
            assert result.success
            assert os.path.exists(output_file)


# ============================================================================
# AnalyzeMusicTool Tests
# ============================================================================


class TestAnalyzeMusicTool:
    """Test music analysis tool."""

    @pytest.fixture
    def tool(self):
        return AnalyzeMusicTool()

    @pytest.mark.asyncio
    async def test_analyze_abc_content(self, tool):
        """Test analyzing ABC notation content."""
        abc_content = """X:1
T:Test Song
C:Test Composer
M:4/4
Q:1/4=120
K:G
CDEF GABc"""
        result = await tool.execute(content=abc_content)
        assert result.success
        analysis = result.metadata["analysis"]
        assert analysis["format"] == "ABC"
        assert analysis["title"] == "Test Song"
        assert analysis["meter"] == "4/4"
        assert analysis["key"] == "G"

    @pytest.mark.asyncio
    async def test_analyze_abc_file(self, tool):
        """Test analyzing ABC file."""
        abc_content = "X:1\nT:File Test\nM:3/4\nK:Am\nABc def"
        with tempfile.TemporaryDirectory() as tmpdir:
            abc_file = os.path.join(tmpdir, "test.abc")
            Path(abc_file).write_text(abc_content)

            result = await tool.execute(file_path=abc_file)
            assert result.success
            assert result.metadata["analysis"]["title"] == "File Test"

    @pytest.mark.asyncio
    @pytest.mark.skipif(not MIDO_AVAILABLE, reason="mido not available")
    async def test_analyze_midi_file(self, tool):
        """Test analyzing MIDI file."""
        # First create a MIDI file
        midi_tool = GenerateMIDITool()
        with tempfile.TemporaryDirectory() as tmpdir:
            midi_file = os.path.join(tmpdir, "test.mid")
            await midi_tool.execute(
                tempo=100,
                key="C",
                duration_bars=2,
                output_file=midi_file,
            )

            result = await tool.execute(file_path=midi_file)
            assert result.success
            analysis = result.metadata["analysis"]
            assert analysis["format"] == "MIDI"
            assert "tempo_bpm" in analysis

    @pytest.mark.asyncio
    async def test_analyze_different_types(self, tool):
        """Test different analysis types."""
        abc_content = "X:1\nT:Test\nM:4/4\nK:C\nCDEF"
        for analysis_type in ["full", "key", "statistics"]:
            result = await tool.execute(
                content=abc_content,
                analysis_type=analysis_type,
            )
            assert result.success

    @pytest.mark.asyncio
    async def test_analyze_nonexistent_file(self, tool):
        """Test analyzing nonexistent file."""
        result = await tool.execute(file_path="/nonexistent/file.mid")
        assert not result.success
        assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_analyze_no_input(self, tool):
        """Test error when no input provided."""
        result = await tool.execute()
        assert not result.success
        assert "must be provided" in result.error.lower()


# ============================================================================
# ExportAudioTool Tests
# ============================================================================


class TestExportAudioTool:
    """Test audio export tool."""

    @pytest.fixture
    def tool(self):
        return ExportAudioTool()

    @pytest.mark.asyncio
    async def test_export_nonexistent_midi(self, tool):
        """Test exporting nonexistent MIDI file."""
        result = await tool.execute(
            midi_file="/nonexistent/file.mid",
            output_file="/tmp/output.wav",
        )
        assert not result.success
        assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    @pytest.mark.skipif(not MIDO_AVAILABLE, reason="mido not available")
    async def test_export_without_fluidsynth(self, tool):
        """Test export when FluidSynth is not available."""
        # Create a MIDI file first
        midi_tool = GenerateMIDITool()
        with tempfile.TemporaryDirectory() as tmpdir:
            midi_file = os.path.join(tmpdir, "test.mid")
            await midi_tool.execute(
                duration_bars=1,
                output_file=midi_file,
            )

            with patch("sindri.tools.music.FLUIDSYNTH_AVAILABLE", False):
                with patch("subprocess.run") as mock_run:
                    mock_run.side_effect = FileNotFoundError("fluidsynth not found")
                    result = await tool.execute(
                        midi_file=midi_file,
                        output_file=os.path.join(tmpdir, "output.wav"),
                    )
                    # Should fail gracefully
                    assert not result.success


# ============================================================================
# Integration Tests
# ============================================================================


class TestMusicToolsIntegration:
    """Integration tests for music tools."""

    @pytest.mark.asyncio
    async def test_tools_registered(self):
        """Test that all music tools are registered."""
        from sindri.tools.registry import ToolRegistry

        registry = ToolRegistry.default()

        assert registry.get_tool("generate_midi") is not None
        assert registry.get_tool("generate_abc") is not None
        assert registry.get_tool("harmonize") is not None
        assert registry.get_tool("arrange") is not None
        assert registry.get_tool("analyze_music") is not None
        assert registry.get_tool("export_audio") is not None

    @pytest.mark.asyncio
    async def test_bragi_agent_exists(self):
        """Test that Bragi agent is defined."""
        from sindri.agents.registry import AGENTS, get_agent

        assert "bragi" in AGENTS
        bragi = get_agent("bragi")
        assert bragi.name == "bragi"
        assert "music" in bragi.role.lower()
        assert "generate_midi" in bragi.tools
        assert "generate_abc" in bragi.tools

    @pytest.mark.asyncio
    async def test_brokkr_can_delegate_to_bragi(self):
        """Test that Brokkr can delegate to Bragi."""
        from sindri.agents.registry import get_agent

        brokkr = get_agent("brokkr")
        assert "bragi" in brokkr.delegate_to

    @pytest.mark.asyncio
    @pytest.mark.skipif(not MIDO_AVAILABLE, reason="mido not available")
    async def test_full_workflow(self):
        """Test complete music creation workflow."""
        # 1. Generate ABC notation
        abc_tool = GenerateABCTool()
        abc_result = await abc_tool.execute(
            title="Test Composition",
            key="C",
            meter="4/4",
            bars=4,
        )
        assert abc_result.success

        # 2. Harmonize
        harmonize_tool = HarmonizeTool()
        harmony_result = await harmonize_tool.execute(
            melody="CDEF GABc",
            style="classical",
            voice_count=2,
        )
        assert harmony_result.success

        # 3. Generate MIDI
        midi_tool = GenerateMIDITool()
        with tempfile.TemporaryDirectory() as tmpdir:
            midi_file = os.path.join(tmpdir, "composition.mid")
            midi_result = await midi_tool.execute(
                progression="pop",
                key="C",
                duration_bars=4,
                output_file=midi_file,
            )
            assert midi_result.success
            assert os.path.exists(midi_file)

            # 4. Analyze
            analyze_tool = AnalyzeMusicTool()
            analysis_result = await analyze_tool.execute(file_path=midi_file)
            assert analysis_result.success

    @pytest.mark.asyncio
    async def test_abc_to_analysis_workflow(self):
        """Test ABC creation to analysis workflow."""
        # Generate ABC
        abc_tool = GenerateABCTool()
        result = await abc_tool.execute(
            title="Analysis Test",
            key="G",
            meter="3/4",
            tempo="120",
            bars=4,
        )
        assert result.success

        # Analyze the generated content
        abc_content = result.metadata.get("abc_notation", result.output)
        analyze_tool = AnalyzeMusicTool()
        analysis_result = await analyze_tool.execute(content=abc_content)
        assert analysis_result.success


# ============================================================================
# Constants Tests
# ============================================================================


class TestMusicConstants:
    """Test music theory constants."""

    def test_scales_defined(self):
        """Test that expected scales are defined."""
        expected = ["major", "minor", "pentatonic_major", "blues", "dorian"]
        for scale in expected:
            assert scale in SCALES

    def test_progressions_defined(self):
        """Test that expected progressions are defined."""
        expected = ["pop", "jazz_251", "blues_12bar", "classical"]
        for prog in expected:
            assert prog in PROGRESSIONS

    def test_major_scale_pattern(self):
        """Test major scale has correct pattern."""
        assert SCALES["major"] == [0, 2, 4, 5, 7, 9, 11]

    def test_pop_progression(self):
        """Test pop progression is I-V-vi-IV."""
        assert PROGRESSIONS["pop"] == ["I", "V", "vi", "IV"]

    def test_blues_12bar_length(self):
        """Test 12-bar blues has 12 chords."""
        assert len(PROGRESSIONS["blues_12bar"]) == 12
