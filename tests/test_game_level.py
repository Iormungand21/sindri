"""Tests for game level design tools."""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from sindri.tools.game_level import (
    GenerateTilemapTool,
    GenerateDungeonTool,
    BalanceDifficultyTool,
    GenerateDialogueTool,
    GenerateItemStatsTool,
    GenerateGDScriptTool,
    GenerateUnityScriptTool,
    Room,
    BSPNode,
    TILE_TYPES,
    RARITY_MULTIPLIERS,
    AFFIXES,
    BASE_WEAPON_STATS,
    BASE_ARMOR_STATS,
    _create_grid,
    _flood_fill,
    _ensure_connectivity,
    _bsp_split,
    _carve_corridor,
    _cellular_automata,
    _grid_to_ascii,
    _grid_to_tmx,
)


# ============================================================================
# Helper Function Tests
# ============================================================================


class TestCreateGrid:
    """Test grid creation helper."""

    def test_create_empty_grid(self):
        """Test creating an empty grid."""
        grid = _create_grid(10, 8, 0)
        assert len(grid) == 8
        assert len(grid[0]) == 10
        assert all(cell == 0 for row in grid for cell in row)

    def test_create_filled_grid(self):
        """Test creating a filled grid."""
        grid = _create_grid(5, 5, 1)
        assert all(cell == 1 for row in grid for cell in row)

    def test_create_asymmetric_grid(self):
        """Test creating non-square grid."""
        grid = _create_grid(20, 10, 0)
        assert len(grid) == 10  # Height
        assert len(grid[0]) == 20  # Width


class TestFloodFill:
    """Test flood fill algorithm."""

    def test_flood_fill_simple(self):
        """Test flood fill on simple grid."""
        grid = [
            [1, 1, 0],
            [1, 1, 0],
            [0, 0, 0],
        ]
        region = _flood_fill(grid, 0, 0, 1)
        assert len(region) == 4
        assert (0, 0) in region
        assert (1, 0) in region
        assert (0, 1) in region
        assert (1, 1) in region

    def test_flood_fill_isolated(self):
        """Test flood fill doesn't cross walls."""
        grid = [
            [1, 0, 1],
            [0, 0, 0],
            [1, 0, 1],
        ]
        region = _flood_fill(grid, 0, 0, 1)
        assert len(region) == 1  # Only the single cell

    def test_flood_fill_empty(self):
        """Test flood fill on target not in grid."""
        grid = [[0, 0], [0, 0]]
        region = _flood_fill(grid, 0, 0, 1)
        assert len(region) == 0


class TestEnsureConnectivity:
    """Test connectivity validation."""

    def test_already_connected(self):
        """Test grid that's already connected stays unchanged."""
        grid = [
            [0, 0, 0],
            [0, 1, 1],
            [0, 1, 0],
        ]
        result = _ensure_connectivity(grid, 1)
        # Should have same floor tiles
        floor_count = sum(1 for row in result for cell in row if cell == 1)
        assert floor_count == 3

    def test_removes_isolated(self):
        """Test isolated regions are removed."""
        grid = [
            [1, 0, 1],
            [0, 0, 0],
            [1, 0, 1],
        ]
        result = _ensure_connectivity(grid, 1)
        # Should only keep the largest region (1 cell each, keeps first found)
        floor_count = sum(1 for row in result for cell in row if cell == 1)
        assert floor_count == 1


class TestBSPSplit:
    """Test BSP algorithm."""

    def test_bsp_creates_children(self):
        """Test BSP creates child nodes."""
        import random
        node = BSPNode(0, 0, 64, 64)
        rng = random.Random(12345)
        _bsp_split(node, 10, rng, depth=0, max_depth=3)
        # Should have children after split
        assert node.left is not None or node.right is not None

    def test_bsp_respects_min_size(self):
        """Test BSP doesn't split below minimum size."""
        import random
        node = BSPNode(0, 0, 15, 15)
        rng = random.Random(12345)
        _bsp_split(node, 10, rng, depth=0, max_depth=10)
        # Node too small to split meaningfully
        # Either no children or children are near min_size


class TestCarveCorridors:
    """Test corridor carving."""

    def test_carve_horizontal(self):
        """Test carving horizontal corridor."""
        grid = _create_grid(10, 5, 0)
        _carve_corridor(grid, 0, 2, 9, 2, 1, 1)
        # Check horizontal line at y=2
        for x in range(10):
            assert grid[2][x] == 1

    def test_carve_l_shaped(self):
        """Test carving L-shaped corridor."""
        grid = _create_grid(10, 10, 0)
        _carve_corridor(grid, 2, 2, 8, 7, 1, 1)
        # Should have carved an L-shape
        floor_count = sum(1 for row in grid for cell in row if cell == 1)
        assert floor_count > 0


class TestCellularAutomata:
    """Test cellular automata cave generation."""

    def test_cellular_produces_caves(self):
        """Test cellular automata produces cave-like structure."""
        import random
        rng = random.Random(12345)
        grid = _cellular_automata(32, 24, 0.45, 5, rng)
        # Should have mix of walls and floors
        floor_count = sum(1 for row in grid for cell in row if cell == 1)
        wall_count = sum(1 for row in grid for cell in row if cell == 0)
        assert floor_count > 0
        assert wall_count > 0

    def test_cellular_seed_reproducible(self):
        """Test same seed produces same result."""
        import random
        rng1 = random.Random(42)
        rng2 = random.Random(42)
        grid1 = _cellular_automata(20, 15, 0.45, 5, rng1)
        grid2 = _cellular_automata(20, 15, 0.45, 5, rng2)
        assert grid1 == grid2


class TestGridToAscii:
    """Test ASCII grid conversion."""

    def test_basic_ascii(self):
        """Test basic ASCII conversion."""
        grid = [
            [0, 1, 1],
            [0, 1, 0],
        ]
        ascii_str = _grid_to_ascii(grid)
        lines = ascii_str.split("\n")
        assert lines[0] == "#.."
        assert lines[1] == "#.#"


class TestGridToTmx:
    """Test TMX format conversion."""

    def test_tmx_structure(self):
        """Test TMX has proper XML structure."""
        grid = [[0, 1], [1, 0]]
        tmx = _grid_to_tmx(grid, 2, 2)
        assert '<map' in tmx
        assert 'width="2"' in tmx
        assert 'height="2"' in tmx
        assert '<layer' in tmx
        assert '<data' in tmx


class TestRoom:
    """Test Room dataclass."""

    def test_room_center(self):
        """Test room center calculation."""
        room = Room(10, 20, 8, 6)
        assert room.center == (14, 23)

    def test_room_to_dict(self):
        """Test room serialization."""
        room = Room(5, 5, 10, 10, room_type="boss")
        d = room.to_dict()
        assert d["x"] == 5
        assert d["y"] == 5
        assert d["width"] == 10
        assert d["height"] == 10
        assert d["type"] == "boss"


# ============================================================================
# GenerateTilemapTool Tests
# ============================================================================


class TestGenerateTilemapTool:
    """Test tilemap generation tool."""

    @pytest.fixture
    def tool(self):
        """Create tool instance."""
        return GenerateTilemapTool()

    @pytest.mark.asyncio
    async def test_generate_basic_tilemap(self, tool):
        """Test basic tilemap generation."""
        result = await tool.execute(width=16, height=12, seed=12345)
        assert result.success
        assert result.metadata["width"] == 16
        assert result.metadata["height"] == 12
        assert result.metadata["seed"] == 12345

    @pytest.mark.asyncio
    async def test_generate_json_format(self, tool):
        """Test JSON output format."""
        result = await tool.execute(width=10, height=10, format="json", seed=42)
        assert result.success
        data = json.loads(result.output)
        assert "width" in data
        assert "height" in data
        assert "layers" in data
        assert "tile_legend" in data

    @pytest.mark.asyncio
    async def test_generate_tmx_format(self, tool):
        """Test TMX output format."""
        result = await tool.execute(width=10, height=10, format="tmx", seed=42)
        assert result.success
        assert '<map' in result.output
        assert 'version=' in result.output

    @pytest.mark.asyncio
    async def test_generate_csv_format(self, tool):
        """Test CSV output format."""
        result = await tool.execute(width=5, height=5, format="csv", seed=42)
        assert result.success
        lines = result.output.strip().split("\n")
        assert len(lines) == 5

    @pytest.mark.asyncio
    async def test_generate_ascii_format(self, tool):
        """Test ASCII output format."""
        result = await tool.execute(width=10, height=8, format="ascii", seed=42)
        assert result.success
        lines = result.output.strip().split("\n")
        assert len(lines) == 8

    @pytest.mark.asyncio
    async def test_seed_reproducibility(self, tool):
        """Test same seed produces same result."""
        result1 = await tool.execute(width=20, height=15, seed=99999)
        result2 = await tool.execute(width=20, height=15, seed=99999)
        assert result1.output == result2.output

    @pytest.mark.asyncio
    async def test_save_to_file(self, tool):
        """Test saving tilemap to file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "test_map.json")
            result = await tool.execute(
                width=10, height=10, seed=42, output_file=output_path
            )
            assert result.success
            assert os.path.exists(output_path)
            with open(output_path) as f:
                data = json.load(f)
            assert data["width"] == 10

    @pytest.mark.asyncio
    async def test_border_walls(self, tool):
        """Test border walls option."""
        result = await tool.execute(width=10, height=10, border_walls=True, seed=42, format="json")
        assert result.success
        data = json.loads(result.output)
        grid = data["layers"][0]["data"]
        # Check top row is all walls
        assert all(cell == 0 for cell in grid[0])


# ============================================================================
# GenerateDungeonTool Tests
# ============================================================================


class TestGenerateDungeonTool:
    """Test dungeon generation tool."""

    @pytest.fixture
    def tool(self):
        """Create tool instance."""
        return GenerateDungeonTool()

    @pytest.mark.asyncio
    async def test_generate_bsp_dungeon(self, tool):
        """Test BSP dungeon generation."""
        result = await tool.execute(algorithm="bsp", width=48, height=36, seed=12345)
        assert result.success
        assert result.metadata["algorithm"] == "bsp"
        assert result.metadata["room_count"] > 0

    @pytest.mark.asyncio
    async def test_generate_cellular_dungeon(self, tool):
        """Test cellular automata dungeon generation."""
        result = await tool.execute(algorithm="cellular", width=48, height=36, seed=12345)
        assert result.success
        assert result.metadata["algorithm"] == "cellular"

    @pytest.mark.asyncio
    async def test_generate_rooms_dungeon(self, tool):
        """Test room placement dungeon generation."""
        result = await tool.execute(algorithm="rooms", width=48, height=36, room_count=6, seed=12345)
        assert result.success
        assert result.metadata["algorithm"] == "rooms"

    @pytest.mark.asyncio
    async def test_dungeon_json_format(self, tool):
        """Test JSON output contains expected fields."""
        result = await tool.execute(width=32, height=24, seed=42, format="json")
        assert result.success
        data = json.loads(result.output)
        assert "grid" in data
        assert "rooms" in data
        assert "features" in data
        assert "tile_legend" in data

    @pytest.mark.asyncio
    async def test_dungeon_features(self, tool):
        """Test feature placement."""
        result = await tool.execute(
            width=48, height=36, seed=42,
            features=["stairs_up", "stairs_down", "chests", "traps", "spawn", "boss"],
            format="json"
        )
        assert result.success
        data = json.loads(result.output)
        # Features dict should exist
        assert "features" in data

    @pytest.mark.asyncio
    async def test_dungeon_ascii_format(self, tool):
        """Test ASCII dungeon output."""
        result = await tool.execute(width=32, height=24, seed=42, format="ascii")
        assert result.success
        # Should have wall (#) and floor (.) characters
        assert "#" in result.output
        assert "." in result.output

    @pytest.mark.asyncio
    async def test_dungeon_seed_reproducibility(self, tool):
        """Test same seed produces same dungeon."""
        result1 = await tool.execute(algorithm="bsp", width=32, height=24, seed=77777)
        result2 = await tool.execute(algorithm="bsp", width=32, height=24, seed=77777)
        assert result1.output == result2.output

    @pytest.mark.asyncio
    async def test_room_parameters(self, tool):
        """Test room size parameters."""
        result = await tool.execute(
            algorithm="rooms",
            width=64, height=48,
            room_min_size=8,
            room_max_size=15,
            room_count=5,
            seed=42,
            format="json"
        )
        assert result.success
        data = json.loads(result.output)
        # Rooms should exist
        assert len(data["rooms"]) > 0


# ============================================================================
# BalanceDifficultyTool Tests
# ============================================================================


class TestBalanceDifficultyTool:
    """Test difficulty balancing tool."""

    @pytest.fixture
    def tool(self):
        """Create tool instance."""
        return BalanceDifficultyTool()

    @pytest.fixture
    def sample_enemies(self):
        """Sample enemy data."""
        return [
            {"name": "Goblin", "hp": 30, "damage": 5, "attack_speed": 1.0, "count": 3},
            {"name": "Orc", "hp": 80, "damage": 15, "attack_speed": 0.7, "count": 1},
        ]

    @pytest.fixture
    def sample_player(self):
        """Sample player stats."""
        return {"hp": 100, "damage": 20, "attack_speed": 1.0, "armor": 5}

    @pytest.mark.asyncio
    async def test_analyze_difficulty(self, tool, sample_enemies, sample_player):
        """Test difficulty analysis."""
        result = await tool.execute(
            enemies=sample_enemies,
            player_stats=sample_player,
            analysis_type="analyze"
        )
        assert result.success
        data = json.loads(result.output)
        assert "analysis" in data
        assert "actual_difficulty" in data["analysis"]
        assert "difficulty_score" in data["analysis"]

    @pytest.mark.asyncio
    async def test_adjust_difficulty(self, tool, sample_enemies, sample_player):
        """Test difficulty adjustment."""
        result = await tool.execute(
            enemies=sample_enemies,
            player_stats=sample_player,
            target_difficulty="hard",
            analysis_type="adjust"
        )
        assert result.success
        data = json.loads(result.output)
        assert "adjusted_enemies" in data

    @pytest.mark.asyncio
    async def test_difficulty_curve(self, tool, sample_enemies, sample_player):
        """Test difficulty curve generation."""
        result = await tool.execute(
            enemies=sample_enemies,
            player_stats=sample_player,
            analysis_type="curve"
        )
        assert result.success
        data = json.loads(result.output)
        assert "difficulty_curve" in data
        assert len(data["difficulty_curve"]) == 10  # Levels 1-10

    @pytest.mark.asyncio
    async def test_target_difficulties(self, tool, sample_enemies, sample_player):
        """Test different target difficulties."""
        for difficulty in ["easy", "medium", "hard", "nightmare"]:
            result = await tool.execute(
                enemies=sample_enemies,
                player_stats=sample_player,
                target_difficulty=difficulty
            )
            assert result.success

    @pytest.mark.asyncio
    async def test_recommendations(self, tool, sample_enemies, sample_player):
        """Test recommendations are generated."""
        result = await tool.execute(
            enemies=sample_enemies,
            player_stats=sample_player,
            target_difficulty="hard"
        )
        assert result.success
        data = json.loads(result.output)
        assert "recommendations" in data


# ============================================================================
# GenerateDialogueTool Tests
# ============================================================================


class TestGenerateDialogueTool:
    """Test dialogue generation tool."""

    @pytest.fixture
    def tool(self):
        """Create tool instance."""
        return GenerateDialogueTool()

    @pytest.mark.asyncio
    async def test_generate_yarn_dialogue(self, tool):
        """Test Yarn Spinner format generation."""
        result = await tool.execute(
            character_name="Merchant",
            personality="grumpy merchant",
            topics=["greeting", "shop"],
            format="yarn"
        )
        assert result.success
        assert "title:" in result.output
        assert "---" in result.output
        assert "===" in result.output

    @pytest.mark.asyncio
    async def test_generate_ink_dialogue(self, tool):
        """Test Ink format generation."""
        result = await tool.execute(
            character_name="Elder",
            personality="wise elder",
            topics=["greeting", "quest"],
            format="ink"
        )
        assert result.success
        assert "===" in result.output

    @pytest.mark.asyncio
    async def test_generate_json_dialogue(self, tool):
        """Test JSON format generation."""
        result = await tool.execute(
            character_name="Guard",
            personality="friendly",
            topics=["greeting"],
            format="json"
        )
        assert result.success
        data = json.loads(result.output)
        assert "character" in data
        assert "nodes" in data
        assert data["character"] == "Guard"

    @pytest.mark.asyncio
    async def test_dialogue_conditions(self, tool):
        """Test conditional logic in dialogue."""
        result = await tool.execute(
            character_name="NPC",
            topics=["greeting", "quest"],
            include_conditions=True,
            format="yarn"
        )
        assert result.success
        # Yarn should have conditional syntax
        assert "<<if" in result.output or "<<set" in result.output

    @pytest.mark.asyncio
    async def test_dialogue_topics(self, tool):
        """Test multiple topics generate nodes."""
        result = await tool.execute(
            character_name="Innkeeper",
            topics=["greeting", "quest", "shop"],
            format="json"
        )
        assert result.success
        data = json.loads(result.output)
        # Should have multiple nodes
        assert len(data["nodes"]) >= 3

    @pytest.mark.asyncio
    async def test_save_dialogue_to_file(self, tool):
        """Test saving dialogue to file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "dialogue.yarn")
            result = await tool.execute(
                character_name="Test",
                format="yarn",
                output_file=output_path
            )
            assert result.success
            assert os.path.exists(output_path)


# ============================================================================
# GenerateItemStatsTool Tests
# ============================================================================


class TestGenerateItemStatsTool:
    """Test item stats generation tool."""

    @pytest.fixture
    def tool(self):
        """Create tool instance."""
        return GenerateItemStatsTool()

    @pytest.mark.asyncio
    async def test_generate_weapon(self, tool):
        """Test weapon generation."""
        result = await tool.execute(
            item_type="weapon",
            subtype="sword",
            rarity="common",
            level=1,
            seed=42
        )
        assert result.success
        data = json.loads(result.output)
        assert len(data["items"]) == 1
        item = data["items"][0]
        assert item["type"] == "weapon"
        assert "damage" in item["stats"]

    @pytest.mark.asyncio
    async def test_generate_armor(self, tool):
        """Test armor generation."""
        result = await tool.execute(
            item_type="armor",
            subtype="chestplate",
            rarity="rare",
            level=5,
            seed=42
        )
        assert result.success
        data = json.loads(result.output)
        item = data["items"][0]
        assert item["type"] == "armor"
        assert "armor" in item["stats"]

    @pytest.mark.asyncio
    async def test_rarity_scaling(self, tool):
        """Test rarity affects stats."""
        common = await tool.execute(item_type="weapon", subtype="sword", rarity="common", level=10, seed=42)
        legendary = await tool.execute(item_type="weapon", subtype="sword", rarity="legendary", level=10, seed=42)

        common_data = json.loads(common.output)
        legendary_data = json.loads(legendary.output)

        # Legendary should have higher stats
        assert legendary_data["items"][0]["stats"]["damage"] > common_data["items"][0]["stats"]["damage"]

    @pytest.mark.asyncio
    async def test_level_scaling(self, tool):
        """Test level affects stats."""
        low = await tool.execute(item_type="weapon", rarity="common", level=1, seed=42)
        high = await tool.execute(item_type="weapon", rarity="common", level=20, seed=42)

        low_data = json.loads(low.output)
        high_data = json.loads(high.output)

        # Higher level should have higher stats
        assert high_data["items"][0]["stats"]["damage"] > low_data["items"][0]["stats"]["damage"]

    @pytest.mark.asyncio
    async def test_affixes(self, tool):
        """Test affix generation."""
        result = await tool.execute(
            item_type="weapon",
            rarity="epic",
            level=10,
            affix_count=2,
            seed=42
        )
        assert result.success
        data = json.loads(result.output)
        item = data["items"][0]
        assert "affixes" in item
        assert len(item["affixes"]) == 2

    @pytest.mark.asyncio
    async def test_scaling_formulas(self, tool):
        """Test different scaling formulas."""
        for scaling in ["linear", "exponential", "diablo"]:
            result = await tool.execute(
                item_type="weapon",
                level=10,
                scaling=scaling,
                seed=42
            )
            assert result.success

    @pytest.mark.asyncio
    async def test_multiple_items(self, tool):
        """Test generating multiple items."""
        result = await tool.execute(
            item_type="weapon",
            rarity="rare",
            level=5,
            count=5,
            seed=42
        )
        assert result.success
        data = json.loads(result.output)
        assert len(data["items"]) == 5

    @pytest.mark.asyncio
    async def test_seed_reproducibility(self, tool):
        """Test same seed produces same items."""
        result1 = await tool.execute(item_type="weapon", level=5, affix_count=2, seed=12345)
        result2 = await tool.execute(item_type="weapon", level=5, affix_count=2, seed=12345)
        assert result1.output == result2.output


# ============================================================================
# GenerateGDScriptTool Tests
# ============================================================================


class TestGenerateGDScriptTool:
    """Test GDScript generation tool."""

    @pytest.fixture
    def tool(self):
        """Create tool instance."""
        return GenerateGDScriptTool()

    @pytest.mark.asyncio
    async def test_generate_player_script_4x(self, tool):
        """Test Godot 4.x player controller."""
        result = await tool.execute(script_type="player", godot_version="4.x")
        assert result.success
        assert "extends CharacterBody2D" in result.output
        assert "@export" in result.output
        assert "move_and_slide()" in result.output

    @pytest.mark.asyncio
    async def test_generate_player_script_3x(self, tool):
        """Test Godot 3.x player controller."""
        result = await tool.execute(script_type="player", godot_version="3.x")
        assert result.success
        assert "extends KinematicBody2D" in result.output
        assert "export var" in result.output

    @pytest.mark.asyncio
    async def test_generate_enemy_script(self, tool):
        """Test enemy AI script."""
        result = await tool.execute(script_type="enemy", godot_version="4.x")
        assert result.success
        assert "detection_range" in result.output

    @pytest.mark.asyncio
    async def test_generate_item_script(self, tool):
        """Test collectible item script."""
        result = await tool.execute(script_type="item", godot_version="4.x")
        assert result.success
        assert "Area2D" in result.output
        assert "collect" in result.output.lower()

    @pytest.mark.asyncio
    async def test_generate_ui_script(self, tool):
        """Test UI script."""
        result = await tool.execute(script_type="ui", godot_version="4.x")
        assert result.success
        assert "Control" in result.output

    @pytest.mark.asyncio
    async def test_generate_projectile_script(self, tool):
        """Test projectile script."""
        result = await tool.execute(script_type="projectile", godot_version="4.x")
        assert result.success
        assert "speed" in result.output.lower()

    @pytest.mark.asyncio
    async def test_generate_platform_script(self, tool):
        """Test moving platform script."""
        result = await tool.execute(script_type="platform", godot_version="4.x")
        assert result.success
        assert "AnimatableBody2D" in result.output

    @pytest.mark.asyncio
    async def test_include_signals(self, tool):
        """Test signals are included."""
        result = await tool.execute(script_type="player", include_signals=True)
        assert result.success
        assert "signal" in result.output

    @pytest.mark.asyncio
    async def test_include_comments(self, tool):
        """Test comments are included."""
        result = await tool.execute(script_type="player", include_comments=True)
        assert result.success
        assert "##" in result.output

    @pytest.mark.asyncio
    async def test_save_to_file(self, tool):
        """Test saving script to file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "player.gd")
            result = await tool.execute(
                script_type="player",
                output_file=output_path
            )
            assert result.success
            assert os.path.exists(output_path)


# ============================================================================
# GenerateUnityScriptTool Tests
# ============================================================================


class TestGenerateUnityScriptTool:
    """Test Unity C# script generation tool."""

    @pytest.fixture
    def tool(self):
        """Create tool instance."""
        return GenerateUnityScriptTool()

    @pytest.mark.asyncio
    async def test_generate_player_script(self, tool):
        """Test player controller script."""
        result = await tool.execute(script_type="player")
        assert result.success
        assert "using UnityEngine" in result.output
        assert "class PlayerController" in result.output
        assert "MonoBehaviour" in result.output

    @pytest.mark.asyncio
    async def test_generate_enemy_script(self, tool):
        """Test enemy AI script."""
        result = await tool.execute(script_type="enemy")
        assert result.success
        assert "EnemyController" in result.output
        assert "TakeDamage" in result.output

    @pytest.mark.asyncio
    async def test_generate_item_script(self, tool):
        """Test collectible item script."""
        result = await tool.execute(script_type="item")
        assert result.success
        assert "CollectibleItem" in result.output

    @pytest.mark.asyncio
    async def test_generate_ui_script(self, tool):
        """Test UI script."""
        result = await tool.execute(script_type="ui")
        assert result.success
        assert "GameUI" in result.output

    @pytest.mark.asyncio
    async def test_generate_projectile_script(self, tool):
        """Test projectile script."""
        result = await tool.execute(script_type="projectile")
        assert result.success
        assert "Projectile" in result.output

    @pytest.mark.asyncio
    async def test_generate_platform_script(self, tool):
        """Test moving platform script."""
        result = await tool.execute(script_type="platform")
        assert result.success
        assert "MovingPlatform" in result.output

    @pytest.mark.asyncio
    async def test_namespace(self, tool):
        """Test custom namespace."""
        result = await tool.execute(script_type="player", namespace="MyGame.Players")
        assert result.success
        assert "namespace MyGame.Players" in result.output

    @pytest.mark.asyncio
    async def test_include_comments(self, tool):
        """Test XML documentation comments."""
        result = await tool.execute(script_type="player", include_comments=True)
        assert result.success
        assert "/// <summary>" in result.output

    @pytest.mark.asyncio
    async def test_save_to_file(self, tool):
        """Test saving script to file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "PlayerController.cs")
            result = await tool.execute(
                script_type="player",
                output_file=output_path
            )
            assert result.success
            assert os.path.exists(output_path)


# ============================================================================
# Integration Tests
# ============================================================================


class TestToolRegistration:
    """Test tools are properly registered."""

    def test_tools_registered(self):
        """Test all game level tools are registered."""
        from sindri.tools.registry import ToolRegistry

        registry = ToolRegistry.default()

        assert registry.get_tool("generate_tilemap") is not None
        assert registry.get_tool("generate_dungeon") is not None
        assert registry.get_tool("balance_difficulty") is not None
        assert registry.get_tool("generate_dialogue") is not None
        assert registry.get_tool("generate_item_stats") is not None
        assert registry.get_tool("generate_gdscript") is not None
        assert registry.get_tool("generate_unity_script") is not None


class TestAgentRegistration:
    """Test agent is properly registered."""

    def test_nidhogr_game_agent_exists(self):
        """Test nidhogr_game agent is registered."""
        from sindri.agents.registry import AGENTS, get_agent

        assert "nidhogr_game" in AGENTS
        agent = get_agent("nidhogr_game")
        assert agent.name == "nidhogr_game"
        assert "generate_tilemap" in agent.tools
        assert "generate_dungeon" in agent.tools

    def test_brokkr_can_delegate(self):
        """Test Brokkr can delegate to nidhogr_game."""
        from sindri.agents.registry import get_agent

        brokkr = get_agent("brokkr")
        assert "nidhogr_game" in brokkr.delegate_to


class TestConstants:
    """Test constants and lookup tables."""

    def test_tile_types(self):
        """Test TILE_TYPES contains expected tiles."""
        assert "wall" in TILE_TYPES
        assert "floor" in TILE_TYPES
        assert "door" in TILE_TYPES
        assert "stairs_up" in TILE_TYPES
        assert "stairs_down" in TILE_TYPES

    def test_rarity_multipliers(self):
        """Test rarity multipliers are ordered."""
        assert RARITY_MULTIPLIERS["common"] < RARITY_MULTIPLIERS["uncommon"]
        assert RARITY_MULTIPLIERS["uncommon"] < RARITY_MULTIPLIERS["rare"]
        assert RARITY_MULTIPLIERS["rare"] < RARITY_MULTIPLIERS["epic"]
        assert RARITY_MULTIPLIERS["epic"] < RARITY_MULTIPLIERS["legendary"]

    def test_affixes_have_ranges(self):
        """Test affixes have stat ranges."""
        for affix_name, stats in AFFIXES.items():
            for stat_name, (min_val, max_val) in stats.items():
                assert min_val <= max_val

    def test_base_weapon_stats(self):
        """Test base weapon stats exist."""
        assert "sword" in BASE_WEAPON_STATS
        assert "damage" in BASE_WEAPON_STATS["sword"]

    def test_base_armor_stats(self):
        """Test base armor stats exist."""
        assert "chestplate" in BASE_ARMOR_STATS
        assert "armor" in BASE_ARMOR_STATS["chestplate"]
