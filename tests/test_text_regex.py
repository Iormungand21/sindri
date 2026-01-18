"""Tests for text and regex processing tools (Phase 12)."""

import pytest

from sindri.tools.text_regex import (
    RegexGenerateTool,
    RegexExplainTool,
    RegexTestTool,
    TextTransformTool,
    TextExtractTool,
)


# ═══════════════════════════════════════════════════════════════════════════════
# RegexGenerateTool Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestRegexGenerateTool:
    """Test suite for regex pattern generation."""

    @pytest.fixture
    def tool(self):
        return RegexGenerateTool()

    @pytest.mark.asyncio
    async def test_generate_email_pattern(self, tool):
        """Test generating email pattern from description."""
        result = await tool.execute(description="Match email addresses")

        assert result.success
        assert "pattern" in result.metadata
        assert "@" in result.metadata["pattern"]
        assert result.metadata["pattern_name"] == "email"

    @pytest.mark.asyncio
    async def test_generate_url_pattern(self, tool):
        """Test generating URL pattern from description."""
        result = await tool.execute(description="Match URLs")

        assert result.success
        assert "http" in result.metadata["pattern"].lower()
        assert result.metadata["pattern_name"] == "url"

    @pytest.mark.asyncio
    async def test_generate_phone_us_pattern(self, tool):
        """Test generating US phone number pattern."""
        result = await tool.execute(description="Match US phone numbers")

        assert result.success
        assert "pattern" in result.metadata
        assert "phone" in result.metadata["pattern_name"]

    @pytest.mark.asyncio
    async def test_generate_ipv4_pattern(self, tool):
        """Test generating IPv4 pattern."""
        result = await tool.execute(description="Match IP addresses")

        assert result.success
        assert "pattern" in result.metadata
        assert "ip" in result.metadata["pattern_name"]

    @pytest.mark.asyncio
    async def test_generate_date_iso_pattern(self, tool):
        """Test generating ISO date pattern."""
        result = await tool.execute(description="Match ISO dates like 2024-01-15")

        assert result.success
        assert "\\d" in result.metadata["pattern"]
        assert "date" in result.metadata["pattern_name"]

    @pytest.mark.asyncio
    async def test_generate_uuid_pattern(self, tool):
        """Test generating UUID pattern."""
        result = await tool.execute(description="Match UUIDs")

        assert result.success
        assert result.metadata["pattern_name"] == "uuid"

    @pytest.mark.asyncio
    async def test_generate_hex_color_pattern(self, tool):
        """Test generating hex color pattern."""
        result = await tool.execute(description="Match hex colors")

        assert result.success
        assert "#" in result.metadata["pattern"]
        assert result.metadata["pattern_name"] == "hex_color"

    @pytest.mark.asyncio
    async def test_generate_with_examples(self, tool):
        """Test generating pattern with positive examples."""
        result = await tool.execute(
            description="Match these codes",
            examples=["AB-123", "CD-456", "EF-789"],
        )

        assert result.success
        assert "pattern" in result.metadata

    @pytest.mark.asyncio
    async def test_generate_with_negative_examples(self, tool):
        """Test generating pattern with negative examples."""
        result = await tool.execute(
            description="Match email addresses",
            examples=["test@example.com"],
            negative_examples=["notanemail", "missing@domain"],
        )

        assert result.success
        assert "[PASS]" in result.output
        assert "test@example.com" in result.output

    @pytest.mark.asyncio
    async def test_generate_anchored_pattern(self, tool):
        """Test generating anchored pattern."""
        result = await tool.execute(
            description="Match email addresses",
            anchored=True,
        )

        assert result.success
        pattern = result.metadata["pattern"]
        assert pattern.startswith("^")
        assert pattern.endswith("$")

    @pytest.mark.asyncio
    async def test_generate_case_insensitive(self, tool):
        """Test generating with case insensitive hint."""
        result = await tool.execute(
            description="Match email addresses",
            case_insensitive=True,
        )

        assert result.success
        assert "IGNORECASE" in result.output

    @pytest.mark.asyncio
    async def test_generate_javascript_flavor(self, tool):
        """Test generating pattern with JavaScript flavor."""
        result = await tool.execute(
            description="Match email addresses",
            flavor="javascript",
        )

        assert result.success
        assert "JavaScript" in result.output

    @pytest.mark.asyncio
    async def test_generate_starts_with(self, tool):
        """Test generating pattern from 'starts with' description."""
        result = await tool.execute(description="Match words starting with 'test'")

        assert result.success
        pattern = result.metadata["pattern"]
        assert "^" in pattern or "\\b" in pattern

    @pytest.mark.asyncio
    async def test_generate_ends_with(self, tool):
        """Test generating pattern from 'ends with' description."""
        result = await tool.execute(description="Match strings ending with '.txt'")

        assert result.success
        pattern = result.metadata["pattern"]
        assert "$" in pattern or "txt" in pattern

    @pytest.mark.asyncio
    async def test_generate_contains(self, tool):
        """Test generating pattern from 'contains' description."""
        result = await tool.execute(description="Match strings containing 'error'")

        assert result.success
        assert "error" in result.metadata["pattern"]

    @pytest.mark.asyncio
    async def test_generate_digits_only(self, tool):
        """Test generating digits-only pattern."""
        result = await tool.execute(description="Match strings with only digits")

        assert result.success
        assert "\\d" in result.metadata["pattern"]

    @pytest.mark.asyncio
    async def test_generate_unknown_returns_error(self, tool):
        """Test that unknown patterns return helpful error."""
        result = await tool.execute(
            description="Match something completely unusual and undefinable"
        )

        # Should fail with helpful message
        assert not result.success
        assert "Could not generate pattern" in result.error


# ═══════════════════════════════════════════════════════════════════════════════
# RegexExplainTool Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestRegexExplainTool:
    """Test suite for regex pattern explanation."""

    @pytest.fixture
    def tool(self):
        return RegexExplainTool()

    @pytest.mark.asyncio
    async def test_explain_simple_pattern(self, tool):
        """Test explaining a simple pattern."""
        result = await tool.execute(pattern=r"\d+")

        assert result.success
        assert "digit" in result.output.lower()
        assert "Breakdown" in result.output

    @pytest.mark.asyncio
    async def test_explain_email_pattern(self, tool):
        """Test explaining email pattern."""
        result = await tool.execute(
            pattern=r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"
        )

        assert result.success
        assert "email" in result.output.lower()

    @pytest.mark.asyncio
    async def test_explain_anchors(self, tool):
        """Test explaining anchor metacharacters."""
        result = await tool.execute(pattern=r"^hello$")

        assert result.success
        assert "start" in result.output.lower()
        assert "end" in result.output.lower()

    @pytest.mark.asyncio
    async def test_explain_character_class(self, tool):
        """Test explaining character class."""
        result = await tool.execute(pattern=r"[a-z]+")

        assert result.success
        assert "character" in result.output.lower() or "class" in result.output.lower()

    @pytest.mark.asyncio
    async def test_explain_negated_character_class(self, tool):
        """Test explaining negated character class."""
        result = await tool.execute(pattern=r"[^0-9]+")

        assert result.success
        assert "not" in result.output.lower() or "negated" in result.output.lower()

    @pytest.mark.asyncio
    async def test_explain_quantifiers(self, tool):
        """Test explaining quantifiers."""
        result = await tool.execute(pattern=r"\w{3,5}")

        assert result.success
        assert "3" in result.output
        assert "5" in result.output

    @pytest.mark.asyncio
    async def test_explain_groups(self, tool):
        """Test explaining capturing groups."""
        result = await tool.execute(pattern=r"(\w+)@(\w+\.com)")

        assert result.success
        assert "group" in result.output.lower()

    @pytest.mark.asyncio
    async def test_explain_named_group(self, tool):
        """Test explaining named capturing group."""
        result = await tool.execute(pattern=r"(?P<name>\w+)")

        assert result.success
        assert "name" in result.output.lower()

    @pytest.mark.asyncio
    async def test_explain_lookahead(self, tool):
        """Test explaining lookahead."""
        result = await tool.execute(pattern=r"\w+(?=@)")

        assert result.success
        assert "lookahead" in result.output.lower()

    @pytest.mark.asyncio
    async def test_explain_lookbehind(self, tool):
        """Test explaining lookbehind."""
        result = await tool.execute(pattern=r"(?<=@)\w+")

        assert result.success
        assert "lookbehind" in result.output.lower()

    @pytest.mark.asyncio
    async def test_explain_invalid_pattern_returns_error(self, tool):
        """Test that invalid pattern returns error."""
        result = await tool.execute(pattern=r"[unclosed")

        assert not result.success
        assert "Invalid regex" in result.error

    @pytest.mark.asyncio
    async def test_explain_verbose_mode(self, tool):
        """Test verbose explanation mode."""
        result = await tool.execute(pattern=r"\d+", verbose=True)

        assert result.success
        assert "Breakdown" in result.output


# ═══════════════════════════════════════════════════════════════════════════════
# RegexTestTool Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestRegexTestTool:
    """Test suite for regex pattern testing."""

    @pytest.fixture
    def tool(self):
        return RegexTestTool()

    @pytest.mark.asyncio
    async def test_simple_match(self, tool):
        """Test simple pattern matching."""
        result = await tool.execute(
            pattern=r"\d+",
            text="The number is 42",
        )

        assert result.success
        assert result.metadata["match_count"] == 1
        assert result.metadata["matches"][0]["match"] == "42"

    @pytest.mark.asyncio
    async def test_find_all_matches(self, tool):
        """Test finding all matches."""
        result = await tool.execute(
            pattern=r"\d+",
            text="Numbers: 1, 22, 333, 4444",
            find_all=True,
        )

        assert result.success
        assert result.metadata["match_count"] == 4

    @pytest.mark.asyncio
    async def test_find_first_match_only(self, tool):
        """Test finding only first match."""
        result = await tool.execute(
            pattern=r"\d+",
            text="Numbers: 1, 22, 333",
            find_all=False,
        )

        assert result.success
        assert result.metadata["match_count"] == 1
        assert result.metadata["matches"][0]["match"] == "1"

    @pytest.mark.asyncio
    async def test_no_match(self, tool):
        """Test when pattern doesn't match."""
        result = await tool.execute(
            pattern=r"\d+",
            text="No numbers here",
        )

        assert result.success
        assert result.metadata["match_count"] == 0
        assert "No matches" in result.output

    @pytest.mark.asyncio
    async def test_capturing_groups(self, tool):
        """Test capturing groups in matches."""
        result = await tool.execute(
            pattern=r"(\w+)@(\w+\.\w+)",
            text="Contact: user@example.com",
        )

        assert result.success
        assert len(result.metadata["matches"][0]["groups"]) == 2
        assert result.metadata["matches"][0]["groups"][0] == "user"
        assert result.metadata["matches"][0]["groups"][1] == "example.com"

    @pytest.mark.asyncio
    async def test_named_groups(self, tool):
        """Test named capturing groups."""
        result = await tool.execute(
            pattern=r"(?P<user>\w+)@(?P<domain>\w+\.\w+)",
            text="Contact: user@example.com",
        )

        assert result.success
        assert "named_groups" in result.metadata["matches"][0]
        assert result.metadata["matches"][0]["named_groups"]["user"] == "user"
        assert result.metadata["matches"][0]["named_groups"]["domain"] == "example.com"

    @pytest.mark.asyncio
    async def test_ignorecase_flag(self, tool):
        """Test case-insensitive matching."""
        result = await tool.execute(
            pattern=r"hello",
            text="HELLO World",
            flags=["ignorecase"],
        )

        assert result.success
        assert result.metadata["match_count"] == 1
        assert "IGNORECASE" in result.metadata["flags"]

    @pytest.mark.asyncio
    async def test_multiline_flag(self, tool):
        """Test multiline matching."""
        result = await tool.execute(
            pattern=r"^line",
            text="line1\nline2\nline3",
            flags=["multiline"],
            find_all=True,
        )

        assert result.success
        assert result.metadata["match_count"] == 3

    @pytest.mark.asyncio
    async def test_dotall_flag(self, tool):
        """Test dotall flag (dot matches newline)."""
        result = await tool.execute(
            pattern=r"first.*second",
            text="first\nsecond",
            flags=["dotall"],
        )

        assert result.success
        assert result.metadata["match_count"] == 1

    @pytest.mark.asyncio
    async def test_match_positions(self, tool):
        """Test match positions are returned."""
        result = await tool.execute(
            pattern=r"world",
            text="Hello world!",
        )

        assert result.success
        match = result.metadata["matches"][0]
        assert match["start"] == 6
        assert match["end"] == 11

    @pytest.mark.asyncio
    async def test_invalid_pattern_returns_error(self, tool):
        """Test that invalid pattern returns error."""
        result = await tool.execute(
            pattern=r"[invalid",
            text="test",
        )

        assert not result.success
        assert "Invalid regex" in result.error

    @pytest.mark.asyncio
    async def test_context_shown(self, tool):
        """Test that match context is shown."""
        result = await tool.execute(
            pattern=r"world",
            text="Hello world!",
        )

        assert result.success
        assert "Context" in result.output


# ═══════════════════════════════════════════════════════════════════════════════
# TextTransformTool Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestTextTransformTool:
    """Test suite for text transformations."""

    @pytest.fixture
    def tool(self):
        return TextTransformTool()

    @pytest.mark.asyncio
    async def test_transform_upper(self, tool):
        """Test uppercase transformation."""
        result = await tool.execute(text="hello world", transform="upper")

        assert result.success
        assert result.metadata["result"] == "HELLO WORLD"

    @pytest.mark.asyncio
    async def test_transform_lower(self, tool):
        """Test lowercase transformation."""
        result = await tool.execute(text="HELLO WORLD", transform="lower")

        assert result.success
        assert result.metadata["result"] == "hello world"

    @pytest.mark.asyncio
    async def test_transform_title(self, tool):
        """Test title case transformation."""
        result = await tool.execute(text="hello world", transform="title")

        assert result.success
        assert result.metadata["result"] == "Hello World"

    @pytest.mark.asyncio
    async def test_transform_capitalize(self, tool):
        """Test capitalize transformation."""
        result = await tool.execute(text="hello world", transform="capitalize")

        assert result.success
        assert result.metadata["result"] == "Hello world"

    @pytest.mark.asyncio
    async def test_transform_swapcase(self, tool):
        """Test swap case transformation."""
        result = await tool.execute(text="Hello World", transform="swapcase")

        assert result.success
        assert result.metadata["result"] == "hELLO wORLD"

    @pytest.mark.asyncio
    async def test_transform_strip(self, tool):
        """Test strip transformation."""
        result = await tool.execute(text="  hello  ", transform="strip")

        assert result.success
        assert result.metadata["result"] == "hello"

    @pytest.mark.asyncio
    async def test_transform_lstrip(self, tool):
        """Test left strip transformation."""
        result = await tool.execute(text="  hello  ", transform="lstrip")

        assert result.success
        assert result.metadata["result"] == "hello  "

    @pytest.mark.asyncio
    async def test_transform_rstrip(self, tool):
        """Test right strip transformation."""
        result = await tool.execute(text="  hello  ", transform="rstrip")

        assert result.success
        assert result.metadata["result"] == "  hello"

    @pytest.mark.asyncio
    async def test_transform_snake_case(self, tool):
        """Test snake_case transformation."""
        result = await tool.execute(text="HelloWorld", transform="snake_case")

        assert result.success
        assert result.metadata["result"] == "hello_world"

    @pytest.mark.asyncio
    async def test_transform_snake_case_from_spaces(self, tool):
        """Test snake_case from spaced text."""
        result = await tool.execute(text="Hello World", transform="snake_case")

        assert result.success
        assert result.metadata["result"] == "hello_world"

    @pytest.mark.asyncio
    async def test_transform_camel_case(self, tool):
        """Test camelCase transformation."""
        result = await tool.execute(text="hello_world", transform="camel_case")

        assert result.success
        assert result.metadata["result"] == "helloWorld"

    @pytest.mark.asyncio
    async def test_transform_pascal_case(self, tool):
        """Test PascalCase transformation."""
        result = await tool.execute(text="hello_world", transform="pascal_case")

        assert result.success
        assert result.metadata["result"] == "HelloWorld"

    @pytest.mark.asyncio
    async def test_transform_kebab_case(self, tool):
        """Test kebab-case transformation."""
        result = await tool.execute(text="HelloWorld", transform="kebab_case")

        assert result.success
        assert result.metadata["result"] == "hello-world"

    @pytest.mark.asyncio
    async def test_transform_slugify(self, tool):
        """Test slugify transformation."""
        result = await tool.execute(text="Hello World! 123", transform="slugify")

        assert result.success
        assert result.metadata["result"] == "hello-world-123"

    @pytest.mark.asyncio
    async def test_transform_reverse(self, tool):
        """Test reverse transformation."""
        result = await tool.execute(text="hello", transform="reverse")

        assert result.success
        assert result.metadata["result"] == "olleh"

    @pytest.mark.asyncio
    async def test_transform_normalize_whitespace(self, tool):
        """Test whitespace normalization."""
        result = await tool.execute(text="hello    world", transform="normalize_whitespace")

        assert result.success
        assert result.metadata["result"] == "hello world"

    @pytest.mark.asyncio
    async def test_transform_remove_punctuation(self, tool):
        """Test punctuation removal."""
        result = await tool.execute(text="Hello, World!", transform="remove_punctuation")

        assert result.success
        assert result.metadata["result"] == "Hello World"

    @pytest.mark.asyncio
    async def test_transform_replace(self, tool):
        """Test simple replacement."""
        result = await tool.execute(
            text="hello world",
            transform="replace",
            pattern="world",
            replacement="universe",
        )

        assert result.success
        assert result.metadata["result"] == "hello universe"

    @pytest.mark.asyncio
    async def test_transform_replace_without_pattern_fails(self, tool):
        """Test that replace without pattern fails."""
        result = await tool.execute(
            text="hello world",
            transform="replace",
        )

        assert not result.success
        assert "'pattern' is required" in result.error

    @pytest.mark.asyncio
    async def test_transform_regex_replace(self, tool):
        """Test regex replacement."""
        result = await tool.execute(
            text="Hello 123 World 456",
            transform="regex_replace",
            pattern=r"\d+",
            replacement="###",
        )

        assert result.success
        assert result.metadata["result"] == "Hello ### World ###"

    @pytest.mark.asyncio
    async def test_transform_regex_replace_invalid_pattern(self, tool):
        """Test regex replace with invalid pattern."""
        result = await tool.execute(
            text="hello",
            transform="regex_replace",
            pattern=r"[invalid",
            replacement="x",
        )

        assert not result.success
        assert "Invalid regex" in result.error

    @pytest.mark.asyncio
    async def test_transform_unknown_type_fails(self, tool):
        """Test that unknown transform type fails."""
        result = await tool.execute(text="hello", transform="nonexistent")

        assert not result.success
        assert "Unknown transform" in result.error


# ═══════════════════════════════════════════════════════════════════════════════
# TextExtractTool Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestTextExtractTool:
    """Test suite for text pattern extraction."""

    @pytest.fixture
    def tool(self):
        return TextExtractTool()

    @pytest.mark.asyncio
    async def test_extract_simple_pattern(self, tool):
        """Test extracting simple patterns."""
        result = await tool.execute(
            text="Numbers: 1, 22, 333",
            pattern=r"\d+",
        )

        assert result.success
        assert result.metadata["match_count"] == 3
        matches = [e["match"] for e in result.metadata["extractions"]]
        assert matches == ["1", "22", "333"]

    @pytest.mark.asyncio
    async def test_extract_emails(self, tool):
        """Test extracting email addresses."""
        result = await tool.execute(
            text="Contact us at info@example.com or support@test.org",
            pattern=r"[\w.+-]+@[\w.-]+\.\w+",
        )

        assert result.success
        assert result.metadata["match_count"] == 2
        matches = [e["match"] for e in result.metadata["extractions"]]
        assert "info@example.com" in matches
        assert "support@test.org" in matches

    @pytest.mark.asyncio
    async def test_extract_with_groups(self, tool):
        """Test extracting with capturing groups."""
        result = await tool.execute(
            text="Dates: 2024-01-15 and 2024-02-20",
            pattern=r"(\d{4})-(\d{2})-(\d{2})",
        )

        assert result.success
        assert result.metadata["match_count"] == 2
        first_match = result.metadata["extractions"][0]
        assert first_match["groups"] == ["2024", "01", "15"]

    @pytest.mark.asyncio
    async def test_extract_with_named_groups(self, tool):
        """Test extracting with named capturing groups."""
        result = await tool.execute(
            text="Date: 2024-01-15",
            pattern=r"(?P<year>\d{4})-(?P<month>\d{2})-(?P<day>\d{2})",
        )

        assert result.success
        first_match = result.metadata["extractions"][0]
        assert "named_groups" in first_match
        assert first_match["named_groups"]["year"] == "2024"
        assert first_match["named_groups"]["month"] == "01"
        assert first_match["named_groups"]["day"] == "15"

    @pytest.mark.asyncio
    async def test_extract_unique(self, tool):
        """Test extracting unique matches only."""
        result = await tool.execute(
            text="apple banana apple cherry apple",
            pattern=r"\w+",
            unique=True,
        )

        assert result.success
        matches = [e["match"] for e in result.metadata["extractions"]]
        assert matches == ["apple", "banana", "cherry"]

    @pytest.mark.asyncio
    async def test_extract_max_matches(self, tool):
        """Test limiting number of matches."""
        result = await tool.execute(
            text="1 2 3 4 5 6 7 8 9 10",
            pattern=r"\d+",
            max_matches=3,
        )

        assert result.success
        assert result.metadata["match_count"] == 3
        matches = [e["match"] for e in result.metadata["extractions"]]
        assert matches == ["1", "2", "3"]

    @pytest.mark.asyncio
    async def test_extract_with_ignorecase_flag(self, tool):
        """Test extracting with case-insensitive flag."""
        result = await tool.execute(
            text="Apple BANANA Cherry",
            pattern=r"apple|banana|cherry",
            flags=["ignorecase"],
        )

        assert result.success
        assert result.metadata["match_count"] == 3

    @pytest.mark.asyncio
    async def test_extract_multiline_flag(self, tool):
        """Test extracting with multiline flag."""
        result = await tool.execute(
            text="line1\nline2\nline3",
            pattern=r"^line\d",
            flags=["multiline"],
        )

        assert result.success
        assert result.metadata["match_count"] == 3

    @pytest.mark.asyncio
    async def test_extract_no_matches(self, tool):
        """Test extracting when no matches."""
        result = await tool.execute(
            text="no numbers here",
            pattern=r"\d+",
        )

        assert result.success
        assert result.metadata["match_count"] == 0
        assert "No matches" in result.output

    @pytest.mark.asyncio
    async def test_extract_invalid_pattern(self, tool):
        """Test that invalid pattern returns error."""
        result = await tool.execute(
            text="test",
            pattern=r"[invalid",
        )

        assert not result.success
        assert "Invalid regex" in result.error

    @pytest.mark.asyncio
    async def test_extract_shows_match_list(self, tool):
        """Test that output includes match list for copying."""
        result = await tool.execute(
            text="a@b.com c@d.com",
            pattern=r"[\w]+@[\w.]+",
        )

        assert result.success
        assert "Match list" in result.output

    @pytest.mark.asyncio
    async def test_extract_positions(self, tool):
        """Test that match positions are returned."""
        result = await tool.execute(
            text="hello world",
            pattern=r"world",
        )

        assert result.success
        first_match = result.metadata["extractions"][0]
        assert first_match["start"] == 6
        assert first_match["end"] == 11
