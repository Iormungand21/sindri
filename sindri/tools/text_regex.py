"""Text and regex processing tools (Phase 12).

Provides tools for regex pattern generation, explanation, testing,
text transformation, and pattern extraction.
"""

import re
from enum import Enum
from typing import Optional

import structlog

from sindri.tools.base import Tool, ToolResult

log = structlog.get_logger()


# ═══════════════════════════════════════════════════════════════════════════════
# Enums
# ═══════════════════════════════════════════════════════════════════════════════


class TransformType(str, Enum):
    """Text transformation types."""

    UPPER = "upper"
    LOWER = "lower"
    TITLE = "title"
    CAPITALIZE = "capitalize"
    SWAPCASE = "swapcase"
    STRIP = "strip"
    LSTRIP = "lstrip"
    RSTRIP = "rstrip"
    SNAKE_CASE = "snake_case"
    CAMEL_CASE = "camel_case"
    PASCAL_CASE = "pascal_case"
    KEBAB_CASE = "kebab_case"
    REPLACE = "replace"
    REGEX_REPLACE = "regex_replace"
    REVERSE = "reverse"
    NORMALIZE_WHITESPACE = "normalize_whitespace"
    REMOVE_PUNCTUATION = "remove_punctuation"
    SLUGIFY = "slugify"


class RegexFlavor(str, Enum):
    """Regex flavor hints."""

    PYTHON = "python"
    JAVASCRIPT = "javascript"
    PCRE = "pcre"


# ═══════════════════════════════════════════════════════════════════════════════
# Common regex patterns for generation
# ═══════════════════════════════════════════════════════════════════════════════

COMMON_PATTERNS = {
    "email": r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
    "url": r"https?://[^\s<>\"']+",
    "phone_us": r"\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}",
    "phone_intl": r"\+?[1-9]\d{1,14}",
    "ipv4": r"\b(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\b",
    "ipv6": r"(?:[0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}",
    "date_iso": r"\d{4}-\d{2}-\d{2}",
    "date_us": r"\d{1,2}/\d{1,2}/\d{2,4}",
    "time_24h": r"(?:[01]?\d|2[0-3]):[0-5]\d(?::[0-5]\d)?",
    "time_12h": r"(?:1[0-2]|0?[1-9]):[0-5]\d(?::[0-5]\d)?\s*[AaPp][Mm]",
    "hex_color": r"#(?:[0-9a-fA-F]{3}){1,2}\b",
    "credit_card": r"\b(?:\d{4}[-\s]?){3}\d{4}\b",
    "ssn": r"\b\d{3}-\d{2}-\d{4}\b",
    "zip_us": r"\b\d{5}(?:-\d{4})?\b",
    "uuid": r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}",
    "mac_address": r"(?:[0-9a-fA-F]{2}[:-]){5}[0-9a-fA-F]{2}",
    "username": r"[a-zA-Z][a-zA-Z0-9_]{2,15}",
    "password_strong": r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&])[A-Za-z\d@$!%*?&]{8,}$",
    "html_tag": r"<([a-zA-Z][a-zA-Z0-9]*)\b[^>]*>.*?</\1>|<[a-zA-Z][a-zA-Z0-9]*\b[^>]*/>",
    "slug": r"^[a-z0-9]+(?:-[a-z0-9]+)*$",
    "semver": r"\bv?\d+\.\d+\.\d+(?:-[a-zA-Z0-9.]+)?(?:\+[a-zA-Z0-9.]+)?\b",
    "integer": r"-?\d+",
    "float": r"-?\d+\.?\d*",
    "word": r"\b\w+\b",
    "sentence": r"[A-Z][^.!?]*[.!?]",
    "hashtag": r"#\w+",
    "mention": r"@\w+",
    "filepath_unix": r"(?:/[^/\s]+)+",
    "filepath_windows": r"[a-zA-Z]:\\(?:[^\\/:*?\"<>|\r\n]+\\)*[^\\/:*?\"<>|\r\n]*",
}

# Regex metacharacter explanations
METACHAR_EXPLANATIONS = {
    ".": "Matches any single character (except newline by default)",
    "^": "Matches the start of the string (or line in multiline mode)",
    "$": "Matches the end of the string (or line in multiline mode)",
    "*": "Matches 0 or more of the preceding element (greedy)",
    "+": "Matches 1 or more of the preceding element (greedy)",
    "?": "Matches 0 or 1 of the preceding element (greedy), or makes quantifiers non-greedy",
    "\\d": "Matches any digit [0-9]",
    "\\D": "Matches any non-digit",
    "\\w": "Matches any word character [a-zA-Z0-9_]",
    "\\W": "Matches any non-word character",
    "\\s": "Matches any whitespace character (space, tab, newline)",
    "\\S": "Matches any non-whitespace character",
    "\\b": "Matches a word boundary",
    "\\B": "Matches a non-word boundary",
    "\\n": "Matches a newline",
    "\\t": "Matches a tab",
    "\\r": "Matches a carriage return",
    "[...]": "Character class - matches any single character in the brackets",
    "[^...]": "Negated character class - matches any character NOT in the brackets",
    "(...)": "Capturing group - groups elements and captures the match",
    "(?:...)": "Non-capturing group - groups without capturing",
    "(?P<name>...)": "Named capturing group (Python syntax)",
    "(?=...)": "Positive lookahead - matches if followed by the pattern",
    "(?!...)": "Negative lookahead - matches if NOT followed by the pattern",
    "(?<=...)": "Positive lookbehind - matches if preceded by the pattern",
    "(?<!...)": "Negative lookbehind - matches if NOT preceded by the pattern",
    "{n}": "Matches exactly n occurrences",
    "{n,}": "Matches n or more occurrences",
    "{n,m}": "Matches between n and m occurrences",
    "|": "Alternation - matches either the expression before or after",
    "\\": "Escapes a metacharacter to match it literally",
}


# ═══════════════════════════════════════════════════════════════════════════════
# RegexGenerateTool
# ═══════════════════════════════════════════════════════════════════════════════


class RegexGenerateTool(Tool):
    """Generate regex patterns from natural language descriptions."""

    name = "regex_generate"
    description = """Generate a regex pattern from a natural language description.

Can generate patterns for common use cases like email addresses, URLs, phone numbers,
dates, IP addresses, etc. Also handles custom patterns based on examples.

Examples:
- "Match email addresses" -> [a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}
- "Match US phone numbers" -> \\(?\\d{3}\\)?[-.\\s]?\\d{3}[-.\\s]?\\d{4}
- "Match words starting with 'pre'" -> \\bpre\\w*\\b
"""

    parameters = {
        "type": "object",
        "properties": {
            "description": {
                "type": "string",
                "description": "Natural language description of what to match",
            },
            "examples": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional list of strings that SHOULD match",
            },
            "negative_examples": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional list of strings that should NOT match",
            },
            "flavor": {
                "type": "string",
                "enum": ["python", "javascript", "pcre"],
                "description": "Regex flavor hint (default: python)",
            },
            "anchored": {
                "type": "boolean",
                "description": "Whether to anchor the pattern to match the entire string (default: false)",
            },
            "case_insensitive": {
                "type": "boolean",
                "description": "Whether to suggest case-insensitive matching (default: false)",
            },
        },
        "required": ["description"],
    }

    async def execute(
        self,
        description: str,
        examples: Optional[list[str]] = None,
        negative_examples: Optional[list[str]] = None,
        flavor: str = "python",
        anchored: bool = False,
        case_insensitive: bool = False,
        **kwargs,
    ) -> ToolResult:
        """Generate a regex pattern from description."""
        try:
            log.info(
                "regex_generate_start",
                description=description[:100],
                examples_count=len(examples) if examples else 0,
            )

            description_lower = description.lower()

            # Check for common patterns
            pattern = None
            pattern_name = None

            for name, common_pattern in COMMON_PATTERNS.items():
                keywords = name.replace("_", " ").split()
                if all(kw in description_lower for kw in keywords):
                    pattern = common_pattern
                    pattern_name = name
                    break

            # Additional keyword matching
            if not pattern:
                if "email" in description_lower:
                    pattern = COMMON_PATTERNS["email"]
                    pattern_name = "email"
                elif "url" in description_lower or "http" in description_lower:
                    pattern = COMMON_PATTERNS["url"]
                    pattern_name = "url"
                elif "phone" in description_lower:
                    if "us" in description_lower or "american" in description_lower:
                        pattern = COMMON_PATTERNS["phone_us"]
                        pattern_name = "phone_us"
                    else:
                        pattern = COMMON_PATTERNS["phone_intl"]
                        pattern_name = "phone_intl"
                elif "ip" in description_lower:
                    if "v6" in description_lower or "ipv6" in description_lower:
                        pattern = COMMON_PATTERNS["ipv6"]
                        pattern_name = "ipv6"
                    else:
                        pattern = COMMON_PATTERNS["ipv4"]
                        pattern_name = "ipv4"
                elif "date" in description_lower:
                    if "iso" in description_lower or "yyyy" in description_lower:
                        pattern = COMMON_PATTERNS["date_iso"]
                        pattern_name = "date_iso"
                    else:
                        pattern = COMMON_PATTERNS["date_us"]
                        pattern_name = "date_us"
                elif "time" in description_lower:
                    if "24" in description_lower or "military" in description_lower:
                        pattern = COMMON_PATTERNS["time_24h"]
                        pattern_name = "time_24h"
                    else:
                        pattern = COMMON_PATTERNS["time_12h"]
                        pattern_name = "time_12h"
                elif "color" in description_lower or "hex" in description_lower:
                    pattern = COMMON_PATTERNS["hex_color"]
                    pattern_name = "hex_color"
                elif "uuid" in description_lower or "guid" in description_lower:
                    pattern = COMMON_PATTERNS["uuid"]
                    pattern_name = "uuid"
                elif "mac" in description_lower and "address" in description_lower:
                    pattern = COMMON_PATTERNS["mac_address"]
                    pattern_name = "mac_address"
                elif "credit" in description_lower and "card" in description_lower:
                    pattern = COMMON_PATTERNS["credit_card"]
                    pattern_name = "credit_card"
                elif "ssn" in description_lower or "social security" in description_lower:
                    pattern = COMMON_PATTERNS["ssn"]
                    pattern_name = "ssn"
                elif "zip" in description_lower or "postal" in description_lower:
                    pattern = COMMON_PATTERNS["zip_us"]
                    pattern_name = "zip_us"
                elif "version" in description_lower or "semver" in description_lower:
                    pattern = COMMON_PATTERNS["semver"]
                    pattern_name = "semver"
                elif "hashtag" in description_lower:
                    pattern = COMMON_PATTERNS["hashtag"]
                    pattern_name = "hashtag"
                elif "mention" in description_lower or "@" in description_lower:
                    pattern = COMMON_PATTERNS["mention"]
                    pattern_name = "mention"
                elif "html" in description_lower and "tag" in description_lower:
                    pattern = COMMON_PATTERNS["html_tag"]
                    pattern_name = "html_tag"
                elif "word" in description_lower:
                    pattern = COMMON_PATTERNS["word"]
                    pattern_name = "word"
                elif "integer" in description_lower or "whole number" in description_lower:
                    pattern = COMMON_PATTERNS["integer"]
                    pattern_name = "integer"
                elif (
                    "float" in description_lower
                    or "decimal" in description_lower
                    or "number" in description_lower
                ):
                    pattern = COMMON_PATTERNS["float"]
                    pattern_name = "float"
                elif "slug" in description_lower:
                    pattern = COMMON_PATTERNS["slug"]
                    pattern_name = "slug"

            # If still no pattern, try to build one from examples
            if not pattern and examples:
                pattern = self._generate_from_examples(examples)
                pattern_name = "custom (from examples)"

            # If still no pattern, provide guidance
            if not pattern:
                # Try to parse some common description patterns
                pattern = self._generate_from_description(description)
                if pattern:
                    pattern_name = "custom (from description)"

            if not pattern:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Could not generate pattern for: {description}. "
                    "Try providing examples or a more specific description. "
                    "Supported types: email, url, phone, ip, date, time, uuid, etc.",
                )

            # Apply anchoring if requested
            if anchored:
                pattern = f"^{pattern}$"

            # Validate the pattern
            try:
                compiled = re.compile(pattern)
            except re.error as e:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Generated invalid pattern: {pattern}. Error: {e}",
                )

            # Test against examples
            test_results = []
            if examples:
                for ex in examples:
                    match = compiled.search(ex) if not anchored else compiled.match(ex)
                    test_results.append(
                        f"  {'[PASS]' if match else '[FAIL]'} {ex!r}"
                    )

            if negative_examples:
                for ex in negative_examples:
                    match = compiled.search(ex) if not anchored else compiled.match(ex)
                    test_results.append(
                        f"  {'[FAIL]' if match else '[PASS]'} {ex!r} (should NOT match)"
                    )

            # Build output
            output_lines = [
                f"**Pattern:** `{pattern}`",
                f"**Type:** {pattern_name}",
                "",
            ]

            if case_insensitive:
                output_lines.append("**Note:** Use `re.IGNORECASE` flag for case-insensitive matching")
                output_lines.append("")

            if flavor != "python":
                output_lines.append(f"**Flavor hint:** {flavor}")
                if flavor == "javascript":
                    js_pattern = pattern.replace("(?P<", "(?<")  # Named groups
                    output_lines.append(f"**JavaScript:** `/{js_pattern}/`")
                output_lines.append("")

            if test_results:
                output_lines.append("**Test Results:**")
                output_lines.extend(test_results)
                output_lines.append("")

            output_lines.append("**Usage (Python):**")
            output_lines.append("```python")
            output_lines.append("import re")
            flags = ", re.IGNORECASE" if case_insensitive else ""
            output_lines.append(f"pattern = re.compile(r'{pattern}'{flags})")
            output_lines.append("matches = pattern.findall(text)")
            output_lines.append("```")

            log.info(
                "regex_generate_success",
                pattern=pattern,
                pattern_name=pattern_name,
            )

            return ToolResult(
                success=True,
                output="\n".join(output_lines),
                metadata={
                    "pattern": pattern,
                    "pattern_name": pattern_name,
                    "anchored": anchored,
                    "case_insensitive": case_insensitive,
                },
            )

        except Exception as e:
            log.error("regex_generate_error", error=str(e))
            return ToolResult(
                success=False,
                output="",
                error=f"Failed to generate regex: {e}",
            )

    def _generate_from_examples(self, examples: list[str]) -> Optional[str]:
        """Try to generate a pattern from examples."""
        if not examples:
            return None

        # Find common prefix and suffix
        common_prefix = ""
        common_suffix = ""

        # Check for common structure
        all_same_length = len(set(len(e) for e in examples)) == 1

        if all_same_length:
            length = len(examples[0])
            # Build character class for each position
            pattern_chars = []
            for i in range(length):
                chars_at_pos = set(e[i] for e in examples)
                if len(chars_at_pos) == 1:
                    char = list(chars_at_pos)[0]
                    if char in ".^$*+?{}[]\\|()":
                        pattern_chars.append(f"\\{char}")
                    else:
                        pattern_chars.append(char)
                elif chars_at_pos <= set("0123456789"):
                    pattern_chars.append("\\d")
                elif chars_at_pos <= set("abcdefghijklmnopqrstuvwxyz"):
                    pattern_chars.append("[a-z]")
                elif chars_at_pos <= set("ABCDEFGHIJKLMNOPQRSTUVWXYZ"):
                    pattern_chars.append("[A-Z]")
                elif chars_at_pos <= set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"):
                    pattern_chars.append("[a-zA-Z]")
                else:
                    pattern_chars.append(".")
            return "".join(pattern_chars)

        # Variable length - try to find common structure
        # This is a simplified heuristic
        return None

    def _generate_from_description(self, description: str) -> Optional[str]:
        """Try to generate a pattern from description keywords."""
        desc_lower = description.lower()

        # Check for "starts with" patterns
        if "starts with" in desc_lower or "beginning with" in desc_lower:
            # Extract the literal
            for marker in ["starts with", "beginning with"]:
                if marker in desc_lower:
                    rest = desc_lower.split(marker, 1)[1].strip()
                    # Extract quoted or first word
                    if rest.startswith('"') or rest.startswith("'"):
                        literal = rest[1:].split(rest[0], 1)[0]
                    else:
                        literal = rest.split()[0] if rest else ""
                    if literal:
                        return f"^{re.escape(literal)}.*"

        # Check for "ends with" patterns
        if "ends with" in desc_lower or "ending with" in desc_lower:
            for marker in ["ends with", "ending with"]:
                if marker in desc_lower:
                    rest = desc_lower.split(marker, 1)[1].strip()
                    if rest.startswith('"') or rest.startswith("'"):
                        literal = rest[1:].split(rest[0], 1)[0]
                    else:
                        literal = rest.split()[0] if rest else ""
                    if literal:
                        return f".*{re.escape(literal)}$"

        # Check for "contains" patterns
        if "contains" in desc_lower or "containing" in desc_lower:
            for marker in ["contains", "containing"]:
                if marker in desc_lower:
                    rest = desc_lower.split(marker, 1)[1].strip()
                    if rest.startswith('"') or rest.startswith("'"):
                        literal = rest[1:].split(rest[0], 1)[0]
                    else:
                        literal = rest.split()[0] if rest else ""
                    if literal:
                        return f".*{re.escape(literal)}.*"

        # Check for digit/letter patterns
        if "digits" in desc_lower or "numbers" in desc_lower:
            if "only" in desc_lower:
                return r"^\d+$"
            return r"\d+"

        if "letters" in desc_lower or "alphabetic" in desc_lower:
            if "only" in desc_lower:
                return r"^[a-zA-Z]+$"
            return r"[a-zA-Z]+"

        if "alphanumeric" in desc_lower:
            if "only" in desc_lower:
                return r"^[a-zA-Z0-9]+$"
            return r"[a-zA-Z0-9]+"

        return None


# ═══════════════════════════════════════════════════════════════════════════════
# RegexExplainTool
# ═══════════════════════════════════════════════════════════════════════════════


class RegexExplainTool(Tool):
    """Explain what a regex pattern matches."""

    name = "regex_explain"
    description = """Explain a regex pattern in plain English.

Breaks down each component of the pattern and explains what it matches.
Useful for understanding complex patterns or learning regex syntax.

Example:
- Pattern: ^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}$
- Output: Detailed explanation of email pattern components
"""

    parameters = {
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "description": "The regex pattern to explain",
            },
            "verbose": {
                "type": "boolean",
                "description": "Include detailed breakdown of each component (default: false)",
            },
        },
        "required": ["pattern"],
    }

    async def execute(
        self,
        pattern: str,
        verbose: bool = False,
        **kwargs,
    ) -> ToolResult:
        """Explain a regex pattern."""
        try:
            log.info("regex_explain_start", pattern=pattern[:100])

            # Validate the pattern first
            try:
                re.compile(pattern)
            except re.error as e:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Invalid regex pattern: {e}",
                )

            # Build explanation
            explanation_lines = [
                f"**Pattern:** `{pattern}`",
                "",
                "**Explanation:**",
            ]

            # Check for known patterns
            for name, common_pattern in COMMON_PATTERNS.items():
                if pattern == common_pattern or pattern.strip("^$") == common_pattern:
                    explanation_lines.append(
                        f"This is a standard pattern for matching **{name.replace('_', ' ')}**."
                    )
                    explanation_lines.append("")
                    break

            # Detailed breakdown
            explanation_lines.append("**Breakdown:**")
            breakdown = self._explain_pattern(pattern, verbose)
            explanation_lines.extend(breakdown)

            # Summary
            explanation_lines.append("")
            explanation_lines.append("**In summary:**")
            summary = self._generate_summary(pattern)
            explanation_lines.append(summary)

            log.info("regex_explain_success", pattern=pattern[:50])

            return ToolResult(
                success=True,
                output="\n".join(explanation_lines),
                metadata={"pattern": pattern},
            )

        except Exception as e:
            log.error("regex_explain_error", error=str(e))
            return ToolResult(
                success=False,
                output="",
                error=f"Failed to explain regex: {e}",
            )

    def _explain_pattern(self, pattern: str, verbose: bool) -> list[str]:
        """Generate a breakdown of the pattern."""
        lines = []
        i = 0
        part_num = 1

        while i < len(pattern):
            explained = False

            # Check for multi-character metacharacters first
            for meta, explanation in sorted(
                METACHAR_EXPLANATIONS.items(), key=lambda x: -len(x[0])
            ):
                if pattern[i:].startswith(meta):
                    lines.append(f"  {part_num}. `{meta}` - {explanation}")
                    i += len(meta)
                    part_num += 1
                    explained = True
                    break

            if explained:
                continue

            # Character classes [...]
            if pattern[i] == "[":
                end = pattern.find("]", i)
                if end != -1:
                    char_class = pattern[i : end + 1]
                    if char_class.startswith("[^"):
                        lines.append(
                            f"  {part_num}. `{char_class}` - Negated character class: "
                            f"matches any character NOT in {char_class[2:-1]!r}"
                        )
                    else:
                        lines.append(
                            f"  {part_num}. `{char_class}` - Character class: "
                            f"matches any single character from {char_class[1:-1]!r}"
                        )
                    i = end + 1
                    part_num += 1
                    continue

            # Quantifiers {n,m}
            if pattern[i] == "{":
                end = pattern.find("}", i)
                if end != -1:
                    quant = pattern[i : end + 1]
                    nums = quant[1:-1].split(",")
                    if len(nums) == 1:
                        lines.append(
                            f"  {part_num}. `{quant}` - Matches exactly {nums[0]} occurrences"
                        )
                    elif len(nums) == 2:
                        if nums[1]:
                            lines.append(
                                f"  {part_num}. `{quant}` - Matches between {nums[0]} and {nums[1]} occurrences"
                            )
                        else:
                            lines.append(
                                f"  {part_num}. `{quant}` - Matches {nums[0]} or more occurrences"
                            )
                    i = end + 1
                    part_num += 1
                    continue

            # Groups (...)
            if pattern[i] == "(":
                # Find matching close paren
                depth = 1
                j = i + 1
                while j < len(pattern) and depth > 0:
                    if pattern[j] == "\\":
                        j += 2
                        continue
                    if pattern[j] == "(":
                        depth += 1
                    elif pattern[j] == ")":
                        depth -= 1
                    j += 1

                group = pattern[i:j]
                if group.startswith("(?:"):
                    lines.append(
                        f"  {part_num}. `{group}` - Non-capturing group: groups the pattern without capturing"
                    )
                elif group.startswith("(?P<"):
                    name_end = group.find(">")
                    group_name = group[4:name_end]
                    lines.append(
                        f"  {part_num}. `{group}` - Named capturing group '{group_name}'"
                    )
                elif group.startswith("(?="):
                    lines.append(
                        f"  {part_num}. `{group}` - Positive lookahead: asserts what follows matches the pattern"
                    )
                elif group.startswith("(?!"):
                    lines.append(
                        f"  {part_num}. `{group}` - Negative lookahead: asserts what follows does NOT match"
                    )
                elif group.startswith("(?<="):
                    lines.append(
                        f"  {part_num}. `{group}` - Positive lookbehind: asserts what precedes matches the pattern"
                    )
                elif group.startswith("(?<!"):
                    lines.append(
                        f"  {part_num}. `{group}` - Negative lookbehind: asserts what precedes does NOT match"
                    )
                else:
                    lines.append(
                        f"  {part_num}. `{group}` - Capturing group: captures the matched text"
                    )
                i = j
                part_num += 1
                continue

            # Escaped character
            if pattern[i] == "\\" and i + 1 < len(pattern):
                escaped = pattern[i : i + 2]
                if escaped in METACHAR_EXPLANATIONS:
                    lines.append(
                        f"  {part_num}. `{escaped}` - {METACHAR_EXPLANATIONS[escaped]}"
                    )
                else:
                    lines.append(
                        f"  {part_num}. `{escaped}` - Literal character '{pattern[i+1]}'"
                    )
                i += 2
                part_num += 1
                continue

            # Single metacharacters
            char = pattern[i]
            if char in METACHAR_EXPLANATIONS:
                lines.append(f"  {part_num}. `{char}` - {METACHAR_EXPLANATIONS[char]}")
            elif char.isalnum():
                # Collect consecutive literals
                j = i
                while j < len(pattern) and pattern[j].isalnum():
                    j += 1
                literal = pattern[i:j]
                lines.append(f"  {part_num}. `{literal}` - Literal text '{literal}'")
                i = j
                part_num += 1
                continue
            else:
                lines.append(f"  {part_num}. `{char}` - Literal character '{char}'")

            i += 1
            part_num += 1

        return lines

    def _generate_summary(self, pattern: str) -> str:
        """Generate a plain English summary."""
        summary_parts = []

        if pattern.startswith("^"):
            summary_parts.append("starting at the beginning of the string")
        if pattern.endswith("$"):
            summary_parts.append("ending at the end of the string")

        # Check for common patterns
        for name, common_pattern in COMMON_PATTERNS.items():
            if common_pattern in pattern:
                summary_parts.append(f"containing a {name.replace('_', ' ')} pattern")
                break

        if not summary_parts:
            summary_parts.append("matching the specified pattern")

        return "This pattern matches text " + ", ".join(summary_parts) + "."


# ═══════════════════════════════════════════════════════════════════════════════
# RegexTestTool
# ═══════════════════════════════════════════════════════════════════════════════


class RegexTestTool(Tool):
    """Test a regex pattern against sample text."""

    name = "regex_test"
    description = """Test a regex pattern against sample text and show matches.

Returns all matches with their positions and any captured groups.
Supports common regex flags: ignorecase, multiline, dotall.

Example:
- Pattern: (\\w+)@(\\w+\\.\\w+)
- Text: "Contact us at info@example.com or support@test.org"
- Output: Shows both email matches with captured groups
"""

    parameters = {
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "description": "The regex pattern to test",
            },
            "text": {
                "type": "string",
                "description": "The text to test against",
            },
            "flags": {
                "type": "array",
                "items": {
                    "type": "string",
                    "enum": ["ignorecase", "multiline", "dotall", "verbose", "ascii"],
                },
                "description": "Regex flags to apply",
            },
            "find_all": {
                "type": "boolean",
                "description": "Find all matches (default: true) or just the first",
            },
        },
        "required": ["pattern", "text"],
    }

    async def execute(
        self,
        pattern: str,
        text: str,
        flags: Optional[list[str]] = None,
        find_all: bool = True,
        **kwargs,
    ) -> ToolResult:
        """Test a regex pattern against text."""
        try:
            log.info(
                "regex_test_start",
                pattern=pattern[:50],
                text_length=len(text),
            )

            # Build flags
            re_flags = 0
            flag_names = []
            if flags:
                flag_map = {
                    "ignorecase": re.IGNORECASE,
                    "multiline": re.MULTILINE,
                    "dotall": re.DOTALL,
                    "verbose": re.VERBOSE,
                    "ascii": re.ASCII,
                }
                for flag in flags:
                    if flag.lower() in flag_map:
                        re_flags |= flag_map[flag.lower()]
                        flag_names.append(flag.upper())

            # Compile pattern
            try:
                compiled = re.compile(pattern, re_flags)
            except re.error as e:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Invalid regex pattern: {e}",
                )

            # Find matches
            output_lines = [
                f"**Pattern:** `{pattern}`",
                f"**Flags:** {', '.join(flag_names) if flag_names else 'None'}",
                f"**Text length:** {len(text)} characters",
                "",
            ]

            if find_all:
                matches = list(compiled.finditer(text))
            else:
                match = compiled.search(text)
                matches = [match] if match else []

            if not matches:
                output_lines.append("**Result:** No matches found")
                return ToolResult(
                    success=True,
                    output="\n".join(output_lines),
                    metadata={
                        "pattern": pattern,
                        "match_count": 0,
                        "flags": flag_names,
                    },
                )

            output_lines.append(f"**Matches found:** {len(matches)}")
            output_lines.append("")

            match_data = []
            for i, match in enumerate(matches, 1):
                output_lines.append(f"**Match {i}:**")
                output_lines.append(f"  - Full match: `{match.group()}`")
                output_lines.append(f"  - Position: {match.start()}-{match.end()}")

                match_info = {
                    "match": match.group(),
                    "start": match.start(),
                    "end": match.end(),
                    "groups": [],
                }

                # Show captured groups
                if match.groups():
                    output_lines.append(f"  - Groups: {len(match.groups())}")
                    for j, group in enumerate(match.groups(), 1):
                        output_lines.append(f"    - Group {j}: `{group}`")
                        match_info["groups"].append(group)

                # Show named groups
                if match.groupdict():
                    output_lines.append("  - Named groups:")
                    match_info["named_groups"] = {}
                    for name, value in match.groupdict().items():
                        output_lines.append(f"    - {name}: `{value}`")
                        match_info["named_groups"][name] = value

                output_lines.append("")
                match_data.append(match_info)

            # Show context for first match
            if matches:
                first = matches[0]
                context_start = max(0, first.start() - 20)
                context_end = min(len(text), first.end() + 20)
                context = text[context_start:context_end]
                output_lines.append("**Context (first match):**")
                output_lines.append(f"```")
                output_lines.append(f"...{context}...")
                output_lines.append(f"```")

            log.info(
                "regex_test_success",
                pattern=pattern[:50],
                match_count=len(matches),
            )

            return ToolResult(
                success=True,
                output="\n".join(output_lines),
                metadata={
                    "pattern": pattern,
                    "match_count": len(matches),
                    "matches": match_data,
                    "flags": flag_names,
                },
            )

        except Exception as e:
            log.error("regex_test_error", error=str(e))
            return ToolResult(
                success=False,
                output="",
                error=f"Failed to test regex: {e}",
            )


# ═══════════════════════════════════════════════════════════════════════════════
# TextTransformTool
# ═══════════════════════════════════════════════════════════════════════════════


class TextTransformTool(Tool):
    """Apply text transformations."""

    name = "text_transform"
    description = """Apply various text transformations.

Supports case changes, whitespace handling, naming conventions, and regex-based replacements.

Transform types:
- Case: upper, lower, title, capitalize, swapcase
- Whitespace: strip, lstrip, rstrip, normalize_whitespace
- Naming: snake_case, camel_case, pascal_case, kebab_case
- Other: replace, regex_replace, reverse, remove_punctuation, slugify
"""

    parameters = {
        "type": "object",
        "properties": {
            "text": {
                "type": "string",
                "description": "The text to transform",
            },
            "transform": {
                "type": "string",
                "enum": [t.value for t in TransformType],
                "description": "The transformation to apply",
            },
            "pattern": {
                "type": "string",
                "description": "For replace/regex_replace: the pattern to find",
            },
            "replacement": {
                "type": "string",
                "description": "For replace/regex_replace: the replacement text",
            },
        },
        "required": ["text", "transform"],
    }

    async def execute(
        self,
        text: str,
        transform: str,
        pattern: Optional[str] = None,
        replacement: Optional[str] = None,
        **kwargs,
    ) -> ToolResult:
        """Apply a text transformation."""
        try:
            log.info(
                "text_transform_start",
                transform=transform,
                text_length=len(text),
            )

            result = text

            if transform == TransformType.UPPER.value:
                result = text.upper()
            elif transform == TransformType.LOWER.value:
                result = text.lower()
            elif transform == TransformType.TITLE.value:
                result = text.title()
            elif transform == TransformType.CAPITALIZE.value:
                result = text.capitalize()
            elif transform == TransformType.SWAPCASE.value:
                result = text.swapcase()
            elif transform == TransformType.STRIP.value:
                result = text.strip()
            elif transform == TransformType.LSTRIP.value:
                result = text.lstrip()
            elif transform == TransformType.RSTRIP.value:
                result = text.rstrip()
            elif transform == TransformType.REVERSE.value:
                result = text[::-1]
            elif transform == TransformType.NORMALIZE_WHITESPACE.value:
                result = " ".join(text.split())
            elif transform == TransformType.REMOVE_PUNCTUATION.value:
                result = re.sub(r"[^\w\s]", "", text)
            elif transform == TransformType.SNAKE_CASE.value:
                result = self._to_snake_case(text)
            elif transform == TransformType.CAMEL_CASE.value:
                result = self._to_camel_case(text)
            elif transform == TransformType.PASCAL_CASE.value:
                result = self._to_pascal_case(text)
            elif transform == TransformType.KEBAB_CASE.value:
                result = self._to_kebab_case(text)
            elif transform == TransformType.SLUGIFY.value:
                result = self._slugify(text)
            elif transform == TransformType.REPLACE.value:
                if pattern is None:
                    return ToolResult(
                        success=False,
                        output="",
                        error="'pattern' is required for replace transform",
                    )
                result = text.replace(pattern, replacement or "")
            elif transform == TransformType.REGEX_REPLACE.value:
                if pattern is None:
                    return ToolResult(
                        success=False,
                        output="",
                        error="'pattern' is required for regex_replace transform",
                    )
                try:
                    result = re.sub(pattern, replacement or "", text)
                except re.error as e:
                    return ToolResult(
                        success=False,
                        output="",
                        error=f"Invalid regex pattern: {e}",
                    )
            else:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Unknown transform type: {transform}",
                )

            output_lines = [
                f"**Transform:** {transform}",
                f"**Input length:** {len(text)}",
                f"**Output length:** {len(result)}",
                "",
                "**Result:**",
                "```",
                result,
                "```",
            ]

            log.info(
                "text_transform_success",
                transform=transform,
                input_length=len(text),
                output_length=len(result),
            )

            return ToolResult(
                success=True,
                output="\n".join(output_lines),
                metadata={
                    "transform": transform,
                    "input_length": len(text),
                    "output_length": len(result),
                    "result": result,
                },
            )

        except Exception as e:
            log.error("text_transform_error", error=str(e))
            return ToolResult(
                success=False,
                output="",
                error=f"Failed to transform text: {e}",
            )

    def _to_snake_case(self, text: str) -> str:
        """Convert text to snake_case."""
        # Handle camelCase and PascalCase
        s1 = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", text)
        s2 = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s1)
        # Replace spaces and hyphens with underscores
        s3 = re.sub(r"[\s\-]+", "_", s2)
        # Remove non-alphanumeric except underscore
        s4 = re.sub(r"[^\w]+", "", s3)
        # Collapse multiple underscores
        s5 = re.sub(r"_+", "_", s4)
        return s5.lower()

    def _to_camel_case(self, text: str) -> str:
        """Convert text to camelCase."""
        # Split on non-alphanumeric
        words = re.split(r"[^a-zA-Z0-9]+", text)
        words = [w for w in words if w]
        if not words:
            return ""
        # First word lowercase, rest title case
        result = words[0].lower()
        for word in words[1:]:
            result += word.capitalize()
        return result

    def _to_pascal_case(self, text: str) -> str:
        """Convert text to PascalCase."""
        words = re.split(r"[^a-zA-Z0-9]+", text)
        words = [w for w in words if w]
        return "".join(word.capitalize() for word in words)

    def _to_kebab_case(self, text: str) -> str:
        """Convert text to kebab-case."""
        snake = self._to_snake_case(text)
        return snake.replace("_", "-")

    def _slugify(self, text: str) -> str:
        """Convert text to URL-friendly slug."""
        # Lowercase
        slug = text.lower()
        # Replace spaces and underscores with hyphens
        slug = re.sub(r"[\s_]+", "-", slug)
        # Remove non-alphanumeric except hyphens
        slug = re.sub(r"[^a-z0-9\-]", "", slug)
        # Remove consecutive hyphens
        slug = re.sub(r"-+", "-", slug)
        # Strip hyphens from ends
        slug = slug.strip("-")
        return slug


# ═══════════════════════════════════════════════════════════════════════════════
# TextExtractTool
# ═══════════════════════════════════════════════════════════════════════════════


class TextExtractTool(Tool):
    """Extract patterns from text."""

    name = "text_extract"
    description = """Extract all matches of a pattern from text.

Returns all matches including captured groups. Useful for extracting
structured data like emails, URLs, dates, etc. from text.

Example:
- Pattern: (\\d{4})-(\\d{2})-(\\d{2})
- Text: "Events: 2024-01-15, 2024-02-20, 2024-03-25"
- Output: List of dates with year, month, day groups
"""

    parameters = {
        "type": "object",
        "properties": {
            "text": {
                "type": "string",
                "description": "The text to extract from",
            },
            "pattern": {
                "type": "string",
                "description": "The regex pattern (can include capturing groups)",
            },
            "flags": {
                "type": "array",
                "items": {
                    "type": "string",
                    "enum": ["ignorecase", "multiline", "dotall"],
                },
                "description": "Regex flags to apply",
            },
            "unique": {
                "type": "boolean",
                "description": "Return only unique matches (default: false)",
            },
            "max_matches": {
                "type": "integer",
                "description": "Maximum number of matches to return (default: unlimited)",
            },
        },
        "required": ["text", "pattern"],
    }

    async def execute(
        self,
        text: str,
        pattern: str,
        flags: Optional[list[str]] = None,
        unique: bool = False,
        max_matches: Optional[int] = None,
        **kwargs,
    ) -> ToolResult:
        """Extract patterns from text."""
        try:
            log.info(
                "text_extract_start",
                pattern=pattern[:50],
                text_length=len(text),
            )

            # Build flags
            re_flags = 0
            flag_names = []
            if flags:
                flag_map = {
                    "ignorecase": re.IGNORECASE,
                    "multiline": re.MULTILINE,
                    "dotall": re.DOTALL,
                }
                for flag in flags:
                    if flag.lower() in flag_map:
                        re_flags |= flag_map[flag.lower()]
                        flag_names.append(flag.upper())

            # Compile pattern
            try:
                compiled = re.compile(pattern, re_flags)
            except re.error as e:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Invalid regex pattern: {e}",
                )

            # Find all matches
            matches = list(compiled.finditer(text))

            if not matches:
                return ToolResult(
                    success=True,
                    output="**No matches found**",
                    metadata={
                        "pattern": pattern,
                        "match_count": 0,
                        "extractions": [],
                    },
                )

            # Process matches
            extractions = []
            seen = set()

            for match in matches:
                full_match = match.group()

                # Check uniqueness
                if unique and full_match in seen:
                    continue
                seen.add(full_match)

                extraction = {
                    "match": full_match,
                    "start": match.start(),
                    "end": match.end(),
                }

                # Capture groups
                if match.groups():
                    extraction["groups"] = list(match.groups())

                # Named groups
                if match.groupdict():
                    named = {k: v for k, v in match.groupdict().items() if v is not None}
                    if named:
                        extraction["named_groups"] = named

                extractions.append(extraction)

                # Check max matches
                if max_matches and len(extractions) >= max_matches:
                    break

            # Build output
            output_lines = [
                f"**Pattern:** `{pattern}`",
                f"**Flags:** {', '.join(flag_names) if flag_names else 'None'}",
                f"**Unique:** {unique}",
                f"**Matches found:** {len(extractions)}",
                "",
            ]

            # Show extractions
            output_lines.append("**Extractions:**")
            for i, ext in enumerate(extractions, 1):
                output_lines.append(f"{i}. `{ext['match']}`")
                if "groups" in ext:
                    output_lines.append(f"   Groups: {ext['groups']}")
                if "named_groups" in ext:
                    output_lines.append(f"   Named: {ext['named_groups']}")

            # List just the matches for easy copying
            output_lines.append("")
            output_lines.append("**Match list:**")
            output_lines.append("```")
            for ext in extractions:
                output_lines.append(ext["match"])
            output_lines.append("```")

            log.info(
                "text_extract_success",
                pattern=pattern[:50],
                match_count=len(extractions),
            )

            return ToolResult(
                success=True,
                output="\n".join(output_lines),
                metadata={
                    "pattern": pattern,
                    "match_count": len(extractions),
                    "extractions": extractions,
                    "flags": flag_names,
                },
            )

        except Exception as e:
            log.error("text_extract_error", error=str(e))
            return ToolResult(
                success=False,
                output="",
                error=f"Failed to extract patterns: {e}",
            )
