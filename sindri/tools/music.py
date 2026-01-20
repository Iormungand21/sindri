"""Music composition and generation tools for Sindri.

This module provides tools for generating MIDI files, ABC notation,
harmonization, arrangement, music analysis, and audio export.

Named after Bragi, the Norse god of poetry and eloquence.
"""

import base64
import json
import re
import subprocess
from pathlib import Path
from typing import Any, Optional

import structlog

from sindri.tools.base import Tool, ToolResult

log = structlog.get_logger()

# Check for mido availability
try:
    import mido
    from mido import MidiFile, MidiTrack, Message, MetaMessage

    MIDO_AVAILABLE = True
except ImportError:
    MIDO_AVAILABLE = False
    mido = None
    MidiFile = None
    MidiTrack = None
    Message = None
    MetaMessage = None

# Check for FluidSynth/midi2audio availability
try:
    from midi2audio import FluidSynth

    FLUIDSYNTH_AVAILABLE = True
except ImportError:
    FLUIDSYNTH_AVAILABLE = False
    FluidSynth = None


# ============================================================================
# Music Theory Constants
# ============================================================================

# MIDI note numbers for middle octave (C4 = 60)
NOTE_TO_MIDI = {
    "C": 0,
    "D": 2,
    "E": 4,
    "F": 5,
    "G": 7,
    "A": 9,
    "B": 11,
}

# Scale patterns (semitones from root)
SCALES = {
    "major": [0, 2, 4, 5, 7, 9, 11],
    "minor": [0, 2, 3, 5, 7, 8, 10],
    "natural_minor": [0, 2, 3, 5, 7, 8, 10],
    "harmonic_minor": [0, 2, 3, 5, 7, 8, 11],
    "melodic_minor": [0, 2, 3, 5, 7, 9, 11],
    "pentatonic_major": [0, 2, 4, 7, 9],
    "pentatonic_minor": [0, 3, 5, 7, 10],
    "blues": [0, 3, 5, 6, 7, 10],
    "dorian": [0, 2, 3, 5, 7, 9, 10],
    "phrygian": [0, 1, 3, 5, 7, 8, 10],
    "lydian": [0, 2, 4, 6, 7, 9, 11],
    "mixolydian": [0, 2, 4, 5, 7, 9, 10],
    "locrian": [0, 1, 3, 5, 6, 8, 10],
    "chromatic": [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11],
    "whole_tone": [0, 2, 4, 6, 8, 10],
}

# Common chord progressions (Roman numeral notation)
PROGRESSIONS = {
    "pop": ["I", "V", "vi", "IV"],
    "jazz_251": ["ii", "V", "I"],
    "blues_12bar": [
        "I",
        "I",
        "I",
        "I",
        "IV",
        "IV",
        "I",
        "I",
        "V",
        "IV",
        "I",
        "V",
    ],
    "classical": ["I", "IV", "V", "I"],
    "andalusian": ["i", "VII", "VI", "V"],
    "pachelbel": ["I", "V", "vi", "iii", "IV", "I", "IV", "V"],
    "axis": ["I", "V", "vi", "IV"],
    "50s": ["I", "vi", "IV", "V"],
    "sensitive": ["vi", "IV", "I", "V"],
}

# Chord intervals from root (semitones)
CHORD_INTERVALS = {
    "major": [0, 4, 7],
    "minor": [0, 3, 7],
    "dim": [0, 3, 6],
    "aug": [0, 4, 8],
    "sus2": [0, 2, 7],
    "sus4": [0, 5, 7],
    "7": [0, 4, 7, 10],
    "maj7": [0, 4, 7, 11],
    "min7": [0, 3, 7, 10],
    "dim7": [0, 3, 6, 9],
}

# Scale degree to semitone offset (major scale context)
DEGREE_TO_SEMITONE = {
    "I": 0,
    "ii": 2,
    "II": 2,
    "iii": 4,
    "III": 4,
    "IV": 5,
    "iv": 5,
    "V": 7,
    "vi": 9,
    "VI": 9,
    "vii": 11,
    "VII": 10,  # In minor context, bVII
}

# General MIDI instrument names (subset)
GM_INSTRUMENTS = {
    "piano": 0,
    "acoustic_piano": 0,
    "bright_piano": 1,
    "electric_piano": 4,
    "harpsichord": 6,
    "organ": 19,
    "guitar": 24,
    "acoustic_guitar": 24,
    "electric_guitar": 27,
    "bass": 32,
    "acoustic_bass": 32,
    "electric_bass": 33,
    "violin": 40,
    "viola": 41,
    "cello": 42,
    "strings": 48,
    "trumpet": 56,
    "trombone": 57,
    "tuba": 58,
    "french_horn": 60,
    "saxophone": 65,
    "alto_sax": 65,
    "tenor_sax": 66,
    "oboe": 68,
    "clarinet": 71,
    "flute": 73,
    "synth_lead": 80,
    "synth_pad": 88,
    "drums": 0,  # Channel 10
}

# Time signature presets
TIME_SIGNATURES = {
    "4/4": (4, 4),
    "3/4": (3, 4),
    "2/4": (2, 4),
    "6/8": (6, 8),
    "2/2": (2, 2),
    "12/8": (12, 8),
    "5/4": (5, 4),
    "7/8": (7, 8),
}


# ============================================================================
# Helper Functions
# ============================================================================


def parse_note(note_str: str) -> tuple[int, int]:
    """Parse a note string like 'C4', 'F#5', 'Bb3' into MIDI note number and octave.

    Returns:
        Tuple of (midi_note_number, octave)
    """
    note_str = note_str.strip()
    if not note_str:
        raise ValueError("Empty note string")

    # Extract note name, accidental, and octave
    match = re.match(r"([A-Ga-g])([#b]?)(-?\d+)?", note_str)
    if not match:
        raise ValueError(f"Invalid note format: {note_str}")

    note_name = match.group(1).upper()
    accidental = match.group(2) or ""
    octave_str = match.group(3)
    octave = int(octave_str) if octave_str else 4  # Default to octave 4

    # Calculate MIDI note number
    base_note = NOTE_TO_MIDI.get(note_name)
    if base_note is None:
        raise ValueError(f"Invalid note name: {note_name}")

    midi_note = base_note + (octave + 1) * 12  # MIDI octave 0 starts at note 12

    # Apply accidental
    if accidental == "#":
        midi_note += 1
    elif accidental == "b":
        midi_note -= 1

    return midi_note, octave


def midi_to_note_name(midi_note: int) -> str:
    """Convert MIDI note number to note name with octave."""
    note_names = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
    octave = (midi_note // 12) - 1
    note_index = midi_note % 12
    return f"{note_names[note_index]}{octave}"


def parse_key(key_str: str) -> tuple[int, str]:
    """Parse a key string like 'C', 'Am', 'F#m', 'Bb' into root note and mode.

    Returns:
        Tuple of (root_midi_note, mode)
    """
    key_str = key_str.strip()
    if not key_str:
        raise ValueError("Empty key string")

    # Check for minor indicator
    mode = "major"
    if key_str.endswith("m"):
        mode = "minor"
        key_str = key_str[:-1]

    # Parse the root note (without octave)
    match = re.match(r"([A-Ga-g])([#b]?)", key_str)
    if not match:
        raise ValueError(f"Invalid key format: {key_str}")

    note_name = match.group(1).upper()
    accidental = match.group(2) or ""

    base_note = NOTE_TO_MIDI.get(note_name)
    if base_note is None:
        raise ValueError(f"Invalid note name: {note_name}")

    root = base_note
    if accidental == "#":
        root += 1
    elif accidental == "b":
        root -= 1

    return root, mode


def get_scale_notes(root: int, scale_type: str, octave: int = 4) -> list[int]:
    """Get MIDI note numbers for a scale starting at given root and octave."""
    scale_pattern = SCALES.get(scale_type.lower())
    if not scale_pattern:
        raise ValueError(f"Unknown scale type: {scale_type}")

    base_midi = root + (octave + 1) * 12
    return [base_midi + interval for interval in scale_pattern]


def get_chord_notes(root: int, chord_type: str, octave: int = 4) -> list[int]:
    """Get MIDI note numbers for a chord."""
    intervals = CHORD_INTERVALS.get(chord_type.lower(), CHORD_INTERVALS["major"])
    base_midi = root + (octave + 1) * 12
    return [base_midi + interval for interval in intervals]


def duration_to_ticks(duration: str, ticks_per_beat: int = 480) -> int:
    """Convert duration string to MIDI ticks.

    Duration formats: 'whole', 'half', 'quarter', 'eighth', '16th', '32nd'
    Also supports dotted: 'dotted_quarter', etc.
    """
    durations = {
        "whole": 4.0,
        "half": 2.0,
        "quarter": 1.0,
        "eighth": 0.5,
        "16th": 0.25,
        "32nd": 0.125,
    }

    duration = duration.lower()
    dotted = "dotted" in duration or duration.endswith(".")

    # Clean up duration string
    clean_duration = duration.replace("dotted_", "").replace("dotted", "").replace(".", "").strip()
    if clean_duration.endswith("_"):
        clean_duration = clean_duration[:-1]

    beats = durations.get(clean_duration, 1.0)
    if dotted:
        beats *= 1.5

    return int(beats * ticks_per_beat)


# ============================================================================
# Tool Implementations
# ============================================================================


class GenerateMIDITool(Tool):
    """Generate MIDI files from text descriptions or parameters."""

    name = "generate_midi"
    description = """Generate a MIDI file from a text description or musical parameters.
    Can create melodies, chord progressions, drum patterns, and more.
    Supports various scales, keys, time signatures, and instruments."""

    parameters = {
        "type": "object",
        "properties": {
            "description": {
                "type": "string",
                "description": "Natural language description of the music to generate",
            },
            "tempo": {
                "type": "integer",
                "minimum": 40,
                "maximum": 300,
                "description": "Tempo in BPM (default: 120)",
            },
            "time_signature": {
                "type": "string",
                "enum": ["4/4", "3/4", "2/4", "6/8", "2/2", "12/8", "5/4", "7/8"],
                "description": "Time signature (default: 4/4)",
            },
            "key": {
                "type": "string",
                "description": "Key signature (e.g., 'C', 'G', 'Am', 'F#m', 'Bb')",
            },
            "scale": {
                "type": "string",
                "enum": list(SCALES.keys()),
                "description": "Scale type for melody generation",
            },
            "duration_bars": {
                "type": "integer",
                "minimum": 1,
                "maximum": 64,
                "description": "Duration in bars (default: 4)",
            },
            "instrument": {
                "type": "string",
                "description": "Instrument name (e.g., 'piano', 'guitar', 'strings') or MIDI program number",
            },
            "notes": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "pitch": {"type": "string", "description": "Note name (e.g., 'C4', 'F#5')"},
                        "duration": {
                            "type": "string",
                            "description": "Duration ('whole', 'half', 'quarter', 'eighth', '16th')",
                        },
                        "velocity": {"type": "integer", "minimum": 0, "maximum": 127},
                    },
                },
                "description": "Explicit note sequence (overrides description-based generation)",
            },
            "progression": {
                "type": "string",
                "description": "Chord progression preset name (e.g., 'pop', 'jazz_251', 'blues_12bar')",
            },
            "output_file": {
                "type": "string",
                "description": "Output file path (optional, returns base64 if not specified)",
            },
        },
        "required": [],
    }

    async def execute(
        self,
        description: Optional[str] = None,
        tempo: int = 120,
        time_signature: str = "4/4",
        key: str = "C",
        scale: str = "major",
        duration_bars: int = 4,
        instrument: str = "piano",
        notes: Optional[list[dict]] = None,
        progression: Optional[str] = None,
        output_file: Optional[str] = None,
    ) -> ToolResult:
        """Generate a MIDI file."""
        if not MIDO_AVAILABLE:
            return ToolResult(
                success=False,
                output="",
                error="mido library not available. Install with: pip install mido",
            )

        try:
            log.info(
                "generating_midi",
                description=description,
                tempo=tempo,
                key=key,
                scale=scale,
                duration_bars=duration_bars,
            )

            # Create MIDI file
            mid = MidiFile(ticks_per_beat=480)
            track = MidiTrack()
            mid.tracks.append(track)

            # Set tempo
            microseconds_per_beat = int(60_000_000 / tempo)
            track.append(MetaMessage("set_tempo", tempo=microseconds_per_beat))

            # Set time signature
            num, denom = TIME_SIGNATURES.get(time_signature, (4, 4))
            track.append(
                MetaMessage(
                    "time_signature",
                    numerator=num,
                    denominator=denom,
                    clocks_per_click=24,
                    notated_32nd_notes_per_beat=8,
                )
            )

            # Set instrument
            program = self._get_instrument_program(instrument)
            track.append(Message("program_change", program=program, time=0))

            # Parse key
            root, mode = parse_key(key)
            actual_scale = scale if mode == "major" else "minor"

            # Generate notes
            if notes:
                # Use provided note sequence
                self._add_notes_to_track(track, notes, root)
            elif progression:
                # Generate chord progression
                self._add_progression_to_track(track, progression, root, mode, duration_bars)
            else:
                # Generate melody based on description or defaults
                self._generate_melody(track, root, actual_scale, duration_bars, time_signature)

            # Add end of track
            track.append(MetaMessage("end_of_track", time=0))

            # Save or return as base64
            if output_file:
                out_path = self._resolve_path(output_file)
                out_path.parent.mkdir(parents=True, exist_ok=True)
                mid.save(str(out_path))
                return ToolResult(
                    success=True,
                    output=f"MIDI file saved to: {out_path}",
                    metadata={
                        "output_file": str(out_path),
                        "tempo": tempo,
                        "key": key,
                        "time_signature": time_signature,
                        "duration_bars": duration_bars,
                    },
                )
            else:
                # Return as base64
                import io

                buffer = io.BytesIO()
                mid.save(file=buffer)
                buffer.seek(0)
                midi_data = base64.b64encode(buffer.read()).decode("utf-8")
                return ToolResult(
                    success=True,
                    output=f"Generated MIDI (base64):\n{midi_data[:200]}...",
                    metadata={
                        "midi_base64": midi_data,
                        "tempo": tempo,
                        "key": key,
                        "time_signature": time_signature,
                        "duration_bars": duration_bars,
                    },
                )

        except Exception as e:
            log.error("midi_generation_failed", error=str(e))
            return ToolResult(success=False, output="", error=f"MIDI generation failed: {str(e)}")

    def _get_instrument_program(self, instrument: str) -> int:
        """Get MIDI program number for instrument name."""
        if instrument.isdigit():
            return int(instrument) % 128

        instrument_lower = instrument.lower().replace(" ", "_").replace("-", "_")
        return GM_INSTRUMENTS.get(instrument_lower, 0)

    def _add_notes_to_track(
        self, track: "MidiTrack", notes: list[dict], root: int
    ) -> None:
        """Add explicit notes to track."""
        ticks_per_beat = 480

        for note_data in notes:
            pitch_str = note_data.get("pitch", "C4")
            duration_str = note_data.get("duration", "quarter")
            velocity = note_data.get("velocity", 80)

            midi_note, _ = parse_note(pitch_str)
            duration_ticks = duration_to_ticks(duration_str, ticks_per_beat)

            track.append(Message("note_on", note=midi_note, velocity=velocity, time=0))
            track.append(Message("note_off", note=midi_note, velocity=0, time=duration_ticks))

    def _add_progression_to_track(
        self,
        track: "MidiTrack",
        progression_name: str,
        root: int,
        mode: str,
        duration_bars: int,
    ) -> None:
        """Add chord progression to track."""
        ticks_per_beat = 480
        ticks_per_bar = ticks_per_beat * 4  # Assuming 4/4

        progression = PROGRESSIONS.get(progression_name, ["I", "IV", "V", "I"])

        # Repeat progression to fill duration
        chords = []
        while len(chords) < duration_bars:
            chords.extend(progression)
        chords = chords[:duration_bars]

        for i, chord_symbol in enumerate(chords):
            # Parse chord symbol
            is_minor = chord_symbol.islower()
            degree = chord_symbol.upper()

            semitone_offset = DEGREE_TO_SEMITONE.get(degree, 0)
            chord_root = (root + semitone_offset) % 12
            chord_type = "minor" if is_minor else "major"

            # Get chord notes
            chord_notes = get_chord_notes(chord_root, chord_type, octave=4)

            # Add chord
            for note in chord_notes:
                track.append(Message("note_on", note=note, velocity=70, time=0))

            track.append(
                Message("note_off", note=chord_notes[0], velocity=0, time=ticks_per_bar)
            )
            for note in chord_notes[1:]:
                track.append(Message("note_off", note=note, velocity=0, time=0))

    def _generate_melody(
        self,
        track: "MidiTrack",
        root: int,
        scale: str,
        duration_bars: int,
        time_signature: str,
    ) -> None:
        """Generate a simple melody using the scale."""
        import random

        ticks_per_beat = 480
        num, denom = TIME_SIGNATURES.get(time_signature, (4, 4))
        beats_per_bar = num
        ticks_per_bar = ticks_per_beat * beats_per_bar

        # Get scale notes
        scale_notes = get_scale_notes(root, scale, octave=4)
        # Add octave above
        scale_notes.extend([n + 12 for n in scale_notes[:3]])

        # Generate notes for each bar
        for bar in range(duration_bars):
            remaining_ticks = ticks_per_bar

            while remaining_ticks > 0:
                # Random note from scale
                note = random.choice(scale_notes)

                # Random duration (quarter, eighth, or half note)
                durations = [ticks_per_beat, ticks_per_beat // 2, ticks_per_beat * 2]
                duration = random.choice([d for d in durations if d <= remaining_ticks])

                velocity = random.randint(60, 100)

                track.append(Message("note_on", note=note, velocity=velocity, time=0))
                track.append(Message("note_off", note=note, velocity=0, time=duration))

                remaining_ticks -= duration


class GenerateABCTool(Tool):
    """Generate ABC notation from descriptions or parameters."""

    name = "generate_abc"
    description = """Generate ABC notation (text-based sheet music format).
    ABC notation is a simple text format for writing music that can be rendered
    to sheet music or converted to MIDI."""

    parameters = {
        "type": "object",
        "properties": {
            "description": {
                "type": "string",
                "description": "Natural language description of the music",
            },
            "title": {
                "type": "string",
                "description": "Title of the tune",
            },
            "composer": {
                "type": "string",
                "description": "Composer name",
            },
            "meter": {
                "type": "string",
                "description": "Time signature (e.g., '4/4', '3/4', '6/8')",
            },
            "key": {
                "type": "string",
                "description": "Key signature (e.g., 'C', 'G', 'Am', 'Dm')",
            },
            "tempo": {
                "type": "string",
                "description": "Tempo marking (e.g., '120' or '1/4=120')",
            },
            "notes": {
                "type": "string",
                "description": "ABC notation note string (e.g., 'CDEFGABc')",
            },
            "progression": {
                "type": "string",
                "description": "Chord progression preset (e.g., 'pop', 'blues_12bar')",
            },
            "style": {
                "type": "string",
                "enum": ["melody", "chords", "arpeggios"],
                "description": "Generation style",
            },
            "bars": {
                "type": "integer",
                "minimum": 1,
                "maximum": 64,
                "description": "Number of bars to generate",
            },
            "output_file": {
                "type": "string",
                "description": "Output file path (optional)",
            },
        },
        "required": [],
    }

    async def execute(
        self,
        description: Optional[str] = None,
        title: str = "Untitled",
        composer: str = "Sindri",
        meter: str = "4/4",
        key: str = "C",
        tempo: str = "120",
        notes: Optional[str] = None,
        progression: Optional[str] = None,
        style: str = "melody",
        bars: int = 4,
        output_file: Optional[str] = None,
    ) -> ToolResult:
        """Generate ABC notation."""
        try:
            log.info(
                "generating_abc",
                title=title,
                key=key,
                meter=meter,
                bars=bars,
            )

            # Build ABC header
            abc_lines = [
                f"X:1",
                f"T:{title}",
                f"C:{composer}",
                f"M:{meter}",
                f"L:1/8",
                f"Q:1/4={tempo}",
                f"K:{key}",
            ]

            # Generate notes section
            if notes:
                # Use provided notes
                abc_lines.append(notes)
            elif progression:
                # Generate from chord progression
                note_str = self._generate_progression_abc(progression, key, style, bars)
                abc_lines.append(note_str)
            else:
                # Generate simple melody
                note_str = self._generate_melody_abc(key, bars)
                abc_lines.append(note_str)

            abc_content = "\n".join(abc_lines)

            # Output
            if output_file:
                out_path = self._resolve_path(output_file)
                out_path.parent.mkdir(parents=True, exist_ok=True)
                out_path.write_text(abc_content)
                return ToolResult(
                    success=True,
                    output=f"ABC notation saved to: {out_path}\n\n```abc\n{abc_content}\n```",
                    metadata={
                        "output_file": str(out_path),
                        "title": title,
                        "key": key,
                        "meter": meter,
                    },
                )
            else:
                return ToolResult(
                    success=True,
                    output=f"```abc\n{abc_content}\n```",
                    metadata={
                        "title": title,
                        "key": key,
                        "meter": meter,
                        "abc_notation": abc_content,
                    },
                )

        except Exception as e:
            log.error("abc_generation_failed", error=str(e))
            return ToolResult(success=False, output="", error=f"ABC generation failed: {str(e)}")

    def _generate_melody_abc(self, key: str, bars: int) -> str:
        """Generate a simple ABC melody."""
        import random

        root, mode = parse_key(key)

        # ABC note names for major scale
        scale_notes = ["C", "D", "E", "F", "G", "A", "B", "c", "d", "e"]
        if mode == "minor":
            # Flatten the 3rd, 6th, 7th for natural minor
            scale_notes = ["C", "D", "_E", "F", "G", "_A", "_B", "c", "d", "_e"]

        # Transpose to key
        key_offset = root
        note_names = ["C", "^C", "D", "^D", "E", "F", "^F", "G", "^G", "A", "^A", "B"]

        lines = []
        for bar in range(bars):
            bar_notes = []
            remaining_eighths = 8  # 4/4 = 8 eighth notes

            while remaining_eighths > 0:
                note = random.choice(scale_notes)
                # Random duration (1, 2, or 4 eighth notes)
                duration = random.choice([d for d in [1, 2, 4] if d <= remaining_eighths])

                if duration == 1:
                    bar_notes.append(note)
                elif duration == 2:
                    bar_notes.append(note + "2")
                else:
                    bar_notes.append(note + "4")

                remaining_eighths -= duration

            lines.append("".join(bar_notes) + " |")

        return "\n".join(lines)

    def _generate_progression_abc(
        self, progression_name: str, key: str, style: str, bars: int
    ) -> str:
        """Generate ABC from chord progression."""
        progression = PROGRESSIONS.get(progression_name, ["I", "IV", "V", "I"])

        # Chord to ABC notation mapping (simplified)
        chord_notes = {
            "I": "[CEG]",
            "ii": "[DFA]",
            "iii": "[EGB]",
            "IV": "[FAc]",
            "V": "[GBd]",
            "vi": "[Ace]",
            "VII": "[Bdf]",
            "i": "[C_EG]",
        }

        # Generate bars
        lines = []
        for i in range(bars):
            chord = progression[i % len(progression)]
            chord_abc = chord_notes.get(chord, "[CEG]")

            if style == "arpeggios":
                # Break chord into arpeggio
                notes = chord_abc[1:-1]  # Remove brackets
                lines.append(f"{notes[0]}2{notes[1]}2{notes[2]}2{notes[0]}2 |")
            else:
                # Play chord as whole note
                lines.append(f'"{chord}"{chord_abc}4 z4 |')

        return "\n".join(lines)


class HarmonizeTool(Tool):
    """Add harmonies to a melody."""

    name = "harmonize"
    description = """Add harmony voices to a melody. Supports different harmonization
    styles including classical, jazz, pop, and folk."""

    parameters = {
        "type": "object",
        "properties": {
            "melody": {
                "type": "string",
                "description": "ABC notation melody string or path to ABC/MIDI file",
            },
            "style": {
                "type": "string",
                "enum": ["classical", "jazz", "pop", "folk"],
                "description": "Harmonization style",
            },
            "voice_count": {
                "type": "integer",
                "minimum": 2,
                "maximum": 4,
                "description": "Number of harmony voices (2-4)",
            },
            "key": {
                "type": "string",
                "description": "Key for harmonization (e.g., 'C', 'Am')",
            },
            "output_file": {
                "type": "string",
                "description": "Output file path",
            },
        },
        "required": ["melody"],
    }

    async def execute(
        self,
        melody: str,
        style: str = "classical",
        voice_count: int = 2,
        key: str = "C",
        output_file: Optional[str] = None,
    ) -> ToolResult:
        """Harmonize a melody."""
        try:
            log.info("harmonizing", style=style, voice_count=voice_count, key=key)

            # Check if melody is a file path
            melody_path = Path(melody) if not melody.startswith("X:") else None
            if melody_path and melody_path.exists():
                melody_content = melody_path.read_text()
            else:
                melody_content = melody

            # Parse key
            root, mode = parse_key(key)

            # Harmonization intervals based on style
            if style == "jazz":
                # Jazz uses more complex intervals (3rds, 7ths)
                intervals = [-3, -7, -12][:voice_count - 1]
            elif style == "pop":
                # Pop uses simple 3rds and 5ths
                intervals = [-4, -7][:voice_count - 1]
            elif style == "folk":
                # Folk uses parallel 3rds
                intervals = [-3][:voice_count - 1]
            else:  # classical
                # Classical uses proper voice leading
                intervals = [-4, -7, -12][:voice_count - 1]

            # Generate harmonized version
            if melody_content.startswith("X:"):
                # ABC notation - add harmony voices
                harmonized = self._harmonize_abc(melody_content, intervals, key)
            else:
                # Treat as raw notes
                harmonized = self._harmonize_notes(melody_content, intervals)

            if output_file:
                out_path = self._resolve_path(output_file)
                out_path.parent.mkdir(parents=True, exist_ok=True)
                out_path.write_text(harmonized)
                return ToolResult(
                    success=True,
                    output=f"Harmonized music saved to: {out_path}\n\n```abc\n{harmonized[:500]}...\n```",
                    metadata={
                        "output_file": str(out_path),
                        "style": style,
                        "voice_count": voice_count,
                    },
                )
            else:
                return ToolResult(
                    success=True,
                    output=f"```abc\n{harmonized}\n```",
                    metadata={
                        "style": style,
                        "voice_count": voice_count,
                        "harmonized_abc": harmonized,
                    },
                )

        except Exception as e:
            log.error("harmonization_failed", error=str(e))
            return ToolResult(
                success=False, output="", error=f"Harmonization failed: {str(e)}"
            )

    def _harmonize_abc(self, abc_content: str, intervals: list[int], key: str) -> str:
        """Add harmony to ABC notation."""
        lines = abc_content.split("\n")
        result_lines = []

        for line in lines:
            if line.startswith(("X:", "T:", "C:", "M:", "L:", "Q:", "K:")):
                result_lines.append(line)
            elif line.strip() and not line.startswith("%"):
                # This is a music line - add harmony
                # Simplified: wrap single notes in chords
                harmonized_line = self._add_harmony_to_line(line, intervals)
                result_lines.append(harmonized_line)
            else:
                result_lines.append(line)

        return "\n".join(result_lines)

    def _add_harmony_to_line(self, line: str, intervals: list[int]) -> str:
        """Add harmony notes to a line of ABC notation."""
        # Simple pattern: find single notes and add harmony
        result = []
        i = 0
        while i < len(line):
            char = line[i]

            # Check if this is a note (A-G or a-g)
            if char.upper() in "ABCDEFG" and (i == 0 or line[i - 1] not in "[]"):
                # Get full note with accidentals and duration
                note_match = re.match(r"([_^=]?)([A-Ga-g][,']*)(\d*/?[\d]*)", line[i:])
                if note_match:
                    accidental = note_match.group(1)
                    note = note_match.group(2)
                    duration = note_match.group(3)

                    # Create chord with harmony notes
                    chord = f"[{accidental}{note}"
                    for interval in intervals:
                        harmony_note = self._transpose_abc_note(note, interval)
                        chord += harmony_note
                    chord += f"]{duration}"

                    result.append(chord)
                    i += len(note_match.group(0))
                    continue

            result.append(char)
            i += 1

        return "".join(result)

    def _transpose_abc_note(self, note: str, semitones: int) -> str:
        """Transpose an ABC note by semitones."""
        # Simplified transposition
        note_order = ["C", "D", "E", "F", "G", "A", "B"]
        lower_order = ["c", "d", "e", "f", "g", "a", "b"]

        is_lower = note[0].islower()
        base_note = note[0].upper()
        octave_marks = note[1:] if len(note) > 1 else ""

        if base_note in note_order:
            idx = note_order.index(base_note)
            # Simple 3rd/5th transposition (ignoring accidentals for simplicity)
            steps = semitones // 2 if semitones < 0 else semitones // 2
            new_idx = (idx + steps) % 7

            if is_lower:
                new_note = lower_order[new_idx]
            else:
                new_note = note_order[new_idx]

            return new_note + octave_marks

        return note

    def _harmonize_notes(self, notes: str, intervals: list[int]) -> str:
        """Harmonize raw note input."""
        # Wrap in ABC format
        abc = f"X:1\nT:Harmonized\nM:4/4\nL:1/8\nK:C\n{notes}"
        return self._harmonize_abc(abc, intervals, "C")


class ArrangeTool(Tool):
    """Create multi-track arrangements from a source melody or chord progression."""

    name = "arrange"
    description = """Create a multi-instrument arrangement from a source melody or progression.
    Supports orchestral, band, quartet, and solo arrangements."""

    parameters = {
        "type": "object",
        "properties": {
            "source": {
                "type": "string",
                "description": "Input MIDI or ABC file path, or ABC notation string",
            },
            "instruments": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of instruments for the arrangement",
            },
            "style": {
                "type": "string",
                "enum": ["orchestral", "band", "quartet", "solo", "piano"],
                "description": "Arrangement style",
            },
            "output_file": {
                "type": "string",
                "description": "Output MIDI file path",
            },
        },
        "required": ["source"],
    }

    async def execute(
        self,
        source: str,
        instruments: Optional[list[str]] = None,
        style: str = "band",
        output_file: Optional[str] = None,
    ) -> ToolResult:
        """Create an arrangement."""
        if not MIDO_AVAILABLE:
            return ToolResult(
                success=False,
                output="",
                error="mido library not available. Install with: pip install mido",
            )

        try:
            log.info("arranging", style=style, instruments=instruments)

            # Default instruments by style
            if not instruments:
                instruments = self._get_default_instruments(style)

            # Load or parse source
            source_path = Path(source)
            if source_path.exists() and source_path.suffix.lower() == ".mid":
                mid = MidiFile(str(source_path))
            elif source_path.exists() and source_path.suffix.lower() == ".abc":
                # Convert ABC to MIDI first (simplified - just use original)
                abc_content = source_path.read_text()
                mid = self._abc_to_midi(abc_content)
            else:
                # Treat as ABC notation string
                mid = self._abc_to_midi(source)

            # Create arrangement
            arranged = self._create_arrangement(mid, instruments, style)

            if output_file:
                out_path = self._resolve_path(output_file)
                out_path.parent.mkdir(parents=True, exist_ok=True)
                arranged.save(str(out_path))
                return ToolResult(
                    success=True,
                    output=f"Arrangement saved to: {out_path}",
                    metadata={
                        "output_file": str(out_path),
                        "style": style,
                        "instruments": instruments,
                        "track_count": len(arranged.tracks),
                    },
                )
            else:
                # Return info about the arrangement
                return ToolResult(
                    success=True,
                    output=f"Created {style} arrangement with {len(instruments)} instruments: {', '.join(instruments)}",
                    metadata={
                        "style": style,
                        "instruments": instruments,
                        "track_count": len(arranged.tracks),
                    },
                )

        except Exception as e:
            log.error("arrangement_failed", error=str(e))
            return ToolResult(
                success=False, output="", error=f"Arrangement failed: {str(e)}"
            )

    def _get_default_instruments(self, style: str) -> list[str]:
        """Get default instruments for arrangement style."""
        styles = {
            "orchestral": ["violin", "viola", "cello", "flute", "oboe", "french_horn"],
            "band": ["guitar", "bass", "drums", "keyboard"],
            "quartet": ["violin", "violin", "viola", "cello"],
            "solo": ["piano"],
            "piano": ["piano"],
        }
        return styles.get(style, ["piano"])

    def _abc_to_midi(self, abc_content: str) -> "MidiFile":
        """Convert ABC notation to MIDI (simplified)."""
        mid = MidiFile(ticks_per_beat=480)
        track = MidiTrack()
        mid.tracks.append(track)

        track.append(MetaMessage("set_tempo", tempo=500000))  # 120 BPM

        # Parse simple ABC notes (very simplified)
        note_map = {"C": 60, "D": 62, "E": 64, "F": 65, "G": 67, "A": 69, "B": 71}
        note_map.update({k.lower(): v + 12 for k, v in note_map.items()})

        for char in abc_content:
            if char.upper() in note_map:
                note = note_map.get(char, 60)
                track.append(Message("note_on", note=note, velocity=80, time=0))
                track.append(Message("note_off", note=note, velocity=0, time=480))

        track.append(MetaMessage("end_of_track", time=0))
        return mid

    def _create_arrangement(
        self, source_mid: "MidiFile", instruments: list[str], style: str
    ) -> "MidiFile":
        """Create multi-track arrangement from source MIDI."""
        arranged = MidiFile(ticks_per_beat=source_mid.ticks_per_beat)

        # Get notes from source
        source_notes = []
        for track in source_mid.tracks:
            current_time = 0
            for msg in track:
                current_time += msg.time
                if msg.type == "note_on" and msg.velocity > 0:
                    source_notes.append(
                        {"note": msg.note, "time": current_time, "velocity": msg.velocity}
                    )

        # Create track for each instrument
        for i, instrument in enumerate(instruments):
            track = MidiTrack()
            arranged.tracks.append(track)

            # Set instrument
            program = GM_INSTRUMENTS.get(instrument.lower(), 0)
            track.append(Message("program_change", program=program, channel=i, time=0))

            # Add notes (with variation based on instrument)
            octave_offset = self._get_octave_offset(instrument, style)

            last_time = 0
            for note_data in source_notes:
                delta = note_data["time"] - last_time
                new_note = note_data["note"] + octave_offset
                new_note = max(21, min(108, new_note))  # Keep in piano range

                track.append(
                    Message(
                        "note_on",
                        note=new_note,
                        velocity=note_data["velocity"],
                        channel=i,
                        time=delta,
                    )
                )
                track.append(
                    Message("note_off", note=new_note, velocity=0, channel=i, time=480)
                )
                last_time = note_data["time"] + 480

            track.append(MetaMessage("end_of_track", time=0))

        return arranged

    def _get_octave_offset(self, instrument: str, style: str) -> int:
        """Get octave offset for instrument in arrangement."""
        offsets = {
            "bass": -24,
            "cello": -12,
            "viola": -5,
            "guitar": 0,
            "piano": 0,
            "violin": 0,
            "flute": 12,
            "oboe": 0,
            "clarinet": 0,
            "trumpet": 0,
        }
        return offsets.get(instrument.lower(), 0)


class AnalyzeMusicTool(Tool):
    """Analyze music to extract key, tempo, structure, and other properties."""

    name = "analyze_music"
    description = """Analyze a music file (MIDI or ABC) to extract musical properties
    including key signature, tempo, time signature, note statistics, and structure."""

    parameters = {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "Path to MIDI or ABC file to analyze",
            },
            "content": {
                "type": "string",
                "description": "ABC notation content to analyze (alternative to file_path)",
            },
            "analysis_type": {
                "type": "string",
                "enum": ["full", "key", "tempo", "structure", "chords", "statistics"],
                "description": "Type of analysis to perform",
            },
        },
        "required": [],
    }

    async def execute(
        self,
        file_path: Optional[str] = None,
        content: Optional[str] = None,
        analysis_type: str = "full",
    ) -> ToolResult:
        """Analyze music file or content."""
        try:
            log.info("analyzing_music", file_path=file_path, analysis_type=analysis_type)

            if file_path:
                path = self._resolve_path(file_path)
                if not path.exists():
                    return ToolResult(
                        success=False,
                        output="",
                        error=f"File not found: {file_path}",
                    )

                if path.suffix.lower() in [".mid", ".midi"]:
                    analysis = self._analyze_midi(path, analysis_type)
                elif path.suffix.lower() == ".abc":
                    content = path.read_text()
                    analysis = self._analyze_abc(content, analysis_type)
                else:
                    return ToolResult(
                        success=False,
                        output="",
                        error=f"Unsupported file format: {path.suffix}",
                    )
            elif content:
                analysis = self._analyze_abc(content, analysis_type)
            else:
                return ToolResult(
                    success=False,
                    output="",
                    error="Either file_path or content must be provided",
                )

            # Format output
            output = json.dumps(analysis, indent=2)
            return ToolResult(
                success=True,
                output=f"Music Analysis:\n```json\n{output}\n```",
                metadata={"analysis": analysis},
            )

        except Exception as e:
            log.error("music_analysis_failed", error=str(e))
            return ToolResult(
                success=False, output="", error=f"Music analysis failed: {str(e)}"
            )

    def _analyze_midi(self, path: Path, analysis_type: str) -> dict[str, Any]:
        """Analyze a MIDI file."""
        if not MIDO_AVAILABLE:
            return {"error": "mido library not available"}

        mid = MidiFile(str(path))
        analysis = {
            "format": "MIDI",
            "file": str(path),
            "ticks_per_beat": mid.ticks_per_beat,
            "track_count": len(mid.tracks),
        }

        # Collect all notes
        all_notes = []
        tempo = 500000  # Default: 120 BPM
        time_sig = (4, 4)

        for track in mid.tracks:
            for msg in track:
                if msg.type == "set_tempo":
                    tempo = msg.tempo
                elif msg.type == "time_signature":
                    time_sig = (msg.numerator, msg.denominator)
                elif msg.type == "note_on" and msg.velocity > 0:
                    all_notes.append(msg.note)

        # Calculate BPM
        bpm = 60_000_000 / tempo
        analysis["tempo_bpm"] = round(bpm, 1)
        analysis["time_signature"] = f"{time_sig[0]}/{time_sig[1]}"

        if analysis_type in ["full", "key"]:
            analysis["detected_key"] = self._detect_key(all_notes)

        if analysis_type in ["full", "statistics"]:
            if all_notes:
                analysis["statistics"] = {
                    "total_notes": len(all_notes),
                    "unique_pitches": len(set(all_notes)),
                    "lowest_note": midi_to_note_name(min(all_notes)),
                    "highest_note": midi_to_note_name(max(all_notes)),
                    "average_pitch": round(sum(all_notes) / len(all_notes), 1),
                }

        if analysis_type in ["full", "structure"]:
            analysis["duration_seconds"] = round(mid.length, 2)

        return analysis

    def _analyze_abc(self, content: str, analysis_type: str) -> dict[str, Any]:
        """Analyze ABC notation content."""
        analysis = {"format": "ABC"}

        lines = content.split("\n")
        for line in lines:
            if line.startswith("T:"):
                analysis["title"] = line[2:].strip()
            elif line.startswith("M:"):
                analysis["meter"] = line[2:].strip()
            elif line.startswith("K:"):
                analysis["key"] = line[2:].strip()
            elif line.startswith("Q:"):
                analysis["tempo"] = line[2:].strip()
            elif line.startswith("C:"):
                analysis["composer"] = line[2:].strip()

        # Count notes
        note_count = 0
        for line in lines:
            if not line.startswith(("X:", "T:", "M:", "K:", "Q:", "C:", "L:", "%")):
                note_count += len(re.findall(r"[A-Ga-g]", line))

        if analysis_type in ["full", "statistics"]:
            analysis["statistics"] = {"note_count": note_count}

        return analysis

    def _detect_key(self, notes: list[int]) -> str:
        """Detect the key from a list of MIDI notes."""
        if not notes:
            return "Unknown"

        # Count pitch classes
        pitch_classes = [0] * 12
        for note in notes:
            pitch_classes[note % 12] += 1

        # Simple key detection: find the pitch class with highest count
        # and check if it matches major or minor scale patterns
        max_pc = pitch_classes.index(max(pitch_classes))

        note_names = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

        # Check major scale fit
        major_scale = [0, 2, 4, 5, 7, 9, 11]
        major_score = sum(pitch_classes[(max_pc + i) % 12] for i in major_scale)

        # Check minor scale fit
        minor_scale = [0, 2, 3, 5, 7, 8, 10]
        minor_root = (max_pc + 9) % 12  # Relative minor
        minor_score = sum(pitch_classes[(minor_root + i) % 12] for i in minor_scale)

        if minor_score > major_score:
            return f"{note_names[minor_root]}m"
        else:
            return note_names[max_pc]


class ExportAudioTool(Tool):
    """Export MIDI to audio format (WAV/MP3)."""

    name = "export_audio"
    description = """Convert a MIDI file to audio (WAV or MP3) using FluidSynth.
    Requires FluidSynth and a SoundFont file to be installed."""

    parameters = {
        "type": "object",
        "properties": {
            "midi_file": {
                "type": "string",
                "description": "Path to the input MIDI file",
            },
            "output_file": {
                "type": "string",
                "description": "Path for the output audio file",
            },
            "format": {
                "type": "string",
                "enum": ["wav", "mp3"],
                "description": "Output audio format",
            },
            "soundfont": {
                "type": "string",
                "description": "Path to SoundFont file (optional, uses default if not specified)",
            },
            "sample_rate": {
                "type": "integer",
                "enum": [22050, 44100, 48000],
                "description": "Sample rate in Hz",
            },
        },
        "required": ["midi_file", "output_file"],
    }

    async def execute(
        self,
        midi_file: str,
        output_file: str,
        format: str = "wav",
        soundfont: Optional[str] = None,
        sample_rate: int = 44100,
    ) -> ToolResult:
        """Export MIDI to audio."""
        try:
            log.info(
                "exporting_audio",
                midi_file=midi_file,
                output_file=output_file,
                format=format,
            )

            midi_path = self._resolve_path(midi_file)
            if not midi_path.exists():
                return ToolResult(
                    success=False,
                    output="",
                    error=f"MIDI file not found: {midi_file}",
                )

            out_path = self._resolve_path(output_file)
            out_path.parent.mkdir(parents=True, exist_ok=True)

            # Try using midi2audio (FluidSynth wrapper)
            if FLUIDSYNTH_AVAILABLE:
                return await self._export_with_fluidsynth(
                    midi_path, out_path, soundfont, sample_rate
                )

            # Try using fluidsynth directly via subprocess
            return await self._export_with_subprocess(
                midi_path, out_path, soundfont, sample_rate, format
            )

        except Exception as e:
            log.error("audio_export_failed", error=str(e))
            return ToolResult(
                success=False, output="", error=f"Audio export failed: {str(e)}"
            )

    async def _export_with_fluidsynth(
        self,
        midi_path: Path,
        out_path: Path,
        soundfont: Optional[str],
        sample_rate: int,
    ) -> ToolResult:
        """Export using midi2audio library."""
        # Find soundfont
        sf_path = soundfont
        if not sf_path:
            # Try common locations
            common_paths = [
                "/usr/share/soundfonts/default.sf2",
                "/usr/share/sounds/sf2/FluidR3_GM.sf2",
                "/usr/share/soundfonts/FluidR3_GM.sf2",
                "~/.local/share/soundfonts/default.sf2",
            ]
            for path in common_paths:
                expanded = Path(path).expanduser()
                if expanded.exists():
                    sf_path = str(expanded)
                    break

        if not sf_path:
            return ToolResult(
                success=False,
                output="",
                error="No SoundFont file found. Please specify a soundfont path or install FluidR3_GM.sf2",
            )

        fs = FluidSynth(sf_path, sample_rate=sample_rate)
        fs.midi_to_audio(str(midi_path), str(out_path))

        return ToolResult(
            success=True,
            output=f"Audio exported to: {out_path}",
            metadata={
                "output_file": str(out_path),
                "soundfont": sf_path,
                "sample_rate": sample_rate,
            },
        )

    async def _export_with_subprocess(
        self,
        midi_path: Path,
        out_path: Path,
        soundfont: Optional[str],
        sample_rate: int,
        format: str,
    ) -> ToolResult:
        """Export using fluidsynth subprocess."""
        # Check if fluidsynth is available
        try:
            subprocess.run(["fluidsynth", "--version"], capture_output=True, check=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            return ToolResult(
                success=False,
                output="",
                error="FluidSynth not available. Install with: pacman -S fluidsynth",
            )

        # Find soundfont
        sf_path = soundfont
        if not sf_path:
            common_paths = [
                "/usr/share/soundfonts/default.sf2",
                "/usr/share/sounds/sf2/FluidR3_GM.sf2",
            ]
            for path in common_paths:
                if Path(path).exists():
                    sf_path = path
                    break

        if not sf_path:
            return ToolResult(
                success=False,
                output="",
                error="No SoundFont file found",
            )

        # Run fluidsynth
        wav_path = out_path.with_suffix(".wav")
        cmd = [
            "fluidsynth",
            "-ni",
            sf_path,
            str(midi_path),
            "-F",
            str(wav_path),
            "-r",
            str(sample_rate),
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            return ToolResult(
                success=False,
                output="",
                error=f"FluidSynth failed: {result.stderr}",
            )

        # Convert to mp3 if needed
        if format == "mp3":
            try:
                subprocess.run(
                    ["ffmpeg", "-i", str(wav_path), "-y", str(out_path)],
                    capture_output=True,
                    check=True,
                )
                wav_path.unlink()  # Remove intermediate wav
            except (subprocess.CalledProcessError, FileNotFoundError):
                return ToolResult(
                    success=False,
                    output="",
                    error="ffmpeg not available for MP3 conversion",
                )

        return ToolResult(
            success=True,
            output=f"Audio exported to: {out_path}",
            metadata={
                "output_file": str(out_path),
                "soundfont": sf_path,
                "sample_rate": sample_rate,
                "format": format,
            },
        )


# Export all tools
__all__ = [
    "GenerateMIDITool",
    "GenerateABCTool",
    "HarmonizeTool",
    "ArrangeTool",
    "AnalyzeMusicTool",
    "ExportAudioTool",
    "MIDO_AVAILABLE",
    "FLUIDSYNTH_AVAILABLE",
]
