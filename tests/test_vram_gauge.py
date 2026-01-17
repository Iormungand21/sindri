"""Tests for VRAM gauge in TUI header."""

from sindri.tui.widgets.header import SindriHeader


def test_header_init():
    """Test header initializes with default values."""
    header = SindriHeader()
    assert header.vram_used == 0.0
    assert header.vram_total == 16.0
    assert header.loaded_models == []


def test_header_update_vram():
    """Test updating VRAM stats."""
    header = SindriHeader()

    # Update with some usage
    header.update_vram(used=8.5, total=16.0, loaded_models=["qwen2.5-coder:14b"])

    assert header.vram_used == 8.5
    assert header.vram_total == 16.0
    assert header.loaded_models == ["qwen2.5-coder:14b"]


def test_header_render_contains_vram(monkeypatch):
    """Test that rendered header contains VRAM info."""
    header = SindriHeader()

    # Mock the title/subtitle getter
    monkeypatch.setattr(
        header, "_get_title_subtitle", lambda: ("Test Title", "Test Subtitle")
    )

    # Update with some usage
    header.update_vram(used=8.0, total=16.0, loaded_models=["model1", "model2"])

    # Render and check content
    rendered = header.render()
    text = rendered.plain

    assert "Test Title" in text
    assert "Test Subtitle" in text
    assert "VRAM" in text
    assert "8.0/16.0GB" in text
    assert "2 models" in text


def test_header_render_empty_vram(monkeypatch):
    """Test that header shows empty VRAM gauge."""
    header = SindriHeader()

    # Mock the title/subtitle getter
    monkeypatch.setattr(header, "_get_title_subtitle", lambda: ("Sindri", None))

    # No models loaded
    header.update_vram(used=0.0, total=16.0, loaded_models=[])

    rendered = header.render()
    text = rendered.plain

    assert "VRAM" in text
    assert "0.0/16.0GB" in text
    # Should show all empty blocks
    assert "░" in text


def test_header_vram_bar_calculation(monkeypatch):
    """Test VRAM bar fill calculation."""
    header = SindriHeader()

    # Mock the title/subtitle getter
    monkeypatch.setattr(header, "_get_title_subtitle", lambda: ("Sindri", None))

    # 50% usage (8GB of 16GB)
    header.update_vram(used=8.0, total=16.0, loaded_models=["model1"])
    rendered = header.render()
    text = rendered.plain

    # Should have both filled and empty blocks
    assert "█" in text or "░" in text
    assert "8.0/16.0GB" in text


def test_header_multiple_models(monkeypatch):
    """Test header with multiple models loaded."""
    header = SindriHeader()

    # Mock the title/subtitle getter
    monkeypatch.setattr(header, "_get_title_subtitle", lambda: ("Sindri", None))

    # Multiple models
    models = ["qwen2.5-coder:14b", "llama3.1:8b", "qwen2.5:3b"]
    header.update_vram(used=12.5, total=16.0, loaded_models=models)

    rendered = header.render()
    text = rendered.plain

    assert "3 models" in text
    assert "12.5/16.0GB" in text
