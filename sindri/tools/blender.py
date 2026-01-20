"""Blender Python tools for Sindri.

This module provides tools for generating Blender Python scripts,
creating 3D meshes, applying modifiers, generating materials,
setting up animations, and configuring renders.

Named after Dvalin, the Norse dwarf craftsman who was a master of smithing.
"""

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any, Optional

import structlog

from sindri.tools.base import Tool, ToolResult

log = structlog.get_logger()

# Check for Blender availability
BLENDER_AVAILABLE = shutil.which("blender") is not None


# ============================================================================
# Constants
# ============================================================================

MESH_TYPES = [
    "cube", "sphere", "cylinder", "cone", "torus", "plane",
    "uv_sphere", "ico_sphere", "grid", "monkey", "circle", "custom"
]

MODIFIER_TYPES = [
    "subdivision", "bevel", "solidify", "boolean", "array", "mirror",
    "screw", "displace", "wave", "simple_deform", "decimate", "remesh",
    "smooth", "wireframe", "skin", "cloth", "shrinkwrap", "lattice"
]

ANIMATION_TYPES = [
    "custom", "turntable", "bounce", "orbit", "zoom", "shake", "wave", "fade"
]

INTERPOLATION_TYPES = [
    "LINEAR", "BEZIER", "CONSTANT", "BOUNCE", "ELASTIC", "BACK", "SINE"
]

RENDER_ENGINES = ["cycles", "eevee", "workbench"]

OUTPUT_FORMATS = ["PNG", "JPEG", "EXR", "TIFF", "FFMPEG", "BMP", "OPEN_EXR"]

# Blender versions supported
BLENDER_VERSIONS = ["3.6", "4.0", "4.1", "4.2"]


# ============================================================================
# Helper Functions
# ============================================================================

def _generate_imports(include_bmesh: bool = False, include_mathutils: bool = True) -> str:
    """Generate standard Blender Python imports."""
    imports = ["import bpy"]
    if include_mathutils:
        imports.append("from mathutils import Vector, Matrix, Euler")
    if include_bmesh:
        imports.append("import bmesh")
    imports.append("import math")
    return "\n".join(imports)


def _generate_cleanup_code() -> str:
    """Generate scene cleanup code."""
    return '''
# Clean up the scene
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete()

# Remove orphan data
for mesh in bpy.data.meshes:
    if mesh.users == 0:
        bpy.data.meshes.remove(mesh)
for mat in bpy.data.materials:
    if mat.users == 0:
        bpy.data.materials.remove(mat)
'''


def _format_vector(values: list) -> str:
    """Format a list as a Blender vector/tuple."""
    if not values:
        return "(0, 0, 0)"
    return f"({', '.join(str(v) for v in values)})"


def _format_color(values: list) -> str:
    """Format RGB values as RGBA tuple."""
    if not values:
        return "(1, 1, 1, 1)"
    if len(values) == 3:
        return f"({values[0]}, {values[1]}, {values[2]}, 1)"
    return f"({', '.join(str(v) for v in values)})"


# ============================================================================
# BlenderScriptTool
# ============================================================================

class BlenderScriptTool(Tool):
    """Generate complete Blender Python scripts from text descriptions."""

    name = "blender_script"
    description = """Generate a complete Blender Python script from a text description.

Creates scripts compatible with Blender's Python API (bpy) that can be run
in Blender's scripting environment or via command line with:
  blender --background --python script.py

Features:
- Scene setup and cleanup
- Object creation and manipulation
- Material assignment
- Animation setup
- Render configuration

Examples:
- blender_script(description="Create a simple red cube")
- blender_script(description="Generate a procedural landscape with erosion")
- blender_script(description="Set up a product visualization scene with lighting")
"""

    parameters = {
        "type": "object",
        "properties": {
            "description": {
                "type": "string",
                "description": "Text description of the desired Blender script"
            },
            "include_cleanup": {
                "type": "boolean",
                "description": "Include scene cleanup at script start (default: true)"
            },
            "blender_version": {
                "type": "string",
                "description": "Target Blender version (default: '4.0')",
                "enum": BLENDER_VERSIONS
            },
            "output_file": {
                "type": "string",
                "description": "Optional file path to save the script"
            },
            "execute": {
                "type": "boolean",
                "description": "Execute the script via blender --background (default: false)"
            }
        },
        "required": ["description"]
    }

    # Script templates for common operations
    TEMPLATES = {
        "cube": '''
# Create a cube
bpy.ops.mesh.primitive_cube_add(size=2, location=(0, 0, 0))
cube = bpy.context.active_object
cube.name = "Cube"
''',
        "sphere": '''
# Create a UV sphere
bpy.ops.mesh.primitive_uv_sphere_add(radius=1, segments=32, ring_count=16, location=(0, 0, 0))
sphere = bpy.context.active_object
sphere.name = "Sphere"
''',
        "basic_material": '''
# Create a basic material
mat = bpy.data.materials.new(name="Material")
mat.use_nodes = True
bsdf = mat.node_tree.nodes.get("Principled BSDF")
bsdf.inputs['Base Color'].default_value = (0.8, 0.2, 0.2, 1)
obj.data.materials.append(mat)
''',
        "basic_lighting": '''
# Add a sun light
bpy.ops.object.light_add(type='SUN', location=(5, 5, 10))
sun = bpy.context.active_object
sun.data.energy = 3

# Add ambient lighting
bpy.context.scene.world.use_nodes = True
world_nodes = bpy.context.scene.world.node_tree.nodes
bg = world_nodes.get("Background")
if bg:
    bg.inputs[0].default_value = (0.05, 0.05, 0.1, 1)
    bg.inputs[1].default_value = 0.5
''',
        "basic_camera": '''
# Add a camera
bpy.ops.object.camera_add(location=(7, -7, 5))
camera = bpy.context.active_object
camera.rotation_euler = (1.1, 0, 0.78)
bpy.context.scene.camera = camera
''',
        "render_setup": '''
# Render settings
bpy.context.scene.render.engine = 'CYCLES'
bpy.context.scene.cycles.samples = 128
bpy.context.scene.render.resolution_x = 1920
bpy.context.scene.render.resolution_y = 1080
bpy.context.scene.render.filepath = "/tmp/render.png"
''',
    }

    async def execute(
        self,
        description: str,
        include_cleanup: bool = True,
        blender_version: str = "4.0",
        output_file: Optional[str] = None,
        execute: bool = False,
    ) -> ToolResult:
        """Generate a Blender Python script from description."""
        try:
            # Build the script
            script_parts = []

            # Header comment
            script_parts.append(f'"""Blender Python script - Generated by Sindri')
            script_parts.append(f'Description: {description}')
            script_parts.append(f'Target Blender version: {blender_version}')
            script_parts.append('"""')
            script_parts.append("")

            # Imports
            script_parts.append(_generate_imports(include_bmesh=True, include_mathutils=True))
            script_parts.append("")

            # Scene cleanup
            if include_cleanup:
                script_parts.append(_generate_cleanup_code())
                script_parts.append("")

            # Generate code based on description keywords
            desc_lower = description.lower()

            # Add appropriate templates based on keywords
            if "cube" in desc_lower:
                script_parts.append(self.TEMPLATES["cube"])
            elif "sphere" in desc_lower:
                script_parts.append(self.TEMPLATES["sphere"])
            else:
                # Default: create a cube
                script_parts.append(self.TEMPLATES["cube"])

            # Check for material keywords
            if any(word in desc_lower for word in ["material", "color", "red", "blue", "green", "metal", "glass"]):
                script_parts.append("""
# Create and assign material
mat = bpy.data.materials.new(name="Material")
mat.use_nodes = True
bsdf = mat.node_tree.nodes.get("Principled BSDF")
""")
                # Determine color
                if "red" in desc_lower:
                    script_parts.append("bsdf.inputs['Base Color'].default_value = (0.8, 0.1, 0.1, 1)")
                elif "blue" in desc_lower:
                    script_parts.append("bsdf.inputs['Base Color'].default_value = (0.1, 0.2, 0.8, 1)")
                elif "green" in desc_lower:
                    script_parts.append("bsdf.inputs['Base Color'].default_value = (0.1, 0.6, 0.2, 1)")
                elif "gold" in desc_lower or "metal" in desc_lower:
                    script_parts.append("bsdf.inputs['Base Color'].default_value = (1.0, 0.8, 0.2, 1)")
                    script_parts.append("bsdf.inputs['Metallic'].default_value = 1.0")
                    script_parts.append("bsdf.inputs['Roughness'].default_value = 0.3")
                elif "glass" in desc_lower:
                    script_parts.append("bsdf.inputs['Transmission'].default_value = 1.0")
                    script_parts.append("bsdf.inputs['IOR'].default_value = 1.45")
                    script_parts.append("bsdf.inputs['Roughness'].default_value = 0.0")
                else:
                    script_parts.append("bsdf.inputs['Base Color'].default_value = (0.8, 0.8, 0.8, 1)")

                script_parts.append("""
obj = bpy.context.active_object
if obj and obj.data:
    obj.data.materials.append(mat)
""")

            # Check for lighting keywords
            if any(word in desc_lower for word in ["light", "lighting", "scene", "visualization"]):
                script_parts.append(self.TEMPLATES["basic_lighting"])

            # Check for camera keywords
            if any(word in desc_lower for word in ["camera", "scene", "visualization", "render"]):
                script_parts.append(self.TEMPLATES["basic_camera"])

            # Check for render keywords
            if any(word in desc_lower for word in ["render", "output"]):
                script_parts.append(self.TEMPLATES["render_setup"])

            # Add completion comment
            script_parts.append("")
            script_parts.append("# Script complete")
            script_parts.append("print('Blender script executed successfully')")

            script = "\n".join(script_parts)

            # Save to file if requested
            if output_file:
                out_path = self._resolve_path(output_file)
                out_path.parent.mkdir(parents=True, exist_ok=True)
                out_path.write_text(script)
                log.info("blender_script_saved", path=str(out_path))

            # Execute if requested
            execution_result = None
            if execute:
                if not BLENDER_AVAILABLE:
                    return ToolResult(
                        success=True,
                        output=script,
                        error="Blender not found - script generated but not executed",
                        metadata={"script_generated": True, "executed": False}
                    )

                # Save to temp file for execution
                import tempfile
                with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
                    f.write(script)
                    temp_path = f.name

                try:
                    result = subprocess.run(
                        ["blender", "--background", "--python", temp_path],
                        capture_output=True,
                        text=True,
                        timeout=300
                    )
                    execution_result = {
                        "returncode": result.returncode,
                        "stdout": result.stdout[-2000:] if len(result.stdout) > 2000 else result.stdout,
                        "stderr": result.stderr[-1000:] if len(result.stderr) > 1000 else result.stderr,
                    }
                except subprocess.TimeoutExpired:
                    execution_result = {"error": "Execution timed out after 5 minutes"}
                except Exception as e:
                    execution_result = {"error": str(e)}
                finally:
                    Path(temp_path).unlink(missing_ok=True)

            metadata = {
                "blender_version": blender_version,
                "include_cleanup": include_cleanup,
                "line_count": len(script.splitlines()),
            }
            if output_file:
                metadata["output_file"] = str(out_path)
            if execution_result:
                metadata["execution"] = execution_result

            return ToolResult(
                success=True,
                output=script,
                metadata=metadata
            )

        except Exception as e:
            log.error("blender_script_error", error=str(e))
            return ToolResult(
                success=False,
                output="",
                error=f"Failed to generate Blender script: {e}"
            )


# ============================================================================
# CreateMeshTool
# ============================================================================

class CreateMeshTool(Tool):
    """Generate Blender Python code to create 3D meshes."""

    name = "create_mesh"
    description = """Generate Blender Python code to create a custom 3D mesh.

Creates mesh objects from:
- Primitive definitions (cube, sphere, cylinder, cone, torus, etc.)
- Custom vertex/face data

Examples:
- create_mesh(mesh_type="cube", size=2.0, location=[0, 0, 0])
- create_mesh(mesh_type="torus", major_radius=2, minor_radius=0.5)
- create_mesh(mesh_type="custom", vertices=[[0,0,0],[1,0,0],[0.5,1,0]], faces=[[0,1,2]])
"""

    parameters = {
        "type": "object",
        "properties": {
            "mesh_type": {
                "type": "string",
                "description": "Type of mesh to create",
                "enum": MESH_TYPES
            },
            "name": {
                "type": "string",
                "description": "Name for the mesh object"
            },
            "size": {
                "type": "number",
                "description": "Overall size/scale factor (default: 2.0)"
            },
            "radius": {
                "type": "number",
                "description": "Radius for spheres, cylinders, etc."
            },
            "location": {
                "type": "array",
                "items": {"type": "number"},
                "description": "Location as [x, y, z]"
            },
            "rotation": {
                "type": "array",
                "items": {"type": "number"},
                "description": "Rotation in radians as [x, y, z]"
            },
            "scale": {
                "type": "array",
                "items": {"type": "number"},
                "description": "Scale as [x, y, z]"
            },
            "segments": {
                "type": "integer",
                "description": "Number of segments for curved surfaces"
            },
            "ring_count": {
                "type": "integer",
                "description": "Number of rings for UV spheres"
            },
            "depth": {
                "type": "number",
                "description": "Depth/height for cylinders, cones"
            },
            "major_radius": {
                "type": "number",
                "description": "Major radius for torus"
            },
            "minor_radius": {
                "type": "number",
                "description": "Minor radius for torus"
            },
            "vertices": {
                "type": "array",
                "description": "Custom vertices as [[x,y,z], ...] (for mesh_type='custom')"
            },
            "faces": {
                "type": "array",
                "description": "Custom faces as [[v1,v2,v3,...], ...] (for mesh_type='custom')"
            },
            "output_file": {
                "type": "string",
                "description": "Optional file path to save the script"
            }
        },
        "required": ["mesh_type"]
    }

    async def execute(
        self,
        mesh_type: str,
        name: Optional[str] = None,
        size: float = 2.0,
        radius: Optional[float] = None,
        location: Optional[list] = None,
        rotation: Optional[list] = None,
        scale: Optional[list] = None,
        segments: int = 32,
        ring_count: int = 16,
        depth: float = 2.0,
        major_radius: float = 1.0,
        minor_radius: float = 0.25,
        vertices: Optional[list] = None,
        faces: Optional[list] = None,
        output_file: Optional[str] = None,
    ) -> ToolResult:
        """Generate Blender code for mesh creation."""
        try:
            if mesh_type not in MESH_TYPES:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Invalid mesh_type: {mesh_type}. Valid types: {', '.join(MESH_TYPES)}"
                )

            # Default values
            location = location or [0, 0, 0]
            rotation = rotation or [0, 0, 0]
            scale = scale or [1, 1, 1]
            name = name or mesh_type.capitalize()
            radius = radius or (size / 2)

            code_parts = []

            # Header
            code_parts.append(f"# Create {mesh_type} mesh: {name}")

            # Generate mesh creation code
            if mesh_type == "cube":
                code_parts.append(f"bpy.ops.mesh.primitive_cube_add(size={size}, location={_format_vector(location)})")

            elif mesh_type in ["sphere", "uv_sphere"]:
                code_parts.append(f"bpy.ops.mesh.primitive_uv_sphere_add(radius={radius}, segments={segments}, ring_count={ring_count}, location={_format_vector(location)})")

            elif mesh_type == "ico_sphere":
                subdivisions = min(segments // 8, 6)
                code_parts.append(f"bpy.ops.mesh.primitive_ico_sphere_add(radius={radius}, subdivisions={subdivisions}, location={_format_vector(location)})")

            elif mesh_type == "cylinder":
                code_parts.append(f"bpy.ops.mesh.primitive_cylinder_add(radius={radius}, depth={depth}, vertices={segments}, location={_format_vector(location)})")

            elif mesh_type == "cone":
                code_parts.append(f"bpy.ops.mesh.primitive_cone_add(radius1={radius}, radius2=0, depth={depth}, vertices={segments}, location={_format_vector(location)})")

            elif mesh_type == "torus":
                code_parts.append(f"bpy.ops.mesh.primitive_torus_add(major_radius={major_radius}, minor_radius={minor_radius}, major_segments={segments}, minor_segments={ring_count}, location={_format_vector(location)})")

            elif mesh_type == "plane":
                code_parts.append(f"bpy.ops.mesh.primitive_plane_add(size={size}, location={_format_vector(location)})")

            elif mesh_type == "grid":
                subdivisions = max(2, segments // 4)
                code_parts.append(f"bpy.ops.mesh.primitive_grid_add(x_subdivisions={subdivisions}, y_subdivisions={subdivisions}, size={size}, location={_format_vector(location)})")

            elif mesh_type == "circle":
                code_parts.append(f"bpy.ops.mesh.primitive_circle_add(radius={radius}, vertices={segments}, location={_format_vector(location)})")

            elif mesh_type == "monkey":
                code_parts.append(f"bpy.ops.mesh.primitive_monkey_add(size={size}, location={_format_vector(location)})")

            elif mesh_type == "custom":
                if not vertices or not faces:
                    return ToolResult(
                        success=False,
                        output="",
                        error="Custom mesh requires 'vertices' and 'faces' arrays"
                    )

                code_parts.append("import bmesh")
                code_parts.append("")
                code_parts.append(f"# Create custom mesh")
                code_parts.append(f'mesh = bpy.data.meshes.new("{name}_mesh")')
                code_parts.append(f'obj = bpy.data.objects.new("{name}", mesh)')
                code_parts.append("bpy.context.collection.objects.link(obj)")
                code_parts.append("")
                code_parts.append("# Build mesh with bmesh")
                code_parts.append("bm = bmesh.new()")
                code_parts.append("")
                code_parts.append("# Create vertices")
                code_parts.append(f"vertices = {json.dumps(vertices)}")
                code_parts.append("bm_verts = [bm.verts.new(v) for v in vertices]")
                code_parts.append("bm.verts.ensure_lookup_table()")
                code_parts.append("")
                code_parts.append("# Create faces")
                code_parts.append(f"faces = {json.dumps(faces)}")
                code_parts.append("for face in faces:")
                code_parts.append("    bm.faces.new([bm_verts[i] for i in face])")
                code_parts.append("")
                code_parts.append("bm.to_mesh(mesh)")
                code_parts.append("bm.free()")
                code_parts.append("")
                code_parts.append(f"obj.location = {_format_vector(location)}")

            # For primitive meshes, get the object and set properties
            if mesh_type != "custom":
                code_parts.append(f"obj = bpy.context.active_object")
                code_parts.append(f'obj.name = "{name}"')

                # Apply rotation if specified
                if rotation != [0, 0, 0]:
                    code_parts.append(f"obj.rotation_euler = {_format_vector(rotation)}")

                # Apply scale if not default
                if scale != [1, 1, 1]:
                    code_parts.append(f"obj.scale = {_format_vector(scale)}")

            code = "\n".join(code_parts)

            # Save to file if requested
            if output_file:
                out_path = self._resolve_path(output_file)
                out_path.parent.mkdir(parents=True, exist_ok=True)

                # Wrap in full script
                full_script = _generate_imports(include_bmesh=mesh_type == "custom") + "\n\n" + code
                out_path.write_text(full_script)

            return ToolResult(
                success=True,
                output=code,
                metadata={
                    "mesh_type": mesh_type,
                    "name": name,
                    "location": location,
                    "output_file": str(output_file) if output_file else None,
                }
            )

        except Exception as e:
            log.error("create_mesh_error", error=str(e))
            return ToolResult(
                success=False,
                output="",
                error=f"Failed to generate mesh code: {e}"
            )


# ============================================================================
# ApplyModifierTool
# ============================================================================

class ApplyModifierTool(Tool):
    """Generate Blender Python code to add modifiers to objects."""

    name = "apply_modifier"
    description = """Generate Blender Python code to add modifiers to objects.

Supports common modifiers:
- Subdivision Surface, Bevel, Solidify
- Boolean (union, difference, intersection)
- Array, Mirror, Screw
- Displace, Wave, SimpleDeform
- Decimate, Remesh, Smooth

Examples:
- apply_modifier(modifier_type="subdivision", levels=2)
- apply_modifier(modifier_type="boolean", operation="difference", target_object="Cutter")
- apply_modifier(modifier_type="array", count=5, offset=[2, 0, 0])
"""

    parameters = {
        "type": "object",
        "properties": {
            "modifier_type": {
                "type": "string",
                "description": "Type of modifier to apply",
                "enum": MODIFIER_TYPES
            },
            "object_name": {
                "type": "string",
                "description": "Name of object to modify (default: active object)"
            },
            "levels": {
                "type": "integer",
                "description": "Subdivision/viewport levels (default: 2)"
            },
            "render_levels": {
                "type": "integer",
                "description": "Render subdivision levels (default: 3)"
            },
            "operation": {
                "type": "string",
                "description": "Boolean operation type",
                "enum": ["union", "difference", "intersection"]
            },
            "target_object": {
                "type": "string",
                "description": "Target object name for boolean operations"
            },
            "count": {
                "type": "integer",
                "description": "Array count (default: 3)"
            },
            "offset": {
                "type": "array",
                "items": {"type": "number"},
                "description": "Array relative offset as [x, y, z]"
            },
            "axis": {
                "type": "string",
                "description": "Axis for mirror/screw (X, Y, or Z)",
                "enum": ["X", "Y", "Z"]
            },
            "angle": {
                "type": "number",
                "description": "Angle for screw modifier (in degrees)"
            },
            "width": {
                "type": "number",
                "description": "Width for bevel modifier"
            },
            "thickness": {
                "type": "number",
                "description": "Thickness for solidify modifier"
            },
            "strength": {
                "type": "number",
                "description": "Strength for displace/wave modifiers"
            },
            "apply_modifier": {
                "type": "boolean",
                "description": "Apply modifier permanently (default: false)"
            },
            "output_file": {
                "type": "string",
                "description": "Optional file path to save the script"
            }
        },
        "required": ["modifier_type"]
    }

    async def execute(
        self,
        modifier_type: str,
        object_name: Optional[str] = None,
        levels: int = 2,
        render_levels: int = 3,
        operation: str = "difference",
        target_object: Optional[str] = None,
        count: int = 3,
        offset: Optional[list] = None,
        axis: str = "X",
        angle: float = 360,
        width: float = 0.1,
        thickness: float = 0.1,
        strength: float = 1.0,
        apply_modifier: bool = False,
        output_file: Optional[str] = None,
    ) -> ToolResult:
        """Generate Blender code for modifier application."""
        try:
            if modifier_type not in MODIFIER_TYPES:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Invalid modifier_type: {modifier_type}. Valid types: {', '.join(MODIFIER_TYPES)}"
                )

            offset = offset or [1.5, 0, 0]

            code_parts = []

            # Get the object
            if object_name:
                code_parts.append(f'obj = bpy.data.objects.get("{object_name}")')
                code_parts.append("if obj is None:")
                code_parts.append(f'    raise ValueError("Object \\"{object_name}\\" not found")')
            else:
                code_parts.append("obj = bpy.context.active_object")
                code_parts.append("if obj is None:")
                code_parts.append('    raise ValueError("No active object")')

            code_parts.append("")

            # Map modifier type to Blender type
            blender_type_map = {
                "subdivision": "SUBSURF",
                "bevel": "BEVEL",
                "solidify": "SOLIDIFY",
                "boolean": "BOOLEAN",
                "array": "ARRAY",
                "mirror": "MIRROR",
                "screw": "SCREW",
                "displace": "DISPLACE",
                "wave": "WAVE",
                "simple_deform": "SIMPLE_DEFORM",
                "decimate": "DECIMATE",
                "remesh": "REMESH",
                "smooth": "SMOOTH",
                "wireframe": "WIREFRAME",
                "skin": "SKIN",
                "cloth": "CLOTH",
                "shrinkwrap": "SHRINKWRAP",
                "lattice": "LATTICE",
            }

            blender_type = blender_type_map.get(modifier_type, modifier_type.upper())
            mod_name = modifier_type.capitalize()

            code_parts.append(f'mod = obj.modifiers.new(name="{mod_name}", type="{blender_type}")')

            # Set modifier-specific properties
            if modifier_type == "subdivision":
                code_parts.append(f"mod.levels = {levels}")
                code_parts.append(f"mod.render_levels = {render_levels}")
                code_parts.append("mod.subdivision_type = 'CATMULL_CLARK'")

            elif modifier_type == "bevel":
                code_parts.append(f"mod.width = {width}")
                code_parts.append(f"mod.segments = {levels}")

            elif modifier_type == "solidify":
                code_parts.append(f"mod.thickness = {thickness}")

            elif modifier_type == "boolean":
                if not target_object:
                    return ToolResult(
                        success=False,
                        output="",
                        error="Boolean modifier requires 'target_object' parameter"
                    )
                code_parts.append(f'mod.operation = "{operation.upper()}"')
                code_parts.append(f'mod.object = bpy.data.objects.get("{target_object}")')

            elif modifier_type == "array":
                code_parts.append(f"mod.count = {count}")
                code_parts.append("mod.use_relative_offset = True")
                code_parts.append(f"mod.relative_offset_displace = {_format_vector(offset)}")

            elif modifier_type == "mirror":
                code_parts.append(f"mod.use_axis[0] = {'True' if axis == 'X' else 'False'}")
                code_parts.append(f"mod.use_axis[1] = {'True' if axis == 'Y' else 'False'}")
                code_parts.append(f"mod.use_axis[2] = {'True' if axis == 'Z' else 'False'}")

            elif modifier_type == "screw":
                code_parts.append(f"mod.angle = math.radians({angle})")
                code_parts.append(f'mod.axis = "{axis}"')
                code_parts.append(f"mod.steps = {max(16, int(segments) if 'segments' in locals() else 32)}")

            elif modifier_type == "displace":
                code_parts.append(f"mod.strength = {strength}")

            elif modifier_type == "wave":
                code_parts.append(f"mod.height = {strength}")
                code_parts.append("mod.width = 1.5")

            elif modifier_type == "simple_deform":
                code_parts.append("mod.deform_method = 'TWIST'")
                code_parts.append(f"mod.angle = math.radians({angle})")

            elif modifier_type == "decimate":
                code_parts.append("mod.decimate_type = 'COLLAPSE'")
                code_parts.append(f"mod.ratio = {max(0.1, min(1.0, 1.0 / levels))}")

            elif modifier_type == "remesh":
                code_parts.append("mod.mode = 'VOXEL'")
                code_parts.append(f"mod.voxel_size = {0.1 * levels}")

            elif modifier_type == "smooth":
                code_parts.append(f"mod.iterations = {levels}")

            elif modifier_type == "wireframe":
                code_parts.append(f"mod.thickness = {thickness}")

            # Apply modifier if requested
            if apply_modifier:
                code_parts.append("")
                code_parts.append("# Apply modifier")
                code_parts.append("bpy.context.view_layer.objects.active = obj")
                code_parts.append(f'bpy.ops.object.modifier_apply(modifier="{mod_name}")')

            code = "\n".join(code_parts)

            # Save to file if requested
            if output_file:
                out_path = self._resolve_path(output_file)
                out_path.parent.mkdir(parents=True, exist_ok=True)

                full_script = _generate_imports() + "\n\n" + code
                out_path.write_text(full_script)

            return ToolResult(
                success=True,
                output=code,
                metadata={
                    "modifier_type": modifier_type,
                    "object_name": object_name,
                    "applied": apply_modifier,
                    "output_file": str(output_file) if output_file else None,
                }
            )

        except Exception as e:
            log.error("apply_modifier_error", error=str(e))
            return ToolResult(
                success=False,
                output="",
                error=f"Failed to generate modifier code: {e}"
            )


# ============================================================================
# CreateMaterialTool
# ============================================================================

class CreateMaterialTool(Tool):
    """Generate Blender Python code to create PBR materials and shaders."""

    name = "create_material"
    description = """Generate Blender Python code to create PBR materials and shaders.

Creates Principled BSDF-based materials with:
- Base color, metallic, roughness
- Emission and transparency
- Procedural textures (noise, voronoi)

Examples:
- create_material(name="GoldMetal", base_color=[1, 0.8, 0.2], metallic=1.0, roughness=0.3)
- create_material(name="Glass", transmission=1.0, ior=1.45)
- create_material(name="Procedural", use_noise=True, noise_scale=5.0)
"""

    parameters = {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Material name"
            },
            "base_color": {
                "type": "array",
                "items": {"type": "number"},
                "description": "RGB color as [r, g, b] (0-1 range)"
            },
            "metallic": {
                "type": "number",
                "description": "Metallic value (0-1)"
            },
            "roughness": {
                "type": "number",
                "description": "Roughness value (0-1)"
            },
            "specular": {
                "type": "number",
                "description": "Specular intensity (0-1)"
            },
            "transmission": {
                "type": "number",
                "description": "Transmission for glass-like materials (0-1)"
            },
            "ior": {
                "type": "number",
                "description": "Index of refraction (default: 1.45)"
            },
            "emission_color": {
                "type": "array",
                "items": {"type": "number"},
                "description": "Emission color as [r, g, b]"
            },
            "emission_strength": {
                "type": "number",
                "description": "Emission strength"
            },
            "alpha": {
                "type": "number",
                "description": "Alpha/opacity (0-1)"
            },
            "use_noise": {
                "type": "boolean",
                "description": "Add procedural noise texture"
            },
            "noise_scale": {
                "type": "number",
                "description": "Scale for noise texture (default: 5.0)"
            },
            "assign_to": {
                "type": "string",
                "description": "Object name to assign material to"
            },
            "output_file": {
                "type": "string",
                "description": "Optional file path to save the script"
            }
        },
        "required": ["name"]
    }

    async def execute(
        self,
        name: str,
        base_color: Optional[list] = None,
        metallic: float = 0.0,
        roughness: float = 0.5,
        specular: float = 0.5,
        transmission: float = 0.0,
        ior: float = 1.45,
        emission_color: Optional[list] = None,
        emission_strength: float = 0.0,
        alpha: float = 1.0,
        use_noise: bool = False,
        noise_scale: float = 5.0,
        assign_to: Optional[str] = None,
        output_file: Optional[str] = None,
    ) -> ToolResult:
        """Generate Blender code for material creation."""
        try:
            base_color = base_color or [0.8, 0.8, 0.8]
            emission_color = emission_color or [1.0, 1.0, 1.0]

            code_parts = []

            code_parts.append(f"# Create material: {name}")
            code_parts.append(f'mat = bpy.data.materials.new(name="{name}")')
            code_parts.append("mat.use_nodes = True")
            code_parts.append("nodes = mat.node_tree.nodes")
            code_parts.append("links = mat.node_tree.links")
            code_parts.append("")
            code_parts.append("# Get Principled BSDF node")
            code_parts.append('bsdf = nodes.get("Principled BSDF")')
            code_parts.append("")

            # Set basic properties
            code_parts.append("# Set material properties")
            code_parts.append(f"bsdf.inputs['Base Color'].default_value = {_format_color(base_color)}")
            code_parts.append(f"bsdf.inputs['Metallic'].default_value = {metallic}")
            code_parts.append(f"bsdf.inputs['Roughness'].default_value = {roughness}")

            if specular != 0.5:
                code_parts.append(f"bsdf.inputs['Specular IOR Level'].default_value = {specular}")

            # Transmission for glass
            if transmission > 0:
                code_parts.append(f"bsdf.inputs['Transmission Weight'].default_value = {transmission}")
                code_parts.append(f"bsdf.inputs['IOR'].default_value = {ior}")

            # Emission
            if emission_strength > 0:
                code_parts.append(f"bsdf.inputs['Emission Color'].default_value = {_format_color(emission_color)}")
                code_parts.append(f"bsdf.inputs['Emission Strength'].default_value = {emission_strength}")

            # Alpha
            if alpha < 1.0:
                code_parts.append(f"bsdf.inputs['Alpha'].default_value = {alpha}")
                code_parts.append("mat.blend_method = 'BLEND'")

            # Add noise texture
            if use_noise:
                code_parts.append("")
                code_parts.append("# Add noise texture")
                code_parts.append('noise = nodes.new(type="ShaderNodeTexNoise")')
                code_parts.append(f"noise.inputs['Scale'].default_value = {noise_scale}")
                code_parts.append("noise.location = (-300, 300)")
                code_parts.append("")
                code_parts.append('mapping = nodes.new(type="ShaderNodeMapping")')
                code_parts.append("mapping.location = (-500, 300)")
                code_parts.append("")
                code_parts.append('coord = nodes.new(type="ShaderNodeTexCoord")')
                code_parts.append("coord.location = (-700, 300)")
                code_parts.append("")
                code_parts.append("# Connect nodes")
                code_parts.append('links.new(coord.outputs["Generated"], mapping.inputs["Vector"])')
                code_parts.append('links.new(mapping.outputs["Vector"], noise.inputs["Vector"])')
                code_parts.append("")
                code_parts.append("# Mix noise with base color")
                code_parts.append('mix = nodes.new(type="ShaderNodeMixRGB")')
                code_parts.append("mix.location = (-100, 200)")
                code_parts.append(f"mix.inputs[1].default_value = {_format_color(base_color)}")
                code_parts.append(f"mix.inputs[2].default_value = {_format_color([c * 0.7 for c in base_color])}")
                code_parts.append('links.new(noise.outputs["Fac"], mix.inputs["Fac"])')
                code_parts.append('links.new(mix.outputs["Color"], bsdf.inputs["Base Color"])')

            # Assign to object
            if assign_to:
                code_parts.append("")
                code_parts.append(f"# Assign to object: {assign_to}")
                code_parts.append(f'obj = bpy.data.objects.get("{assign_to}")')
                code_parts.append("if obj and obj.data:")
                code_parts.append("    if obj.data.materials:")
                code_parts.append("        obj.data.materials[0] = mat")
                code_parts.append("    else:")
                code_parts.append("        obj.data.materials.append(mat)")

            code = "\n".join(code_parts)

            # Save to file if requested
            if output_file:
                out_path = self._resolve_path(output_file)
                out_path.parent.mkdir(parents=True, exist_ok=True)

                full_script = _generate_imports() + "\n\n" + code
                out_path.write_text(full_script)

            return ToolResult(
                success=True,
                output=code,
                metadata={
                    "name": name,
                    "metallic": metallic,
                    "roughness": roughness,
                    "transmission": transmission,
                    "use_noise": use_noise,
                    "assign_to": assign_to,
                    "output_file": str(output_file) if output_file else None,
                }
            )

        except Exception as e:
            log.error("create_material_error", error=str(e))
            return ToolResult(
                success=False,
                output="",
                error=f"Failed to generate material code: {e}"
            )


# ============================================================================
# SetupAnimationTool
# ============================================================================

class SetupAnimationTool(Tool):
    """Generate Blender Python code to set up keyframe animations."""

    name = "setup_animation"
    description = """Generate Blender Python code to set up keyframe animations.

Creates animations for:
- Object transforms (location, rotation, scale)
- Preset animations (turntable, bounce, orbit)

Examples:
- setup_animation(object_name="Cube", animation_type="turntable", end_frame=120)
- setup_animation(animation_type="bounce", height=3.0)
- setup_animation(property="location", keyframes=[{"frame": 1, "value": [0,0,0]}, {"frame": 60, "value": [5,0,0]}])
"""

    parameters = {
        "type": "object",
        "properties": {
            "object_name": {
                "type": "string",
                "description": "Object to animate (default: active object)"
            },
            "animation_type": {
                "type": "string",
                "description": "Preset animation type",
                "enum": ANIMATION_TYPES
            },
            "property": {
                "type": "string",
                "description": "Property to animate",
                "enum": ["location", "rotation_euler", "scale"]
            },
            "keyframes": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "frame": {"type": "integer"},
                        "value": {"type": "array"}
                    }
                },
                "description": "Keyframe data as [{frame, value}, ...]"
            },
            "start_frame": {
                "type": "integer",
                "description": "Animation start frame (default: 1)"
            },
            "end_frame": {
                "type": "integer",
                "description": "Animation end frame (default: 120)"
            },
            "interpolation": {
                "type": "string",
                "description": "Keyframe interpolation type",
                "enum": INTERPOLATION_TYPES
            },
            "height": {
                "type": "number",
                "description": "Height for bounce animation"
            },
            "amplitude": {
                "type": "number",
                "description": "Amplitude for wave/shake animation"
            },
            "cycles": {
                "type": "integer",
                "description": "Number of cycles for repeating animations"
            },
            "output_file": {
                "type": "string",
                "description": "Optional file path to save the script"
            }
        },
        "required": []
    }

    async def execute(
        self,
        object_name: Optional[str] = None,
        animation_type: str = "custom",
        property: str = "location",
        keyframes: Optional[list] = None,
        start_frame: int = 1,
        end_frame: int = 120,
        interpolation: str = "BEZIER",
        height: float = 2.0,
        amplitude: float = 0.5,
        cycles: int = 2,
        output_file: Optional[str] = None,
    ) -> ToolResult:
        """Generate Blender code for animation setup."""
        try:
            code_parts = []

            # Get the object
            if object_name:
                code_parts.append(f'obj = bpy.data.objects.get("{object_name}")')
                code_parts.append("if obj is None:")
                code_parts.append(f'    raise ValueError("Object \\"{object_name}\\" not found")')
            else:
                code_parts.append("obj = bpy.context.active_object")
                code_parts.append("if obj is None:")
                code_parts.append('    raise ValueError("No active object")')

            code_parts.append("")
            code_parts.append("# Set frame range")
            code_parts.append(f"bpy.context.scene.frame_start = {start_frame}")
            code_parts.append(f"bpy.context.scene.frame_end = {end_frame}")
            code_parts.append("")

            # Generate animation based on type
            if animation_type == "turntable":
                code_parts.append("# Turntable animation (360 degree rotation)")
                code_parts.append(f"obj.rotation_euler = (0, 0, 0)")
                code_parts.append(f'obj.keyframe_insert(data_path="rotation_euler", frame={start_frame})')
                code_parts.append(f"obj.rotation_euler = (0, 0, math.radians(360))")
                code_parts.append(f'obj.keyframe_insert(data_path="rotation_euler", frame={end_frame})')

            elif animation_type == "bounce":
                code_parts.append("# Bounce animation")
                code_parts.append(f"initial_z = obj.location.z")
                frames_per_cycle = (end_frame - start_frame) // cycles

                for i in range(cycles + 1):
                    frame = start_frame + i * frames_per_cycle
                    if i % 2 == 0:
                        code_parts.append(f"obj.location.z = initial_z")
                    else:
                        code_parts.append(f"obj.location.z = initial_z + {height}")
                    code_parts.append(f'obj.keyframe_insert(data_path="location", index=2, frame={frame})')

            elif animation_type == "orbit":
                code_parts.append("# Orbit animation around origin")
                code_parts.append("import math")
                code_parts.append("radius = math.sqrt(obj.location.x**2 + obj.location.y**2)")
                code_parts.append("if radius == 0: radius = 3")
                code_parts.append("")
                steps = min(24, end_frame - start_frame)
                code_parts.append(f"for i in range({steps + 1}):")
                code_parts.append(f"    frame = {start_frame} + int(i * {(end_frame - start_frame) / steps})")
                code_parts.append(f"    angle = (i / {steps}) * 2 * math.pi")
                code_parts.append("    obj.location.x = radius * math.cos(angle)")
                code_parts.append("    obj.location.y = radius * math.sin(angle)")
                code_parts.append('    obj.keyframe_insert(data_path="location", frame=frame)')

            elif animation_type == "zoom":
                code_parts.append("# Zoom animation (scale)")
                code_parts.append(f"obj.scale = (0.1, 0.1, 0.1)")
                code_parts.append(f'obj.keyframe_insert(data_path="scale", frame={start_frame})')
                code_parts.append(f"obj.scale = (1, 1, 1)")
                code_parts.append(f'obj.keyframe_insert(data_path="scale", frame={end_frame})')

            elif animation_type == "shake":
                code_parts.append("# Shake animation")
                code_parts.append(f"initial_loc = obj.location.copy()")
                frames_per_shake = max(2, (end_frame - start_frame) // (cycles * 4))

                for i in range(cycles * 4 + 1):
                    frame = start_frame + i * frames_per_shake
                    if frame > end_frame:
                        break
                    offset = amplitude if i % 2 == 1 else -amplitude if i % 4 == 2 else 0
                    code_parts.append(f"obj.location.x = initial_loc.x + {offset}")
                    code_parts.append(f'obj.keyframe_insert(data_path="location", index=0, frame={frame})')

            elif animation_type == "wave":
                code_parts.append("# Wave animation (vertical oscillation)")
                code_parts.append(f"initial_z = obj.location.z")
                code_parts.append(f"for i in range({end_frame - start_frame + 1}):")
                code_parts.append(f"    frame = {start_frame} + i")
                code_parts.append(f"    obj.location.z = initial_z + {amplitude} * math.sin(i * {cycles} * 2 * math.pi / {end_frame - start_frame})")
                code_parts.append('    obj.keyframe_insert(data_path="location", index=2, frame=frame)')

            elif animation_type == "fade":
                code_parts.append("# Fade animation (requires material with alpha)")
                code_parts.append("if obj.data and obj.data.materials:")
                code_parts.append("    mat = obj.data.materials[0]")
                code_parts.append("    if mat.use_nodes:")
                code_parts.append('        bsdf = mat.node_tree.nodes.get("Principled BSDF")')
                code_parts.append("        if bsdf:")
                code_parts.append("            bsdf.inputs['Alpha'].default_value = 0")
                code_parts.append(f'            bsdf.inputs["Alpha"].keyframe_insert(data_path="default_value", frame={start_frame})')
                code_parts.append("            bsdf.inputs['Alpha'].default_value = 1")
                code_parts.append(f'            bsdf.inputs["Alpha"].keyframe_insert(data_path="default_value", frame={end_frame})')

            elif animation_type == "custom" and keyframes:
                code_parts.append(f"# Custom keyframe animation on {property}")
                for kf in keyframes:
                    frame = kf.get("frame", 1)
                    value = kf.get("value", [0, 0, 0])
                    code_parts.append(f"obj.{property} = {_format_vector(value)}")
                    code_parts.append(f'obj.keyframe_insert(data_path="{property}", frame={frame})')

            else:
                # Default: simple location animation
                code_parts.append(f"# Simple {property} animation")
                code_parts.append(f'obj.keyframe_insert(data_path="{property}", frame={start_frame})')
                if property == "location":
                    code_parts.append(f"obj.location.x += 5")
                elif property == "rotation_euler":
                    code_parts.append(f"obj.rotation_euler.z += math.radians(90)")
                elif property == "scale":
                    code_parts.append(f"obj.scale = (2, 2, 2)")
                code_parts.append(f'obj.keyframe_insert(data_path="{property}", frame={end_frame})')

            # Set interpolation
            code_parts.append("")
            code_parts.append(f"# Set interpolation to {interpolation}")
            code_parts.append("if obj.animation_data and obj.animation_data.action:")
            code_parts.append("    for fcurve in obj.animation_data.action.fcurves:")
            code_parts.append("        for keyframe in fcurve.keyframe_points:")
            code_parts.append(f'            keyframe.interpolation = "{interpolation}"')

            code = "\n".join(code_parts)

            # Save to file if requested
            if output_file:
                out_path = self._resolve_path(output_file)
                out_path.parent.mkdir(parents=True, exist_ok=True)

                full_script = _generate_imports() + "\n\n" + code
                out_path.write_text(full_script)

            return ToolResult(
                success=True,
                output=code,
                metadata={
                    "animation_type": animation_type,
                    "object_name": object_name,
                    "start_frame": start_frame,
                    "end_frame": end_frame,
                    "interpolation": interpolation,
                    "output_file": str(output_file) if output_file else None,
                }
            )

        except Exception as e:
            log.error("setup_animation_error", error=str(e))
            return ToolResult(
                success=False,
                output="",
                error=f"Failed to generate animation code: {e}"
            )


# ============================================================================
# RenderSceneTool
# ============================================================================

class RenderSceneTool(Tool):
    """Generate Blender Python code to configure and render scenes."""

    name = "render_scene"
    description = """Generate Blender Python code to configure and render scenes.

Supports:
- Still image renders (PNG, JPEG, EXR)
- Animation renders (MP4, image sequences)
- Render engine selection (Cycles, Eevee)
- Resolution, samples, and quality settings

Examples:
- render_scene(output_path="render.png", engine="cycles", samples=128)
- render_scene(output_path="animation/", render_animation=True, fps=30)
- render_scene(resolution=[1920, 1080], engine="eevee", samples=64)
"""

    parameters = {
        "type": "object",
        "properties": {
            "output_path": {
                "type": "string",
                "description": "Output file path for render"
            },
            "engine": {
                "type": "string",
                "description": "Render engine",
                "enum": RENDER_ENGINES
            },
            "resolution": {
                "type": "array",
                "items": {"type": "integer"},
                "description": "Resolution as [width, height]"
            },
            "samples": {
                "type": "integer",
                "description": "Number of render samples"
            },
            "render_animation": {
                "type": "boolean",
                "description": "Render animation instead of single frame"
            },
            "fps": {
                "type": "integer",
                "description": "Frames per second for animation"
            },
            "format": {
                "type": "string",
                "description": "Output format",
                "enum": OUTPUT_FORMATS
            },
            "transparent": {
                "type": "boolean",
                "description": "Render with transparent background"
            },
            "use_gpu": {
                "type": "boolean",
                "description": "Use GPU rendering (default: true)"
            },
            "frame": {
                "type": "integer",
                "description": "Specific frame to render (for still images)"
            },
            "execute": {
                "type": "boolean",
                "description": "Execute the render via blender --background"
            },
            "blend_file": {
                "type": "string",
                "description": "Input .blend file to render"
            },
            "output_file": {
                "type": "string",
                "description": "Optional file path to save the script"
            }
        },
        "required": ["output_path"]
    }

    async def execute(
        self,
        output_path: str,
        engine: str = "cycles",
        resolution: Optional[list] = None,
        samples: int = 128,
        render_animation: bool = False,
        fps: int = 24,
        format: str = "PNG",
        transparent: bool = False,
        use_gpu: bool = True,
        frame: int = 1,
        execute: bool = False,
        blend_file: Optional[str] = None,
        output_file: Optional[str] = None,
    ) -> ToolResult:
        """Generate Blender code for render configuration."""
        try:
            resolution = resolution or [1920, 1080]

            code_parts = []

            code_parts.append("# Render configuration")
            code_parts.append("")

            # Set render engine
            engine_map = {
                "cycles": "CYCLES",
                "eevee": "BLENDER_EEVEE_NEXT",  # Blender 4.x
                "workbench": "BLENDER_WORKBENCH",
            }
            blender_engine = engine_map.get(engine, "CYCLES")

            code_parts.append(f'bpy.context.scene.render.engine = "{blender_engine}"')
            code_parts.append("")

            # Engine-specific settings
            if engine == "cycles":
                code_parts.append("# Cycles settings")
                code_parts.append(f"bpy.context.scene.cycles.samples = {samples}")
                if use_gpu:
                    code_parts.append("bpy.context.scene.cycles.device = 'GPU'")
                    code_parts.append("")
                    code_parts.append("# Enable GPU compute")
                    code_parts.append("prefs = bpy.context.preferences.addons['cycles'].preferences")
                    code_parts.append("prefs.compute_device_type = 'HIP'  # AMD GPU")
                    code_parts.append("for device in prefs.devices:")
                    code_parts.append("    device.use = True")
            elif engine == "eevee":
                code_parts.append("# Eevee settings")
                code_parts.append(f"bpy.context.scene.eevee.taa_render_samples = {samples}")

            code_parts.append("")

            # Resolution
            code_parts.append("# Resolution")
            code_parts.append(f"bpy.context.scene.render.resolution_x = {resolution[0]}")
            code_parts.append(f"bpy.context.scene.render.resolution_y = {resolution[1]}")
            code_parts.append("bpy.context.scene.render.resolution_percentage = 100")
            code_parts.append("")

            # Output settings
            code_parts.append("# Output settings")
            code_parts.append(f'bpy.context.scene.render.filepath = "{output_path}"')

            # Format
            format_map = {
                "PNG": "PNG",
                "JPEG": "JPEG",
                "EXR": "OPEN_EXR",
                "TIFF": "TIFF",
                "BMP": "BMP",
                "FFMPEG": "FFMPEG",
                "OPEN_EXR": "OPEN_EXR",
            }
            blender_format = format_map.get(format, "PNG")
            code_parts.append(f'bpy.context.scene.render.image_settings.file_format = "{blender_format}"')

            # Transparent background
            if transparent:
                code_parts.append("")
                code_parts.append("# Transparent background")
                code_parts.append("bpy.context.scene.render.film_transparent = True")
                if format in ["PNG", "TIFF", "EXR", "OPEN_EXR"]:
                    code_parts.append("bpy.context.scene.render.image_settings.color_mode = 'RGBA'")

            # Animation settings
            if render_animation:
                code_parts.append("")
                code_parts.append("# Animation settings")
                code_parts.append(f"bpy.context.scene.render.fps = {fps}")
                if format == "FFMPEG":
                    code_parts.append("bpy.context.scene.render.ffmpeg.format = 'MPEG4'")
                    code_parts.append("bpy.context.scene.render.ffmpeg.codec = 'H264'")
                    code_parts.append("bpy.context.scene.render.ffmpeg.constant_rate_factor = 'MEDIUM'")

            code_parts.append("")

            # Render command
            if render_animation:
                code_parts.append("# Render animation")
                code_parts.append("bpy.ops.render.render(animation=True)")
            else:
                code_parts.append(f"# Render frame {frame}")
                code_parts.append(f"bpy.context.scene.frame_set({frame})")
                code_parts.append("bpy.ops.render.render(write_still=True)")

            code_parts.append("")
            code_parts.append(f'print("Render saved to: {output_path}")')

            code = "\n".join(code_parts)

            # Save script to file if requested
            if output_file:
                out_path = self._resolve_path(output_file)
                out_path.parent.mkdir(parents=True, exist_ok=True)

                full_script = _generate_imports() + "\n\n" + code
                out_path.write_text(full_script)

            # Execute if requested
            execution_result = None
            if execute:
                if not BLENDER_AVAILABLE:
                    return ToolResult(
                        success=True,
                        output=code,
                        error="Blender not found - script generated but not executed",
                        metadata={"script_generated": True, "executed": False}
                    )

                if not blend_file:
                    return ToolResult(
                        success=True,
                        output=code,
                        error="No blend_file provided - cannot execute render",
                        metadata={"script_generated": True, "executed": False}
                    )

                # Save to temp file for execution
                import tempfile
                full_script = _generate_imports() + "\n\n" + code
                with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
                    f.write(full_script)
                    temp_path = f.name

                try:
                    result = subprocess.run(
                        ["blender", "--background", blend_file, "--python", temp_path],
                        capture_output=True,
                        text=True,
                        timeout=3600  # 1 hour timeout for renders
                    )
                    execution_result = {
                        "returncode": result.returncode,
                        "stdout": result.stdout[-2000:] if len(result.stdout) > 2000 else result.stdout,
                        "stderr": result.stderr[-1000:] if len(result.stderr) > 1000 else result.stderr,
                    }
                except subprocess.TimeoutExpired:
                    execution_result = {"error": "Render timed out after 1 hour"}
                except Exception as e:
                    execution_result = {"error": str(e)}
                finally:
                    Path(temp_path).unlink(missing_ok=True)

            metadata = {
                "engine": engine,
                "resolution": resolution,
                "samples": samples,
                "format": format,
                "render_animation": render_animation,
                "transparent": transparent,
                "output_path": output_path,
            }
            if output_file:
                metadata["script_file"] = str(output_file)
            if execution_result:
                metadata["execution"] = execution_result

            return ToolResult(
                success=True,
                output=code,
                metadata=metadata
            )

        except Exception as e:
            log.error("render_scene_error", error=str(e))
            return ToolResult(
                success=False,
                output="",
                error=f"Failed to generate render code: {e}"
            )
