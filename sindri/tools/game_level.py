"""Game Level Tools for Sindri.

Tools for procedural game content generation, level design, difficulty balancing,
dialogue trees, and game script generation.

Used by the nidhogr_game (Game Level) agent.
"""

import json
import random
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
import structlog

from sindri.tools.base import Tool, ToolResult

log = structlog.get_logger()


# =============================================================================
# Data Structures
# =============================================================================


@dataclass
class Room:
    """Represents a room in a dungeon."""

    x: int
    y: int
    width: int
    height: int
    room_type: str = "normal"
    connections: list = field(default_factory=list)

    @property
    def center(self) -> tuple[int, int]:
        """Get the center of the room."""
        return (self.x + self.width // 2, self.y + self.height // 2)

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "height": self.height,
            "type": self.room_type,
            "center": self.center,
        }


@dataclass
class BSPNode:
    """Binary Space Partition node for dungeon generation."""

    x: int
    y: int
    width: int
    height: int
    left: Optional["BSPNode"] = None
    right: Optional["BSPNode"] = None
    room: Optional[Room] = None


# =============================================================================
# Constants
# =============================================================================


TILE_TYPES = {
    "wall": 0,
    "floor": 1,
    "door": 2,
    "water": 3,
    "lava": 4,
    "chest": 5,
    "stairs_up": 6,
    "stairs_down": 7,
    "trap": 8,
    "spawn": 9,
    "boss": 10,
}

RARITY_MULTIPLIERS = {
    "common": 1.0,
    "uncommon": 1.2,
    "rare": 1.5,
    "epic": 2.0,
    "legendary": 3.0,
}

AFFIXES = {
    "of_fire": {"fire_damage": (5, 15)},
    "of_ice": {"ice_damage": (5, 15)},
    "of_lightning": {"lightning_damage": (5, 15)},
    "of_the_bear": {"strength": (3, 10), "max_hp": (20, 50)},
    "of_the_wolf": {"agility": (3, 10), "crit_chance": (2, 8)},
    "of_the_owl": {"intelligence": (3, 10), "mana": (15, 40)},
    "vampiric": {"lifesteal": (2, 8)},
    "of_thorns": {"reflect_damage": (3, 10)},
    "swift": {"attack_speed": (5, 15)},
    "sturdy": {"armor": (5, 20)},
    "blessed": {"all_stats": (2, 5)},
    "cursed": {"damage": (10, 25), "max_hp": (-20, -10)},
}

BASE_WEAPON_STATS = {
    "sword": {"damage": 10, "speed": 1.0, "range": 1},
    "axe": {"damage": 14, "speed": 0.8, "range": 1},
    "dagger": {"damage": 6, "speed": 1.4, "range": 1},
    "bow": {"damage": 8, "speed": 1.0, "range": 5},
    "staff": {"damage": 5, "speed": 0.9, "range": 3, "magic_damage": 10},
    "spear": {"damage": 9, "speed": 0.9, "range": 2},
    "hammer": {"damage": 16, "speed": 0.6, "range": 1},
}

BASE_ARMOR_STATS = {
    "helmet": {"armor": 5, "slot": "head"},
    "chestplate": {"armor": 15, "slot": "chest"},
    "leggings": {"armor": 10, "slot": "legs"},
    "boots": {"armor": 4, "slot": "feet"},
    "gloves": {"armor": 3, "slot": "hands"},
    "shield": {"armor": 12, "block_chance": 15, "slot": "offhand"},
}


# =============================================================================
# Helper Functions
# =============================================================================


def _create_grid(width: int, height: int, fill: int = 0) -> list[list[int]]:
    """Create a 2D grid filled with a value."""
    return [[fill for _ in range(width)] for _ in range(height)]


def _flood_fill(
    grid: list[list[int]], start_x: int, start_y: int, target: int
) -> set[tuple[int, int]]:
    """Flood fill to find connected region."""
    height = len(grid)
    width = len(grid[0]) if height > 0 else 0
    visited = set()
    stack = [(start_x, start_y)]

    while stack:
        x, y = stack.pop()
        if (
            x < 0
            or x >= width
            or y < 0
            or y >= height
            or (x, y) in visited
            or grid[y][x] != target
        ):
            continue
        visited.add((x, y))
        stack.extend([(x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)])

    return visited


def _ensure_connectivity(grid: list[list[int]], floor_tile: int = 1) -> list[list[int]]:
    """Ensure all floor tiles are connected, filling isolated areas."""
    height = len(grid)
    width = len(grid[0]) if height > 0 else 0

    # Find all floor tiles
    all_floors = set()
    for y in range(height):
        for x in range(width):
            if grid[y][x] == floor_tile:
                all_floors.add((x, y))

    if not all_floors:
        return grid

    # Find largest connected region
    visited_all = set()
    regions = []

    for x, y in all_floors:
        if (x, y) not in visited_all:
            region = _flood_fill(grid, x, y, floor_tile)
            regions.append(region)
            visited_all.update(region)

    if not regions:
        return grid

    # Keep only the largest region
    largest = max(regions, key=len)
    for y in range(height):
        for x in range(width):
            if grid[y][x] == floor_tile and (x, y) not in largest:
                grid[y][x] = 0  # Wall

    return grid


def _bsp_split(
    node: BSPNode, min_size: int, rng: random.Random, depth: int = 0, max_depth: int = 5
) -> None:
    """Recursively split BSP node."""
    if depth >= max_depth:
        return

    # Check if we can split
    can_split_h = node.height >= min_size * 2
    can_split_v = node.width >= min_size * 2

    if not can_split_h and not can_split_v:
        return

    # Choose split direction
    if can_split_h and can_split_v:
        split_horizontal = rng.random() < 0.5
    else:
        split_horizontal = can_split_h

    if split_horizontal:
        # Split horizontally
        split = rng.randint(min_size, node.height - min_size)
        node.left = BSPNode(node.x, node.y, node.width, split)
        node.right = BSPNode(node.x, node.y + split, node.width, node.height - split)
    else:
        # Split vertically
        split = rng.randint(min_size, node.width - min_size)
        node.left = BSPNode(node.x, node.y, split, node.height)
        node.right = BSPNode(node.x + split, node.y, node.width - split, node.height)

    _bsp_split(node.left, min_size, rng, depth + 1, max_depth)
    _bsp_split(node.right, min_size, rng, depth + 1, max_depth)


def _create_room_in_node(
    node: BSPNode, min_size: int, rng: random.Random
) -> Optional[Room]:
    """Create a room within a BSP leaf node."""
    if node.left or node.right:
        # Not a leaf, recurse
        rooms = []
        if node.left:
            r = _create_room_in_node(node.left, min_size, rng)
            if r:
                rooms.append(r)
        if node.right:
            r = _create_room_in_node(node.right, min_size, rng)
            if r:
                rooms.append(r)
        return rooms[0] if rooms else None

    # Leaf node - create room
    room_width = rng.randint(min_size, max(min_size, node.width - 2))
    room_height = rng.randint(min_size, max(min_size, node.height - 2))
    room_x = node.x + rng.randint(1, max(1, node.width - room_width - 1))
    room_y = node.y + rng.randint(1, max(1, node.height - room_height - 1))

    node.room = Room(room_x, room_y, room_width, room_height)
    return node.room


def _get_all_rooms(node: BSPNode) -> list[Room]:
    """Get all rooms from BSP tree."""
    rooms = []
    if node.room:
        rooms.append(node.room)
    if node.left:
        rooms.extend(_get_all_rooms(node.left))
    if node.right:
        rooms.extend(_get_all_rooms(node.right))
    return rooms


def _carve_corridor(
    grid: list[list[int]],
    x1: int,
    y1: int,
    x2: int,
    y2: int,
    floor_tile: int = 1,
    width: int = 1,
) -> None:
    """Carve a corridor between two points."""
    # L-shaped corridor
    for x in range(min(x1, x2), max(x1, x2) + 1):
        for w in range(width):
            if 0 <= y1 + w < len(grid) and 0 <= x < len(grid[0]):
                grid[y1 + w][x] = floor_tile

    for y in range(min(y1, y2), max(y1, y2) + 1):
        for w in range(width):
            if 0 <= y < len(grid) and 0 <= x2 + w < len(grid[0]):
                grid[y][x2 + w] = floor_tile


def _cellular_automata(
    width: int,
    height: int,
    fill_prob: float,
    iterations: int,
    rng: random.Random,
) -> list[list[int]]:
    """Generate cave-like map using cellular automata."""
    # Initialize with random fill
    grid = [
        [0 if rng.random() < fill_prob else 1 for _ in range(width)]
        for _ in range(height)
    ]

    # Apply 4-5 rule iterations
    for _ in range(iterations):
        new_grid = _create_grid(width, height, 0)
        for y in range(height):
            for x in range(width):
                walls = 0
                for dy in range(-1, 2):
                    for dx in range(-1, 2):
                        nx, ny = x + dx, y + dy
                        if nx < 0 or nx >= width or ny < 0 or ny >= height:
                            walls += 1
                        elif grid[ny][nx] == 0:
                            walls += 1

                # 4-5 rule: become wall if >= 5 neighbors are walls
                new_grid[y][x] = 0 if walls >= 5 else 1
        grid = new_grid

    return grid


def _grid_to_ascii(grid: list[list[int]]) -> str:
    """Convert grid to ASCII representation."""
    chars = {0: "#", 1: ".", 2: "+", 3: "~", 4: "^", 5: "$", 6: "<", 7: ">", 8: "!", 9: "@", 10: "B"}
    lines = []
    for row in grid:
        line = "".join(chars.get(cell, "?") for cell in row)
        lines.append(line)
    return "\n".join(lines)


def _grid_to_tmx(
    grid: list[list[int]],
    width: int,
    height: int,
    tileset_name: str = "default",
) -> str:
    """Convert grid to TMX (Tiled Map Editor) format."""
    root = ET.Element("map")
    root.set("version", "1.10")
    root.set("tiledversion", "1.10.0")
    root.set("orientation", "orthogonal")
    root.set("renderorder", "right-down")
    root.set("width", str(width))
    root.set("height", str(height))
    root.set("tilewidth", "32")
    root.set("tileheight", "32")

    # Tileset
    tileset = ET.SubElement(root, "tileset")
    tileset.set("firstgid", "1")
    tileset.set("name", tileset_name)
    tileset.set("tilewidth", "32")
    tileset.set("tileheight", "32")

    # Layer
    layer = ET.SubElement(root, "layer")
    layer.set("id", "1")
    layer.set("name", "Ground")
    layer.set("width", str(width))
    layer.set("height", str(height))

    data = ET.SubElement(layer, "data")
    data.set("encoding", "csv")

    # Convert grid to CSV (TMX uses 1-indexed tile IDs, 0 = empty)
    csv_data = []
    for row in grid:
        csv_data.append(",".join(str(cell + 1) for cell in row))
    data.text = "\n" + ",\n".join(csv_data) + "\n"

    return ET.tostring(root, encoding="unicode")


# =============================================================================
# Tool Implementations
# =============================================================================


class GenerateTilemapTool(Tool):
    """Generate 2D tilemap layouts for games."""

    name = "generate_tilemap"
    description = """Generate 2D tilemap layouts for games.

Creates tile-based level layouts with configurable dimensions, tile types,
and placement constraints. Supports JSON, TMX (Tiled), and CSV output formats.

Use this tool to create platformer levels, top-down maps, or any 2D game levels."""

    parameters = {
        "type": "object",
        "properties": {
            "width": {
                "type": "integer",
                "minimum": 8,
                "maximum": 256,
                "description": "Map width in tiles (default: 32)",
            },
            "height": {
                "type": "integer",
                "minimum": 8,
                "maximum": 256,
                "description": "Map height in tiles (default: 24)",
            },
            "tile_types": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Available tile types (default: wall, floor, door)",
            },
            "border_walls": {
                "type": "boolean",
                "description": "Add walls around the border (default: true)",
            },
            "fill_ratio": {
                "type": "number",
                "minimum": 0.0,
                "maximum": 1.0,
                "description": "Ratio of floor to wall tiles (default: 0.6)",
            },
            "seed": {
                "type": "integer",
                "description": "Random seed for reproducibility",
            },
            "format": {
                "type": "string",
                "enum": ["json", "tmx", "csv", "ascii"],
                "description": "Output format (default: json)",
            },
            "output_file": {
                "type": "string",
                "description": "Optional file path to save the tilemap",
            },
        },
        "required": [],
    }

    async def execute(
        self,
        width: int = 32,
        height: int = 24,
        tile_types: Optional[list[str]] = None,
        border_walls: bool = True,
        fill_ratio: float = 0.6,
        seed: Optional[int] = None,
        format: str = "json",
        output_file: Optional[str] = None,
    ) -> ToolResult:
        """Generate a tilemap."""
        try:
            if seed is None:
                seed = random.randint(0, 2**31 - 1)

            rng = random.Random(seed)

            if tile_types is None:
                tile_types = ["wall", "floor", "door"]

            log.info(
                "generating_tilemap",
                width=width,
                height=height,
                seed=seed,
                format=format,
            )

            # Create grid
            grid = _create_grid(width, height, TILE_TYPES.get("wall", 0))

            # Fill interior with random tiles based on fill_ratio
            for y in range(1 if border_walls else 0, height - (1 if border_walls else 0)):
                for x in range(1 if border_walls else 0, width - (1 if border_walls else 0)):
                    if rng.random() < fill_ratio:
                        grid[y][x] = TILE_TYPES.get("floor", 1)

            # Ensure connectivity
            grid = _ensure_connectivity(grid, TILE_TYPES.get("floor", 1))

            # Add some doors at floor-wall boundaries
            door_count = max(1, (width * height) // 200)
            for _ in range(door_count):
                x = rng.randint(2, width - 3)
                y = rng.randint(2, height - 3)
                if grid[y][x] == TILE_TYPES.get("floor", 1):
                    # Check if this could be a door position
                    if (
                        grid[y - 1][x] == TILE_TYPES.get("wall", 0)
                        or grid[y + 1][x] == TILE_TYPES.get("wall", 0)
                    ):
                        grid[y][x] = TILE_TYPES.get("door", 2)

            # Format output
            if format == "json":
                output_data = {
                    "width": width,
                    "height": height,
                    "seed": seed,
                    "layers": [{"name": "ground", "data": grid}],
                    "tile_legend": {v: k for k, v in TILE_TYPES.items()},
                }
                output_str = json.dumps(output_data, indent=2)
            elif format == "tmx":
                output_str = _grid_to_tmx(grid, width, height)
            elif format == "csv":
                output_str = "\n".join(",".join(str(c) for c in row) for row in grid)
            elif format == "ascii":
                output_str = _grid_to_ascii(grid)
            else:
                output_str = json.dumps({"width": width, "height": height, "data": grid})

            # Save to file if requested
            if output_file:
                path = self._resolve_path(output_file)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(output_str)
                log.info("tilemap_saved", path=str(path))

            return ToolResult(
                success=True,
                output=output_str,
                metadata={
                    "width": width,
                    "height": height,
                    "seed": seed,
                    "format": format,
                    "output_file": str(output_file) if output_file else None,
                },
            )

        except Exception as e:
            log.error("tilemap_generation_failed", error=str(e))
            return ToolResult(
                success=False,
                output="",
                error=f"Failed to generate tilemap: {str(e)}",
            )


class GenerateDungeonTool(Tool):
    """Generate procedural dungeons with rooms and corridors."""

    name = "generate_dungeon"
    description = """Generate procedural dungeons with rooms, corridors, and features.

Supports multiple generation algorithms:
- bsp: Binary Space Partitioning for rectangular rooms
- cellular: Cellular automata for organic cave systems
- rooms: Traditional room placement with corridors

Use this tool to create roguelike dungeons, cave systems, or interior spaces."""

    parameters = {
        "type": "object",
        "properties": {
            "algorithm": {
                "type": "string",
                "enum": ["bsp", "cellular", "rooms"],
                "description": "Generation algorithm (default: bsp)",
            },
            "width": {
                "type": "integer",
                "minimum": 16,
                "maximum": 256,
                "description": "Dungeon width (default: 64)",
            },
            "height": {
                "type": "integer",
                "minimum": 16,
                "maximum": 256,
                "description": "Dungeon height (default: 48)",
            },
            "room_count": {
                "type": "integer",
                "minimum": 2,
                "maximum": 50,
                "description": "Target number of rooms (default: 8)",
            },
            "room_min_size": {
                "type": "integer",
                "minimum": 3,
                "maximum": 20,
                "description": "Minimum room dimension (default: 5)",
            },
            "room_max_size": {
                "type": "integer",
                "minimum": 5,
                "maximum": 30,
                "description": "Maximum room dimension (default: 12)",
            },
            "corridor_width": {
                "type": "integer",
                "minimum": 1,
                "maximum": 5,
                "description": "Corridor width (default: 1)",
            },
            "features": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Features to place: chests, traps, stairs_up, stairs_down, spawn, boss",
            },
            "seed": {
                "type": "integer",
                "description": "Random seed for reproducibility",
            },
            "format": {
                "type": "string",
                "enum": ["json", "tmx", "ascii"],
                "description": "Output format (default: json)",
            },
            "output_file": {
                "type": "string",
                "description": "Optional file path to save the dungeon",
            },
        },
        "required": [],
    }

    async def execute(
        self,
        algorithm: str = "bsp",
        width: int = 64,
        height: int = 48,
        room_count: int = 8,
        room_min_size: int = 5,
        room_max_size: int = 12,
        corridor_width: int = 1,
        features: Optional[list[str]] = None,
        seed: Optional[int] = None,
        format: str = "json",
        output_file: Optional[str] = None,
    ) -> ToolResult:
        """Generate a dungeon."""
        try:
            if seed is None:
                seed = random.randint(0, 2**31 - 1)

            rng = random.Random(seed)

            if features is None:
                features = ["stairs_up", "stairs_down"]

            log.info(
                "generating_dungeon",
                algorithm=algorithm,
                width=width,
                height=height,
                seed=seed,
            )

            # Generate based on algorithm
            if algorithm == "bsp":
                grid, rooms = self._generate_bsp(
                    width, height, room_min_size, room_max_size, corridor_width, rng
                )
            elif algorithm == "cellular":
                grid, rooms = self._generate_cellular(width, height, rng)
            else:  # rooms
                grid, rooms = self._generate_rooms(
                    width, height, room_count, room_min_size, room_max_size, corridor_width, rng
                )

            # Place features
            feature_positions = self._place_features(grid, rooms, features, rng)

            # Ensure connectivity
            grid = _ensure_connectivity(grid, TILE_TYPES.get("floor", 1))

            # Format output
            if format == "json":
                output_data = {
                    "width": width,
                    "height": height,
                    "algorithm": algorithm,
                    "seed": seed,
                    "grid": grid,
                    "rooms": [r.to_dict() for r in rooms],
                    "features": feature_positions,
                    "tile_legend": {v: k for k, v in TILE_TYPES.items()},
                }
                output_str = json.dumps(output_data, indent=2)
            elif format == "tmx":
                output_str = _grid_to_tmx(grid, width, height)
            else:  # ascii
                output_str = _grid_to_ascii(grid)

            # Save to file if requested
            if output_file:
                path = self._resolve_path(output_file)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(output_str)

            return ToolResult(
                success=True,
                output=output_str,
                metadata={
                    "width": width,
                    "height": height,
                    "algorithm": algorithm,
                    "room_count": len(rooms),
                    "seed": seed,
                    "format": format,
                },
            )

        except Exception as e:
            log.error("dungeon_generation_failed", error=str(e))
            return ToolResult(
                success=False,
                output="",
                error=f"Failed to generate dungeon: {str(e)}",
            )

    def _generate_bsp(
        self,
        width: int,
        height: int,
        min_size: int,
        max_size: int,
        corridor_width: int,
        rng: random.Random,
    ) -> tuple[list[list[int]], list[Room]]:
        """Generate dungeon using BSP algorithm."""
        grid = _create_grid(width, height, TILE_TYPES.get("wall", 0))

        # Create BSP tree
        root = BSPNode(0, 0, width, height)
        _bsp_split(root, min_size + 2, rng)

        # Create rooms in leaf nodes
        _create_room_in_node(root, min_size, rng)

        # Get all rooms
        rooms = _get_all_rooms(root)

        # Carve rooms into grid
        for room in rooms:
            for y in range(room.y, room.y + room.height):
                for x in range(room.x, room.x + room.width):
                    if 0 <= y < height and 0 <= x < width:
                        grid[y][x] = TILE_TYPES.get("floor", 1)

        # Connect rooms with corridors
        for i in range(len(rooms) - 1):
            c1 = rooms[i].center
            c2 = rooms[i + 1].center
            _carve_corridor(grid, c1[0], c1[1], c2[0], c2[1], TILE_TYPES.get("floor", 1), corridor_width)
            rooms[i].connections.append(i + 1)
            rooms[i + 1].connections.append(i)

        return grid, rooms

    def _generate_cellular(
        self, width: int, height: int, rng: random.Random
    ) -> tuple[list[list[int]], list[Room]]:
        """Generate cave-like dungeon using cellular automata."""
        grid = _cellular_automata(width, height, 0.45, 5, rng)

        # Find "rooms" as connected regions
        rooms = []
        visited = set()

        for y in range(height):
            for x in range(width):
                if grid[y][x] == 1 and (x, y) not in visited:
                    region = _flood_fill(grid, x, y, 1)
                    if len(region) >= 20:  # Minimum room size
                        min_x = min(p[0] for p in region)
                        max_x = max(p[0] for p in region)
                        min_y = min(p[1] for p in region)
                        max_y = max(p[1] for p in region)
                        room = Room(min_x, min_y, max_x - min_x + 1, max_y - min_y + 1, "cave")
                        rooms.append(room)
                    visited.update(region)

        return grid, rooms

    def _generate_rooms(
        self,
        width: int,
        height: int,
        room_count: int,
        min_size: int,
        max_size: int,
        corridor_width: int,
        rng: random.Random,
    ) -> tuple[list[list[int]], list[Room]]:
        """Generate dungeon using room placement algorithm."""
        grid = _create_grid(width, height, TILE_TYPES.get("wall", 0))
        rooms = []

        attempts = 0
        max_attempts = room_count * 20

        while len(rooms) < room_count and attempts < max_attempts:
            attempts += 1

            # Generate random room
            room_width = rng.randint(min_size, max_size)
            room_height = rng.randint(min_size, max_size)
            room_x = rng.randint(1, width - room_width - 1)
            room_y = rng.randint(1, height - room_height - 1)

            new_room = Room(room_x, room_y, room_width, room_height)

            # Check for overlap with existing rooms (with padding)
            overlap = False
            for existing in rooms:
                if (
                    new_room.x < existing.x + existing.width + 2
                    and new_room.x + new_room.width + 2 > existing.x
                    and new_room.y < existing.y + existing.height + 2
                    and new_room.y + new_room.height + 2 > existing.y
                ):
                    overlap = True
                    break

            if not overlap:
                # Carve room
                for y in range(new_room.y, new_room.y + new_room.height):
                    for x in range(new_room.x, new_room.x + new_room.width):
                        grid[y][x] = TILE_TYPES.get("floor", 1)

                # Connect to previous room
                if rooms:
                    prev_center = rooms[-1].center
                    new_center = new_room.center
                    _carve_corridor(
                        grid, prev_center[0], prev_center[1], new_center[0], new_center[1],
                        TILE_TYPES.get("floor", 1), corridor_width
                    )
                    rooms[-1].connections.append(len(rooms))
                    new_room.connections.append(len(rooms) - 1)

                rooms.append(new_room)

        return grid, rooms

    def _place_features(
        self,
        grid: list[list[int]],
        rooms: list[Room],
        features: list[str],
        rng: random.Random,
    ) -> dict[str, list[tuple[int, int]]]:
        """Place features in the dungeon."""
        feature_positions = {f: [] for f in features}
        height = len(grid)
        width = len(grid[0]) if height > 0 else 0

        if not rooms:
            return feature_positions

        # Place spawn in first room
        if "spawn" in features:
            spawn_room = rooms[0]
            pos = spawn_room.center
            if 0 <= pos[1] < height and 0 <= pos[0] < width:
                grid[pos[1]][pos[0]] = TILE_TYPES.get("spawn", 9)
                feature_positions["spawn"].append(pos)

        # Place boss in last room
        if "boss" in features and len(rooms) > 1:
            boss_room = rooms[-1]
            boss_room.room_type = "boss"
            pos = boss_room.center
            if 0 <= pos[1] < height and 0 <= pos[0] < width:
                grid[pos[1]][pos[0]] = TILE_TYPES.get("boss", 10)
                feature_positions["boss"].append(pos)

        # Place stairs
        if "stairs_up" in features and len(rooms) >= 1:
            room = rooms[0]
            x = room.x + rng.randint(1, max(1, room.width - 2))
            y = room.y + rng.randint(1, max(1, room.height - 2))
            if 0 <= y < height and 0 <= x < width and grid[y][x] == TILE_TYPES.get("floor", 1):
                grid[y][x] = TILE_TYPES.get("stairs_up", 6)
                feature_positions["stairs_up"].append((x, y))

        if "stairs_down" in features and len(rooms) >= 2:
            room = rooms[-1]
            x = room.x + rng.randint(1, max(1, room.width - 2))
            y = room.y + rng.randint(1, max(1, room.height - 2))
            if 0 <= y < height and 0 <= x < width and grid[y][x] == TILE_TYPES.get("floor", 1):
                grid[y][x] = TILE_TYPES.get("stairs_down", 7)
                feature_positions["stairs_down"].append((x, y))

        # Place chests and traps in random rooms
        for feature in ["chests", "traps"]:
            if feature in features and len(rooms) > 2:
                count = rng.randint(1, min(3, len(rooms) - 2))
                for _ in range(count):
                    room = rng.choice(rooms[1:-1])  # Avoid first and last room
                    x = room.x + rng.randint(1, max(1, room.width - 2))
                    y = room.y + rng.randint(1, max(1, room.height - 2))
                    if 0 <= y < height and 0 <= x < width and grid[y][x] == TILE_TYPES.get("floor", 1):
                        tile = "chest" if feature == "chests" else "trap"
                        grid[y][x] = TILE_TYPES.get(tile, 5 if tile == "chest" else 8)
                        feature_positions[feature].append((x, y))

        return feature_positions


class BalanceDifficultyTool(Tool):
    """Analyze and adjust game difficulty curves."""

    name = "balance_difficulty"
    description = """Analyze and adjust game difficulty curves.

Evaluates enemy encounters, player stats, and level design to provide
balance recommendations. Can analyze existing configurations or suggest
adjustments to achieve target difficulty levels.

Use this tool to ensure fair challenge progression in your game."""

    parameters = {
        "type": "object",
        "properties": {
            "enemies": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "hp": {"type": "number"},
                        "damage": {"type": "number"},
                        "attack_speed": {"type": "number"},
                        "count": {"type": "integer"},
                    },
                },
                "description": "Enemy definitions with stats",
            },
            "player_stats": {
                "type": "object",
                "properties": {
                    "hp": {"type": "number"},
                    "damage": {"type": "number"},
                    "attack_speed": {"type": "number"},
                    "armor": {"type": "number"},
                },
                "description": "Expected player stats",
            },
            "level": {
                "type": "integer",
                "description": "Game level/stage number",
            },
            "target_difficulty": {
                "type": "string",
                "enum": ["easy", "medium", "hard", "nightmare"],
                "description": "Target difficulty level (default: medium)",
            },
            "analysis_type": {
                "type": "string",
                "enum": ["analyze", "adjust", "curve"],
                "description": "Type of analysis (default: analyze)",
            },
            "output_file": {
                "type": "string",
                "description": "Optional file path to save the analysis",
            },
        },
        "required": ["enemies", "player_stats"],
    }

    async def execute(
        self,
        enemies: list[dict],
        player_stats: dict,
        level: int = 1,
        target_difficulty: str = "medium",
        analysis_type: str = "analyze",
        output_file: Optional[str] = None,
    ) -> ToolResult:
        """Analyze or adjust difficulty."""
        try:
            log.info(
                "analyzing_difficulty",
                enemy_count=len(enemies),
                level=level,
                target=target_difficulty,
            )

            # Difficulty multipliers
            difficulty_mults = {
                "easy": 0.7,
                "medium": 1.0,
                "hard": 1.4,
                "nightmare": 2.0,
            }
            target_mult = difficulty_mults.get(target_difficulty, 1.0)

            # Calculate player DPS
            player_damage = player_stats.get("damage", 10)
            player_speed = player_stats.get("attack_speed", 1.0)
            player_hp = player_stats.get("hp", 100)
            player_armor = player_stats.get("armor", 0)
            player_dps = player_damage * player_speed

            # Calculate total enemy stats
            total_enemy_hp = 0
            total_enemy_dps = 0
            enemy_analysis = []

            for enemy in enemies:
                count = enemy.get("count", 1)
                hp = enemy.get("hp", 50) * count
                damage = enemy.get("damage", 10)
                speed = enemy.get("attack_speed", 1.0)
                dps = damage * speed * count

                total_enemy_hp += hp
                total_enemy_dps += dps

                # Time to kill this enemy type
                ttk = hp / max(1, player_dps)

                enemy_analysis.append({
                    "name": enemy.get("name", "Unknown"),
                    "count": count,
                    "total_hp": hp,
                    "dps": dps,
                    "time_to_kill": round(ttk, 2),
                })

            # Calculate key metrics
            player_ttk = total_enemy_hp / max(1, player_dps)
            enemy_ttk = player_hp / max(1, total_enemy_dps - player_armor * 0.5)
            dps_ratio = player_dps / max(1, total_enemy_dps)
            survival_ratio = enemy_ttk / max(1, player_ttk)

            # Determine actual difficulty
            if survival_ratio > 3.0:
                actual_difficulty = "easy"
                difficulty_score = 2.0
            elif survival_ratio > 1.5:
                actual_difficulty = "medium"
                difficulty_score = 5.0
            elif survival_ratio > 0.8:
                actual_difficulty = "hard"
                difficulty_score = 7.5
            else:
                actual_difficulty = "nightmare"
                difficulty_score = 9.5

            # Generate recommendations
            recommendations = []

            if actual_difficulty != target_difficulty:
                if survival_ratio < target_mult:
                    recommendations.append(
                        f"Reduce total enemy HP by {int((1 - survival_ratio / target_mult) * 100)}%"
                    )
                    recommendations.append(
                        f"Or reduce enemy count from {sum(e.get('count', 1) for e in enemies)} to {int(sum(e.get('count', 1) for e in enemies) * survival_ratio / target_mult)}"
                    )
                else:
                    recommendations.append(
                        f"Increase enemy HP by {int((survival_ratio / target_mult - 1) * 100)}%"
                    )
                    recommendations.append(
                        "Or add more enemies to increase challenge"
                    )

            # Generate adjusted enemies if requested
            adjusted_enemies = None
            if analysis_type == "adjust":
                scale_factor = target_mult / max(0.1, survival_ratio)
                adjusted_enemies = []
                for enemy in enemies:
                    adjusted = enemy.copy()
                    adjusted["hp"] = round(enemy.get("hp", 50) * scale_factor)
                    adjusted["damage"] = round(enemy.get("damage", 10) * (scale_factor ** 0.5))
                    adjusted_enemies.append(adjusted)

            # Generate difficulty curve if requested
            curve_data = None
            if analysis_type == "curve":
                curve_data = []
                for lvl in range(1, 11):
                    lvl_scale = 1 + (lvl - 1) * 0.15
                    curve_data.append({
                        "level": lvl,
                        "recommended_enemy_hp": round(50 * lvl_scale * target_mult),
                        "recommended_enemy_damage": round(10 * lvl_scale * (target_mult ** 0.5)),
                        "recommended_player_hp": round(100 * lvl_scale),
                        "recommended_player_damage": round(15 * lvl_scale),
                    })

            # Build result
            result = {
                "analysis": {
                    "actual_difficulty": actual_difficulty,
                    "target_difficulty": target_difficulty,
                    "difficulty_score": round(difficulty_score, 1),
                    "player_time_to_kill": round(player_ttk, 2),
                    "enemy_time_to_kill": round(enemy_ttk, 2),
                    "dps_ratio": round(dps_ratio, 2),
                    "survival_ratio": round(survival_ratio, 2),
                },
                "enemy_breakdown": enemy_analysis,
                "recommendations": recommendations,
            }

            if adjusted_enemies:
                result["adjusted_enemies"] = adjusted_enemies

            if curve_data:
                result["difficulty_curve"] = curve_data

            output_str = json.dumps(result, indent=2)

            # Save to file if requested
            if output_file:
                path = self._resolve_path(output_file)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(output_str)

            return ToolResult(
                success=True,
                output=output_str,
                metadata={
                    "actual_difficulty": actual_difficulty,
                    "target_difficulty": target_difficulty,
                    "difficulty_score": difficulty_score,
                    "balanced": actual_difficulty == target_difficulty,
                },
            )

        except Exception as e:
            log.error("difficulty_analysis_failed", error=str(e))
            return ToolResult(
                success=False,
                output="",
                error=f"Failed to analyze difficulty: {str(e)}",
            )


class GenerateDialogueTool(Tool):
    """Generate NPC dialogue trees."""

    name = "generate_dialogue"
    description = """Generate NPC dialogue trees in Yarn Spinner, Ink, or JSON format.

Creates branching conversation trees with character personality, topics,
conditional logic, and player choices. Supports multiple dialogue formats
used by popular game engines.

Use this tool to create interactive NPC conversations."""

    parameters = {
        "type": "object",
        "properties": {
            "character_name": {
                "type": "string",
                "description": "NPC name",
            },
            "personality": {
                "type": "string",
                "description": "Character personality (e.g., 'grumpy merchant', 'wise elder')",
            },
            "topics": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Conversation topics to include",
            },
            "format": {
                "type": "string",
                "enum": ["yarn", "ink", "json"],
                "description": "Output format (default: yarn)",
            },
            "include_conditions": {
                "type": "boolean",
                "description": "Include conditional logic (default: true)",
            },
            "branch_count": {
                "type": "integer",
                "minimum": 1,
                "maximum": 6,
                "description": "Number of dialogue branches (default: 3)",
            },
            "output_file": {
                "type": "string",
                "description": "Optional file path to save the dialogue",
            },
        },
        "required": ["character_name"],
    }

    async def execute(
        self,
        character_name: str,
        personality: str = "friendly",
        topics: Optional[list[str]] = None,
        format: str = "yarn",
        include_conditions: bool = True,
        branch_count: int = 3,
        output_file: Optional[str] = None,
    ) -> ToolResult:
        """Generate dialogue tree."""
        try:
            if topics is None:
                topics = ["greeting", "quest", "shop"]

            log.info(
                "generating_dialogue",
                character=character_name,
                format=format,
                topics=topics,
            )

            # Generate dialogue based on format
            if format == "yarn":
                output_str = self._generate_yarn(
                    character_name, personality, topics, include_conditions, branch_count
                )
            elif format == "ink":
                output_str = self._generate_ink(
                    character_name, personality, topics, include_conditions, branch_count
                )
            else:  # json
                output_str = self._generate_json(
                    character_name, personality, topics, include_conditions, branch_count
                )

            # Save to file if requested
            if output_file:
                path = self._resolve_path(output_file)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(output_str)

            return ToolResult(
                success=True,
                output=output_str,
                metadata={
                    "character": character_name,
                    "format": format,
                    "topics": topics,
                    "branch_count": branch_count,
                },
            )

        except Exception as e:
            log.error("dialogue_generation_failed", error=str(e))
            return ToolResult(
                success=False,
                output="",
                error=f"Failed to generate dialogue: {str(e)}",
            )

    def _generate_yarn(
        self,
        name: str,
        personality: str,
        topics: list[str],
        conditions: bool,
        branches: int,
    ) -> str:
        """Generate Yarn Spinner format dialogue."""
        lines = []

        # Greeting node
        lines.append(f"title: {name}_Greeting")
        lines.append(f"tags: npc, {personality.replace(' ', '_')}")
        lines.append("---")

        if conditions:
            lines.append(f"<<if visited_{name.lower()}>>")
            lines.append(f"{name}: Ah, you're back. What can I do for you?")
            lines.append("<<else>>")
            lines.append(f"<<set visited_{name.lower()} to true>>")

        # Personality-based greeting
        if "grumpy" in personality.lower():
            lines.append(f"{name}: What do you want? Make it quick.")
        elif "friendly" in personality.lower():
            lines.append(f"{name}: Hello there, traveler! Welcome!")
        elif "wise" in personality.lower():
            lines.append(f"{name}: Greetings, young one. I sense you seek knowledge.")
        else:
            lines.append(f"{name}: Hello. How may I help you?")

        if conditions:
            lines.append("<<endif>>")

        lines.append("")

        # Add topic choices
        for i, topic in enumerate(topics[:branches]):
            topic_title = topic.replace(" ", "_").title()
            if topic == "greeting":
                lines.append(f"-> Who are you?")
                lines.append(f"    <<jump {name}_{topic_title}>>")
            elif topic == "quest":
                lines.append(f"-> Do you have any work for me?")
                lines.append(f"    <<jump {name}_{topic_title}>>")
            elif topic == "shop":
                lines.append(f"-> Let me see your wares.")
                lines.append(f"    <<jump {name}_{topic_title}>>")
            else:
                lines.append(f"-> Tell me about {topic}.")
                lines.append(f"    <<jump {name}_{topic_title}>>")

        lines.append("-> Goodbye.")
        lines.append(f"    {name}: Farewell.")
        lines.append("===")
        lines.append("")

        # Generate topic nodes
        for topic in topics[:branches]:
            topic_title = topic.replace(" ", "_").title()
            lines.append(f"title: {name}_{topic_title}")
            lines.append(f"tags: {topic}")
            lines.append("---")

            if topic == "quest":
                if conditions:
                    lines.append(f"<<if has_quest_{name.lower()}>>")
                    lines.append(f"{name}: You're still working on that task I gave you.")
                    lines.append("<<else>>")

                lines.append(f"{name}: I need someone to help me with a task.")
                lines.append("-> What kind of task?")
                lines.append(f"    {name}: There's trouble nearby that needs dealing with.")
                if conditions:
                    lines.append(f"    <<set has_quest_{name.lower()} to true>>")
                lines.append("-> Not interested.")
                lines.append(f"    {name}: Suit yourself.")

                if conditions:
                    lines.append("<<endif>>")

            elif topic == "shop":
                lines.append(f"{name}: Take a look at what I have for sale.")
                lines.append("<<open_shop>>")

            else:
                lines.append(f"{name}: Ah, you want to know about {topic}?")
                lines.append(f"{name}: Let me tell you what I know...")

            lines.append(f"<<jump {name}_Greeting>>")
            lines.append("===")
            lines.append("")

        return "\n".join(lines)

    def _generate_ink(
        self,
        name: str,
        personality: str,
        topics: list[str],
        conditions: bool,
        branches: int,
    ) -> str:
        """Generate Ink format dialogue."""
        lines = []

        # Variables
        if conditions:
            lines.append(f"VAR visited_{name.lower()} = false")
            lines.append(f"VAR has_quest_{name.lower()} = false")
            lines.append("")

        # Main conversation
        lines.append(f"=== {name.lower()}_conversation ===")

        if conditions:
            lines.append(f"{{visited_{name.lower()}:")
            lines.append(f'    "{name.upper()}: Ah, you\'re back."')
            lines.append("- else:")
            lines.append(f"    ~ visited_{name.lower()} = true")

        # Greeting based on personality
        if "grumpy" in personality.lower():
            greeting = "What do you want?"
        elif "friendly" in personality.lower():
            greeting = "Hello there, friend!"
        elif "wise" in personality.lower():
            greeting = "Greetings, seeker of knowledge."
        else:
            greeting = "How may I help you?"

        if conditions:
            lines.append(f'    "{name.upper()}: {greeting}"')
            lines.append("}")
        else:
            lines.append(f'"{name.upper()}: {greeting}"')

        lines.append("")

        # Choices
        for topic in topics[:branches]:
            if topic == "quest":
                lines.append(f"* [Ask about work] -> {name.lower()}_quest")
            elif topic == "shop":
                lines.append(f"* [View wares] -> {name.lower()}_shop")
            else:
                lines.append(f"* [Ask about {topic}] -> {name.lower()}_{topic}")

        lines.append(f"* [Leave] -> {name.lower()}_farewell")
        lines.append("")

        # Topic sections
        for topic in topics[:branches]:
            lines.append(f"=== {name.lower()}_{topic} ===")
            if topic == "quest":
                if conditions:
                    lines.append(f"{{has_quest_{name.lower()}:")
                    lines.append(f'    "{name.upper()}: Still working on that task?"')
                    lines.append(f"    -> {name.lower()}_conversation")
                    lines.append("}")
                lines.append(f'"{name.upper()}: I have a job for you, if you\'re interested."')
                lines.append("* [Accept]")
                if conditions:
                    lines.append(f"    ~ has_quest_{name.lower()} = true")
                lines.append(f'    "{name.upper()}: Excellent. Here are the details..."')
                lines.append("* [Decline]")
                lines.append(f'    "{name.upper()}: Another time, perhaps."')
            elif topic == "shop":
                lines.append(f'"{name.upper()}: Here\'s what I have for sale."')
                lines.append("# OPEN_SHOP")
            else:
                lines.append(f'"{name.upper()}: You want to know about {topic}?"')
                lines.append(f'"{name.upper()}: Let me tell you what I know..."')

            lines.append(f"-> {name.lower()}_conversation")
            lines.append("")

        # Farewell
        lines.append(f"=== {name.lower()}_farewell ===")
        lines.append(f'"{name.upper()}: Farewell, traveler."')
        lines.append("-> END")

        return "\n".join(lines)

    def _generate_json(
        self,
        name: str,
        personality: str,
        topics: list[str],
        conditions: bool,
        branches: int,
    ) -> str:
        """Generate JSON format dialogue tree."""
        dialogue = {
            "character": name,
            "personality": personality,
            "nodes": {},
        }

        # Greeting node
        if "grumpy" in personality.lower():
            greeting_text = "What do you want? Make it quick."
        elif "friendly" in personality.lower():
            greeting_text = "Hello there, traveler! Welcome!"
        elif "wise" in personality.lower():
            greeting_text = "Greetings, young one."
        else:
            greeting_text = "How may I help you?"

        choices = []
        for topic in topics[:branches]:
            if topic == "quest":
                choices.append({"text": "Do you have any work?", "next": "quest"})
            elif topic == "shop":
                choices.append({"text": "Show me your wares.", "next": "shop"})
            else:
                choices.append({"text": f"Tell me about {topic}.", "next": topic})

        choices.append({"text": "Goodbye.", "next": "farewell"})

        dialogue["nodes"]["greeting"] = {
            "speaker": name,
            "text": greeting_text,
            "choices": choices,
        }

        if conditions:
            dialogue["nodes"]["greeting"]["conditions"] = {
                "if_visited": {
                    "text": "Ah, you're back. What can I do for you?",
                }
            }

        # Topic nodes
        for topic in topics[:branches]:
            if topic == "quest":
                dialogue["nodes"]["quest"] = {
                    "speaker": name,
                    "text": "I have a task that needs doing. Are you interested?",
                    "choices": [
                        {"text": "Yes, I'll help.", "next": "quest_accept", "set_flag": "has_quest"},
                        {"text": "Not right now.", "next": "greeting"},
                    ],
                }
                dialogue["nodes"]["quest_accept"] = {
                    "speaker": name,
                    "text": "Excellent! Here are the details...",
                    "next": "greeting",
                }
            elif topic == "shop":
                dialogue["nodes"]["shop"] = {
                    "speaker": name,
                    "text": "Take a look at my wares.",
                    "action": "open_shop",
                    "next": "greeting",
                }
            else:
                dialogue["nodes"][topic] = {
                    "speaker": name,
                    "text": f"You want to know about {topic}? Let me tell you...",
                    "next": "greeting",
                }

        # Farewell node
        dialogue["nodes"]["farewell"] = {
            "speaker": name,
            "text": "Farewell, traveler.",
            "end": True,
        }

        return json.dumps(dialogue, indent=2)


class GenerateItemStatsTool(Tool):
    """Generate balanced item and weapon statistics."""

    name = "generate_item_stats"
    description = """Generate balanced item and weapon statistics for games.

Creates items with appropriate stats based on level, rarity, and scaling formulas.
Supports weapon and armor types with optional affix/enchantment systems.

Use this tool to create balanced loot tables and item progression."""

    parameters = {
        "type": "object",
        "properties": {
            "item_type": {
                "type": "string",
                "enum": ["weapon", "armor", "consumable", "accessory"],
                "description": "Type of item to generate",
            },
            "subtype": {
                "type": "string",
                "description": "Specific subtype (e.g., 'sword', 'helmet')",
            },
            "rarity": {
                "type": "string",
                "enum": ["common", "uncommon", "rare", "epic", "legendary"],
                "description": "Item rarity (default: common)",
            },
            "level": {
                "type": "integer",
                "minimum": 1,
                "maximum": 100,
                "description": "Item level (default: 1)",
            },
            "scaling": {
                "type": "string",
                "enum": ["linear", "exponential", "diablo"],
                "description": "Stat scaling formula (default: linear)",
            },
            "affix_count": {
                "type": "integer",
                "minimum": 0,
                "maximum": 4,
                "description": "Number of affixes to add (default: 0)",
            },
            "count": {
                "type": "integer",
                "minimum": 1,
                "maximum": 20,
                "description": "Number of items to generate (default: 1)",
            },
            "seed": {
                "type": "integer",
                "description": "Random seed for reproducibility",
            },
            "output_file": {
                "type": "string",
                "description": "Optional file path to save the items",
            },
        },
        "required": ["item_type"],
    }

    async def execute(
        self,
        item_type: str,
        subtype: Optional[str] = None,
        rarity: str = "common",
        level: int = 1,
        scaling: str = "linear",
        affix_count: int = 0,
        count: int = 1,
        seed: Optional[int] = None,
        output_file: Optional[str] = None,
    ) -> ToolResult:
        """Generate item stats."""
        try:
            if seed is None:
                seed = random.randint(0, 2**31 - 1)

            rng = random.Random(seed)

            log.info(
                "generating_items",
                type=item_type,
                rarity=rarity,
                level=level,
                count=count,
            )

            items = []
            for i in range(count):
                item = self._generate_single_item(
                    item_type, subtype, rarity, level, scaling, affix_count, rng
                )
                items.append(item)

            result = {
                "items": items,
                "generation_params": {
                    "seed": seed,
                    "scaling": scaling,
                    "rarity_multiplier": RARITY_MULTIPLIERS.get(rarity, 1.0),
                },
            }

            output_str = json.dumps(result, indent=2)

            # Save to file if requested
            if output_file:
                path = self._resolve_path(output_file)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(output_str)

            return ToolResult(
                success=True,
                output=output_str,
                metadata={
                    "item_count": len(items),
                    "item_type": item_type,
                    "rarity": rarity,
                    "level": level,
                    "seed": seed,
                },
            )

        except Exception as e:
            log.error("item_generation_failed", error=str(e))
            return ToolResult(
                success=False,
                output="",
                error=f"Failed to generate items: {str(e)}",
            )

    def _generate_single_item(
        self,
        item_type: str,
        subtype: Optional[str],
        rarity: str,
        level: int,
        scaling: str,
        affix_count: int,
        rng: random.Random,
    ) -> dict:
        """Generate a single item."""
        rarity_mult = RARITY_MULTIPLIERS.get(rarity, 1.0)

        # Determine subtype
        if item_type == "weapon":
            if subtype is None:
                subtype = rng.choice(list(BASE_WEAPON_STATS.keys()))
            base_stats = BASE_WEAPON_STATS.get(subtype, BASE_WEAPON_STATS["sword"]).copy()
        elif item_type == "armor":
            if subtype is None:
                subtype = rng.choice(list(BASE_ARMOR_STATS.keys()))
            base_stats = BASE_ARMOR_STATS.get(subtype, BASE_ARMOR_STATS["chestplate"]).copy()
        elif item_type == "consumable":
            subtype = subtype or "potion"
            base_stats = {"healing": 50, "duration": 0}
        else:  # accessory
            subtype = subtype or "ring"
            base_stats = {"bonus": 5}

        # Apply scaling
        scaled_stats = {}
        for stat, value in base_stats.items():
            if isinstance(value, (int, float)) and stat not in ["slot"]:
                if scaling == "linear":
                    scaled_value = value * (1 + 0.1 * (level - 1)) * rarity_mult
                elif scaling == "exponential":
                    scaled_value = value * (1.05 ** (level - 1)) * rarity_mult
                else:  # diablo
                    scaled_value = value * (1 + 0.15 * (level - 1)) * rarity_mult
                    # Add variance
                    scaled_value *= rng.uniform(0.85, 1.15)
                scaled_stats[stat] = round(scaled_value)
            else:
                scaled_stats[stat] = value

        # Generate name
        name_parts = []

        # Add affixes
        applied_affixes = []
        if affix_count > 0:
            available_affixes = list(AFFIXES.keys())
            selected = rng.sample(available_affixes, min(affix_count, len(available_affixes)))

            for affix_name in selected:
                affix_stats = AFFIXES[affix_name]
                for stat, (min_val, max_val) in affix_stats.items():
                    bonus = rng.randint(min_val, max_val)
                    if scaling != "linear":
                        bonus = round(bonus * (1 + 0.05 * (level - 1)))
                    if stat in scaled_stats:
                        scaled_stats[stat] += bonus
                    else:
                        scaled_stats[stat] = bonus
                applied_affixes.append(affix_name)

                # Add prefix/suffix to name
                if affix_name.startswith("of_"):
                    name_parts.append(affix_name.replace("of_", "").replace("_", " ").title())

        # Build item name
        rarity_prefix = {"uncommon": "Fine", "rare": "Superior", "epic": "Exquisite", "legendary": "Legendary"}
        if rarity in rarity_prefix:
            name_parts.insert(0, rarity_prefix[rarity])

        name_parts.append(subtype.title())

        if applied_affixes:
            suffix_affixes = [a for a in applied_affixes if a.startswith("of_")]
            if suffix_affixes:
                name_parts.append(suffix_affixes[0].replace("_", " ").title())

        item = {
            "name": " ".join(name_parts),
            "type": item_type,
            "subtype": subtype,
            "rarity": rarity,
            "level": level,
            "stats": scaled_stats,
        }

        if applied_affixes:
            item["affixes"] = applied_affixes

        return item


class GenerateGDScriptTool(Tool):
    """Generate Godot GDScript code."""

    name = "generate_gdscript"
    description = """Generate Godot GDScript code for game mechanics.

Creates GDScript templates for common game patterns like player controllers,
enemy AI, item systems, and UI components. Supports Godot 3.x and 4.x syntax.

Use this tool to quickly scaffold Godot game scripts."""

    parameters = {
        "type": "object",
        "properties": {
            "script_type": {
                "type": "string",
                "enum": ["player", "enemy", "item", "ui", "projectile", "platform"],
                "description": "Type of script to generate",
            },
            "godot_version": {
                "type": "string",
                "enum": ["3.x", "4.x"],
                "description": "Godot version (default: 4.x)",
            },
            "description": {
                "type": "string",
                "description": "Additional description of desired behavior",
            },
            "include_signals": {
                "type": "boolean",
                "description": "Include signal definitions (default: true)",
            },
            "include_comments": {
                "type": "boolean",
                "description": "Include documentation comments (default: true)",
            },
            "output_file": {
                "type": "string",
                "description": "Optional file path to save the script",
            },
        },
        "required": ["script_type"],
    }

    async def execute(
        self,
        script_type: str,
        godot_version: str = "4.x",
        description: Optional[str] = None,
        include_signals: bool = True,
        include_comments: bool = True,
        output_file: Optional[str] = None,
    ) -> ToolResult:
        """Generate GDScript."""
        try:
            log.info(
                "generating_gdscript",
                type=script_type,
                version=godot_version,
            )

            # Generate based on type and version
            if godot_version == "4.x":
                script = self._generate_gdscript_4(script_type, include_signals, include_comments)
            else:
                script = self._generate_gdscript_3(script_type, include_signals, include_comments)

            # Save to file if requested
            if output_file:
                path = self._resolve_path(output_file)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(script)

            return ToolResult(
                success=True,
                output=script,
                metadata={
                    "script_type": script_type,
                    "godot_version": godot_version,
                    "output_file": str(output_file) if output_file else None,
                },
            )

        except Exception as e:
            log.error("gdscript_generation_failed", error=str(e))
            return ToolResult(
                success=False,
                output="",
                error=f"Failed to generate GDScript: {str(e)}",
            )

    def _generate_gdscript_4(self, script_type: str, signals: bool, comments: bool) -> str:
        """Generate Godot 4.x GDScript."""
        templates = {
            "player": '''extends CharacterBody2D
{comments}
{signals}
@export var speed: float = 200.0
@export var jump_force: float = -400.0
@export var max_health: int = 100

var health: int = max_health
var gravity: float = ProjectSettings.get_setting("physics/2d/default_gravity")

func _ready() -> void:
\thealth = max_health

func _physics_process(delta: float) -> void:
\t# Apply gravity
\tif not is_on_floor():
\t\tvelocity.y += gravity * delta
\t
\t# Handle jump
\tif Input.is_action_just_pressed("jump") and is_on_floor():
\t\tvelocity.y = jump_force
\t\t{emit_jumped}
\t
\t# Handle horizontal movement
\tvar direction := Input.get_axis("move_left", "move_right")
\tif direction:
\t\tvelocity.x = direction * speed
\telse:
\t\tvelocity.x = move_toward(velocity.x, 0, speed)
\t
\tmove_and_slide()

func take_damage(amount: int) -> void:
\thealth -= amount
\t{emit_damaged}
\tif health <= 0:
\t\tdie()

func die() -> void:
\t{emit_died}
\tqueue_free()
''',
            "enemy": '''extends CharacterBody2D
{comments}
{signals}
@export var speed: float = 100.0
@export var max_health: int = 50
@export var damage: int = 10
@export var detection_range: float = 200.0

var health: int = max_health
var target: Node2D = null
var gravity: float = ProjectSettings.get_setting("physics/2d/default_gravity")

func _ready() -> void:
\thealth = max_health

func _physics_process(delta: float) -> void:
\t# Apply gravity
\tif not is_on_floor():
\t\tvelocity.y += gravity * delta
\t
\t# Find and chase player
\tif target and is_instance_valid(target):
\t\tvar direction := sign(target.global_position.x - global_position.x)
\t\tvelocity.x = direction * speed
\telse:
\t\tvelocity.x = 0
\t\t_find_target()
\t
\tmove_and_slide()

func _find_target() -> void:
\tvar player := get_tree().get_first_node_in_group("player")
\tif player and global_position.distance_to(player.global_position) < detection_range:
\t\ttarget = player

func take_damage(amount: int) -> void:
\thealth -= amount
\t{emit_damaged}
\tif health <= 0:
\t\tdie()

func die() -> void:
\t{emit_died}
\tqueue_free()
''',
            "item": '''extends Area2D
{comments}
{signals}
@export var item_name: String = "Item"
@export var item_value: int = 10
@export var item_type: String = "consumable"

var collected: bool = false

func _ready() -> void:
\tbody_entered.connect(_on_body_entered)

func _on_body_entered(body: Node2D) -> void:
\tif collected:
\t\treturn
\tif body.is_in_group("player"):
\t\tcollect(body)

func collect(collector: Node2D) -> void:
\tcollected = true
\t{emit_collected}
\t
\t# Apply item effect
\tif collector.has_method("add_item"):
\t\tcollector.add_item(item_name, item_value, item_type)
\t
\tqueue_free()
''',
            "ui": '''extends Control
{comments}
{signals}
@onready var health_bar: ProgressBar = $HealthBar
@onready var score_label: Label = $ScoreLabel

var current_score: int = 0

func _ready() -> void:
\t_update_display()

func set_health(current: int, maximum: int) -> void:
\tif health_bar:
\t\thealth_bar.max_value = maximum
\t\thealth_bar.value = current

func add_score(amount: int) -> void:
\tcurrent_score += amount
\t{emit_score}
\t_update_display()

func _update_display() -> void:
\tif score_label:
\t\tscore_label.text = "Score: %d" % current_score
''',
            "projectile": '''extends Area2D
{comments}
{signals}
@export var speed: float = 500.0
@export var damage: int = 10
@export var lifetime: float = 5.0

var direction: Vector2 = Vector2.RIGHT
var timer: float = 0.0

func _ready() -> void:
\tbody_entered.connect(_on_body_entered)

func _physics_process(delta: float) -> void:
\tposition += direction * speed * delta
\ttimer += delta
\tif timer >= lifetime:
\t\tqueue_free()

func _on_body_entered(body: Node2D) -> void:
\tif body.has_method("take_damage"):
\t\tbody.take_damage(damage)
\t\t{emit_hit}
\tqueue_free()

func set_direction(dir: Vector2) -> void:
\tdirection = dir.normalized()
\trotation = direction.angle()
''',
            "platform": '''extends AnimatableBody2D
{comments}
{signals}
@export var move_speed: float = 100.0
@export var wait_time: float = 1.0
@export var points: Array[Vector2] = []

var current_point: int = 0
var waiting: bool = false
var wait_timer: float = 0.0
var start_position: Vector2

func _ready() -> void:
\tstart_position = global_position
\tif points.is_empty():
\t\tpoints = [Vector2.ZERO, Vector2(100, 0)]

func _physics_process(delta: float) -> void:
\tif waiting:
\t\twait_timer += delta
\t\tif wait_timer >= wait_time:
\t\t\twaiting = false
\t\t\twait_timer = 0.0
\t\t\tcurrent_point = (current_point + 1) % points.size()
\t\treturn
\t
\tvar target := start_position + points[current_point]
\tvar direction := (target - global_position).normalized()
\tvar distance := global_position.distance_to(target)
\t
\tif distance < move_speed * delta:
\t\tglobal_position = target
\t\twaiting = true
\t\t{emit_reached}
\telse:
\t\tglobal_position += direction * move_speed * delta
''',
        }

        template = templates.get(script_type, templates["player"])

        # Add comments
        comments_text = ""
        if comments:
            comments_text = f'''## {script_type.title()} Script
## Generated by Sindri Game Level Agent
## Godot 4.x compatible
'''

        # Add signals
        signals_text = ""
        emit_texts = {
            "emit_jumped": "",
            "emit_damaged": "",
            "emit_died": "",
            "emit_collected": "",
            "emit_score": "",
            "emit_hit": "",
            "emit_reached": "",
        }

        if signals:
            if script_type == "player":
                signals_text = '''signal jumped
signal damaged(amount: int)
signal died
'''
                emit_texts["emit_jumped"] = "jumped.emit()"
                emit_texts["emit_damaged"] = "damaged.emit(amount)"
                emit_texts["emit_died"] = "died.emit()"
            elif script_type == "enemy":
                signals_text = '''signal damaged(amount: int)
signal died
'''
                emit_texts["emit_damaged"] = "damaged.emit(amount)"
                emit_texts["emit_died"] = "died.emit()"
            elif script_type == "item":
                signals_text = '''signal collected(item_name: String, value: int)
'''
                emit_texts["emit_collected"] = "collected.emit(item_name, item_value)"
            elif script_type == "ui":
                signals_text = '''signal score_changed(new_score: int)
'''
                emit_texts["emit_score"] = "score_changed.emit(current_score)"
            elif script_type == "projectile":
                signals_text = '''signal hit(target: Node2D)
'''
                emit_texts["emit_hit"] = "hit.emit(body)"
            elif script_type == "platform":
                signals_text = '''signal point_reached(point_index: int)
'''
                emit_texts["emit_reached"] = "point_reached.emit(current_point)"

        script = template.format(
            comments=comments_text,
            signals=signals_text,
            **emit_texts,
        )

        return script

    def _generate_gdscript_3(self, script_type: str, signals: bool, comments: bool) -> str:
        """Generate Godot 3.x GDScript."""
        templates = {
            "player": '''extends KinematicBody2D
{comments}
{signals}
export var speed: float = 200.0
export var jump_force: float = -400.0
export var max_health: int = 100

var health: int = max_health
var velocity: Vector2 = Vector2.ZERO
var gravity: float = 980.0

func _ready() -> void:
\thealth = max_health

func _physics_process(delta: float) -> void:
\t# Apply gravity
\tif not is_on_floor():
\t\tvelocity.y += gravity * delta
\t
\t# Handle jump
\tif Input.is_action_just_pressed("jump") and is_on_floor():
\t\tvelocity.y = jump_force
\t\t{emit_jumped}
\t
\t# Handle horizontal movement
\tvar direction := Input.get_action_strength("move_right") - Input.get_action_strength("move_left")
\tif direction:
\t\tvelocity.x = direction * speed
\telse:
\t\tvelocity.x = lerp(velocity.x, 0, 0.2)
\t
\tvelocity = move_and_slide(velocity, Vector2.UP)

func take_damage(amount: int) -> void:
\thealth -= amount
\t{emit_damaged}
\tif health <= 0:
\t\tdie()

func die() -> void:
\t{emit_died}
\tqueue_free()
''',
        }

        template = templates.get(script_type, templates["player"])

        comments_text = ""
        if comments:
            comments_text = f'''# {script_type.title()} Script
# Generated by Sindri Game Level Agent
# Godot 3.x compatible
'''

        signals_text = ""
        emit_texts = {"emit_jumped": "", "emit_damaged": "", "emit_died": ""}

        if signals:
            signals_text = '''signal jumped
signal damaged(amount)
signal died
'''
            emit_texts["emit_jumped"] = 'emit_signal("jumped")'
            emit_texts["emit_damaged"] = 'emit_signal("damaged", amount)'
            emit_texts["emit_died"] = 'emit_signal("died")'

        script = template.format(comments=comments_text, signals=signals_text, **emit_texts)
        return script


class GenerateUnityScriptTool(Tool):
    """Generate Unity C# scripts."""

    name = "generate_unity_script"
    description = """Generate Unity C# scripts for game mechanics.

Creates C# scripts for common Unity patterns like player controllers,
enemy AI, item systems, and UI components. Follows Unity best practices.

Use this tool to quickly scaffold Unity game scripts."""

    parameters = {
        "type": "object",
        "properties": {
            "script_type": {
                "type": "string",
                "enum": ["player", "enemy", "item", "ui", "projectile", "platform"],
                "description": "Type of script to generate",
            },
            "namespace": {
                "type": "string",
                "description": "C# namespace (default: Game)",
            },
            "description": {
                "type": "string",
                "description": "Additional description of desired behavior",
            },
            "include_comments": {
                "type": "boolean",
                "description": "Include XML documentation (default: true)",
            },
            "output_file": {
                "type": "string",
                "description": "Optional file path to save the script",
            },
        },
        "required": ["script_type"],
    }

    async def execute(
        self,
        script_type: str,
        namespace: str = "Game",
        description: Optional[str] = None,
        include_comments: bool = True,
        output_file: Optional[str] = None,
    ) -> ToolResult:
        """Generate Unity C# script."""
        try:
            log.info("generating_unity_script", type=script_type, namespace=namespace)

            script = self._generate_csharp(script_type, namespace, include_comments)

            # Save to file if requested
            if output_file:
                path = self._resolve_path(output_file)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(script)

            return ToolResult(
                success=True,
                output=script,
                metadata={
                    "script_type": script_type,
                    "namespace": namespace,
                    "output_file": str(output_file) if output_file else None,
                },
            )

        except Exception as e:
            log.error("unity_script_generation_failed", error=str(e))
            return ToolResult(
                success=False,
                output="",
                error=f"Failed to generate Unity script: {str(e)}",
            )

    def _generate_csharp(self, script_type: str, namespace: str, comments: bool) -> str:
        """Generate Unity C# script."""
        templates = {
            "player": '''using UnityEngine;
using UnityEngine.Events;

namespace {namespace}
{{
{comments}
    public class PlayerController : MonoBehaviour
    {{
        [Header("Movement")]
        [SerializeField] private float moveSpeed = 5f;
        [SerializeField] private float jumpForce = 10f;

        [Header("Stats")]
        [SerializeField] private int maxHealth = 100;

        [Header("Events")]
        public UnityEvent onJump;
        public UnityEvent<int> onDamaged;
        public UnityEvent onDied;

        private Rigidbody2D rb;
        private bool isGrounded;
        private int currentHealth;

        private void Awake()
        {{
            rb = GetComponent<Rigidbody2D>();
            currentHealth = maxHealth;
        }}

        private void Update()
        {{
            // Horizontal movement
            float horizontal = Input.GetAxisRaw("Horizontal");
            rb.velocity = new Vector2(horizontal * moveSpeed, rb.velocity.y);

            // Jump
            if (Input.GetButtonDown("Jump") && isGrounded)
            {{
                rb.velocity = new Vector2(rb.velocity.x, jumpForce);
                onJump?.Invoke();
            }}
        }}

        private void OnCollisionEnter2D(Collision2D collision)
        {{
            if (collision.gameObject.CompareTag("Ground"))
            {{
                isGrounded = true;
            }}
        }}

        private void OnCollisionExit2D(Collision2D collision)
        {{
            if (collision.gameObject.CompareTag("Ground"))
            {{
                isGrounded = false;
            }}
        }}

        public void TakeDamage(int amount)
        {{
            currentHealth -= amount;
            onDamaged?.Invoke(amount);

            if (currentHealth <= 0)
            {{
                Die();
            }}
        }}

        private void Die()
        {{
            onDied?.Invoke();
            Destroy(gameObject);
        }}
    }}
}}
''',
            "enemy": '''using UnityEngine;
using UnityEngine.Events;

namespace {namespace}
{{
{comments}
    public class EnemyController : MonoBehaviour
    {{
        [Header("Stats")]
        [SerializeField] private float moveSpeed = 3f;
        [SerializeField] private int maxHealth = 50;
        [SerializeField] private int damage = 10;
        [SerializeField] private float detectionRange = 5f;

        [Header("Events")]
        public UnityEvent<int> onDamaged;
        public UnityEvent onDied;

        private Transform target;
        private Rigidbody2D rb;
        private int currentHealth;

        private void Awake()
        {{
            rb = GetComponent<Rigidbody2D>();
            currentHealth = maxHealth;
        }}

        private void Update()
        {{
            FindTarget();

            if (target != null)
            {{
                ChaseTarget();
            }}
        }}

        private void FindTarget()
        {{
            GameObject player = GameObject.FindGameObjectWithTag("Player");
            if (player != null)
            {{
                float distance = Vector2.Distance(transform.position, player.transform.position);
                target = distance < detectionRange ? player.transform : null;
            }}
        }}

        private void ChaseTarget()
        {{
            float direction = Mathf.Sign(target.position.x - transform.position.x);
            rb.velocity = new Vector2(direction * moveSpeed, rb.velocity.y);
        }}

        public void TakeDamage(int amount)
        {{
            currentHealth -= amount;
            onDamaged?.Invoke(amount);

            if (currentHealth <= 0)
            {{
                Die();
            }}
        }}

        private void Die()
        {{
            onDied?.Invoke();
            Destroy(gameObject);
        }}

        private void OnCollisionEnter2D(Collision2D collision)
        {{
            if (collision.gameObject.CompareTag("Player"))
            {{
                var player = collision.gameObject.GetComponent<PlayerController>();
                player?.TakeDamage(damage);
            }}
        }}
    }}
}}
''',
            "item": '''using UnityEngine;
using UnityEngine.Events;

namespace {namespace}
{{
{comments}
    public class CollectibleItem : MonoBehaviour
    {{
        [Header("Item Data")]
        [SerializeField] private string itemName = "Item";
        [SerializeField] private int itemValue = 10;
        [SerializeField] private ItemType itemType = ItemType.Consumable;

        [Header("Events")]
        public UnityEvent<string, int> onCollected;

        public enum ItemType
        {{
            Consumable,
            Weapon,
            Armor,
            Key
        }}

        private bool isCollected = false;

        private void OnTriggerEnter2D(Collider2D other)
        {{
            if (isCollected) return;

            if (other.CompareTag("Player"))
            {{
                Collect(other.gameObject);
            }}
        }}

        private void Collect(GameObject collector)
        {{
            isCollected = true;
            onCollected?.Invoke(itemName, itemValue);

            // Optional: Add to inventory
            var inventory = collector.GetComponent<IInventory>();
            inventory?.AddItem(itemName, itemValue, itemType);

            Destroy(gameObject);
        }}
    }}

    public interface IInventory
    {{
        void AddItem(string name, int value, CollectibleItem.ItemType type);
    }}
}}
''',
            "ui": '''using UnityEngine;
using UnityEngine.UI;
using UnityEngine.Events;
using TMPro;

namespace {namespace}
{{
{comments}
    public class GameUI : MonoBehaviour
    {{
        [Header("UI References")]
        [SerializeField] private Slider healthBar;
        [SerializeField] private TextMeshProUGUI scoreText;

        [Header("Events")]
        public UnityEvent<int> onScoreChanged;

        private int currentScore = 0;

        public void SetHealth(int current, int max)
        {{
            if (healthBar != null)
            {{
                healthBar.maxValue = max;
                healthBar.value = current;
            }}
        }}

        public void AddScore(int amount)
        {{
            currentScore += amount;
            UpdateScoreDisplay();
            onScoreChanged?.Invoke(currentScore);
        }}

        private void UpdateScoreDisplay()
        {{
            if (scoreText != null)
            {{
                scoreText.text = $"Score: {{currentScore}}";
            }}
        }}

        public int GetScore() => currentScore;
    }}
}}
''',
            "projectile": '''using UnityEngine;
using UnityEngine.Events;

namespace {namespace}
{{
{comments}
    public class Projectile : MonoBehaviour
    {{
        [Header("Settings")]
        [SerializeField] private float speed = 10f;
        [SerializeField] private int damage = 10;
        [SerializeField] private float lifetime = 5f;

        [Header("Events")]
        public UnityEvent<GameObject> onHit;

        private Vector2 direction = Vector2.right;
        private float timer = 0f;

        private void Update()
        {{
            transform.Translate(direction * speed * Time.deltaTime, Space.World);

            timer += Time.deltaTime;
            if (timer >= lifetime)
            {{
                Destroy(gameObject);
            }}
        }}

        public void SetDirection(Vector2 dir)
        {{
            direction = dir.normalized;
            float angle = Mathf.Atan2(direction.y, direction.x) * Mathf.Rad2Deg;
            transform.rotation = Quaternion.Euler(0, 0, angle);
        }}

        private void OnTriggerEnter2D(Collider2D other)
        {{
            if (other.CompareTag("Enemy"))
            {{
                var enemy = other.GetComponent<EnemyController>();
                enemy?.TakeDamage(damage);
                onHit?.Invoke(other.gameObject);
            }}

            Destroy(gameObject);
        }}
    }}
}}
''',
            "platform": '''using UnityEngine;
using UnityEngine.Events;
using System.Collections.Generic;

namespace {namespace}
{{
{comments}
    public class MovingPlatform : MonoBehaviour
    {{
        [Header("Movement")]
        [SerializeField] private float moveSpeed = 2f;
        [SerializeField] private float waitTime = 1f;
        [SerializeField] private List<Vector2> waypoints = new List<Vector2>();

        [Header("Events")]
        public UnityEvent<int> onWaypointReached;

        private int currentWaypoint = 0;
        private float waitTimer = 0f;
        private bool isWaiting = false;
        private Vector2 startPosition;

        private void Start()
        {{
            startPosition = transform.position;
            if (waypoints.Count == 0)
            {{
                waypoints.Add(Vector2.zero);
                waypoints.Add(new Vector2(3, 0));
            }}
        }}

        private void FixedUpdate()
        {{
            if (isWaiting)
            {{
                waitTimer += Time.fixedDeltaTime;
                if (waitTimer >= waitTime)
                {{
                    isWaiting = false;
                    waitTimer = 0f;
                    currentWaypoint = (currentWaypoint + 1) % waypoints.Count;
                }}
                return;
            }}

            Vector2 targetPosition = startPosition + waypoints[currentWaypoint];
            Vector2 direction = (targetPosition - (Vector2)transform.position).normalized;
            float distance = Vector2.Distance(transform.position, targetPosition);

            if (distance < moveSpeed * Time.fixedDeltaTime)
            {{
                transform.position = targetPosition;
                isWaiting = true;
                onWaypointReached?.Invoke(currentWaypoint);
            }}
            else
            {{
                transform.Translate(direction * moveSpeed * Time.fixedDeltaTime);
            }}
        }}

        private void OnCollisionEnter2D(Collision2D collision)
        {{
            if (collision.gameObject.CompareTag("Player"))
            {{
                collision.transform.SetParent(transform);
            }}
        }}

        private void OnCollisionExit2D(Collision2D collision)
        {{
            if (collision.gameObject.CompareTag("Player"))
            {{
                collision.transform.SetParent(null);
            }}
        }}
    }}
}}
''',
        }

        template = templates.get(script_type, templates["player"])

        comments_text = ""
        if comments:
            class_name = {
                "player": "PlayerController",
                "enemy": "EnemyController",
                "item": "CollectibleItem",
                "ui": "GameUI",
                "projectile": "Projectile",
                "platform": "MovingPlatform",
            }.get(script_type, "GameScript")

            comments_text = f'''    /// <summary>
    /// {class_name} - Generated by Sindri Game Level Agent.
    /// Handles {script_type} behavior and interactions.
    /// </summary>'''

        script = template.format(namespace=namespace, comments=comments_text)
        return script


# =============================================================================
# Exports
# =============================================================================

__all__ = [
    "GenerateTilemapTool",
    "GenerateDungeonTool",
    "BalanceDifficultyTool",
    "GenerateDialogueTool",
    "GenerateItemStatsTool",
    "GenerateGDScriptTool",
    "GenerateUnityScriptTool",
]
