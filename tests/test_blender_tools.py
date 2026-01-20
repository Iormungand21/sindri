"""Tests for Blender Python tools.

This module tests the Blender Python tools for the Dvalin agent:
- BlenderScriptTool
- CreateMeshTool
- ApplyModifierTool
- CreateMaterialTool
- SetupAnimationTool
- RenderSceneTool
"""

import json
import os
import tempfile
from pathlib import Path

import pytest

from sindri.tools.blender import (
    BLENDER_AVAILABLE,
    MESH_TYPES,
    MODIFIER_TYPES,
    ANIMATION_TYPES,
    RENDER_ENGINES,
    OUTPUT_FORMATS,
    BlenderScriptTool,
    CreateMeshTool,
    ApplyModifierTool,
    CreateMaterialTool,
    SetupAnimationTool,
    RenderSceneTool,
)


# ============================================================================
# Constants Tests
# ============================================================================


class TestBlenderConstants:
    """Test Blender constants are properly defined."""

    def test_mesh_types_defined(self):
        """Test that expected mesh types are defined."""
        expected = ["cube", "sphere", "cylinder", "torus", "plane", "custom"]
        for mesh_type in expected:
            assert mesh_type in MESH_TYPES

    def test_modifier_types_defined(self):
        """Test that expected modifier types are defined."""
        expected = ["subdivision", "boolean", "array", "mirror", "bevel", "solidify"]
        for mod_type in expected:
            assert mod_type in MODIFIER_TYPES

    def test_animation_types_defined(self):
        """Test that expected animation types are defined."""
        expected = ["turntable", "bounce", "orbit", "custom"]
        for anim_type in expected:
            assert anim_type in ANIMATION_TYPES

    def test_render_engines_defined(self):
        """Test that render engines are defined."""
        expected = ["cycles", "eevee", "workbench"]
        for engine in expected:
            assert engine in RENDER_ENGINES

    def test_output_formats_defined(self):
        """Test that output formats are defined."""
        expected = ["PNG", "JPEG", "EXR", "FFMPEG"]
        for fmt in expected:
            assert fmt in OUTPUT_FORMATS


# ============================================================================
# BlenderScriptTool Tests
# ============================================================================


class TestBlenderScriptTool:
    """Test BlenderScriptTool."""

    @pytest.fixture
    def tool(self):
        """Create a BlenderScriptTool instance."""
        return BlenderScriptTool()

    @pytest.mark.asyncio
    async def test_generate_basic_script(self, tool):
        """Test basic script generation."""
        result = await tool.execute(
            description="Create a simple cube",
        )
        assert result.success
        assert "import bpy" in result.output
        assert "cube" in result.output.lower()

    @pytest.mark.asyncio
    async def test_script_includes_imports(self, tool):
        """Test that generated scripts include required imports."""
        result = await tool.execute(
            description="Create a sphere",
        )
        assert result.success
        assert "import bpy" in result.output
        assert "import math" in result.output

    @pytest.mark.asyncio
    async def test_script_with_cleanup(self, tool):
        """Test script generation with cleanup code."""
        result = await tool.execute(
            description="Create a cube",
            include_cleanup=True,
        )
        assert result.success
        assert "select_all" in result.output
        assert "delete" in result.output

    @pytest.mark.asyncio
    async def test_script_without_cleanup(self, tool):
        """Test script generation without cleanup code."""
        result = await tool.execute(
            description="Create a cube",
            include_cleanup=False,
        )
        assert result.success
        # Should still have cube creation but not cleanup
        assert "cube" in result.output.lower()

    @pytest.mark.asyncio
    async def test_script_with_material_keywords(self, tool):
        """Test script with material-related keywords."""
        result = await tool.execute(
            description="Create a red cube with material",
        )
        assert result.success
        assert "materials" in result.output.lower() or "material" in result.output.lower()

    @pytest.mark.asyncio
    async def test_script_with_lighting(self, tool):
        """Test script with lighting keywords."""
        result = await tool.execute(
            description="Create a scene with lighting",
        )
        assert result.success
        assert "light" in result.output.lower()

    @pytest.mark.asyncio
    async def test_script_save_to_file(self, tool):
        """Test saving script to file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_file = os.path.join(tmpdir, "script.py")
            result = await tool.execute(
                description="Create a cube",
                output_file=output_file,
            )
            assert result.success
            assert os.path.exists(output_file)
            content = Path(output_file).read_text()
            assert "import bpy" in content

    @pytest.mark.asyncio
    async def test_script_metadata(self, tool):
        """Test that metadata is returned correctly."""
        result = await tool.execute(
            description="Create a sphere",
            blender_version="4.0",
        )
        assert result.success
        assert result.metadata["blender_version"] == "4.0"
        assert "line_count" in result.metadata


# ============================================================================
# CreateMeshTool Tests
# ============================================================================


class TestCreateMeshTool:
    """Test CreateMeshTool."""

    @pytest.fixture
    def tool(self):
        """Create a CreateMeshTool instance."""
        return CreateMeshTool()

    @pytest.mark.asyncio
    async def test_create_cube(self, tool):
        """Test cube mesh creation."""
        result = await tool.execute(
            mesh_type="cube",
            size=2.0,
        )
        assert result.success
        assert "primitive_cube_add" in result.output
        assert result.metadata["mesh_type"] == "cube"

    @pytest.mark.asyncio
    async def test_create_sphere(self, tool):
        """Test sphere mesh creation."""
        result = await tool.execute(
            mesh_type="sphere",
            radius=1.0,
            segments=32,
        )
        assert result.success
        assert "primitive_uv_sphere_add" in result.output

    @pytest.mark.asyncio
    async def test_create_cylinder(self, tool):
        """Test cylinder mesh creation."""
        result = await tool.execute(
            mesh_type="cylinder",
            radius=1.0,
            depth=3.0,
        )
        assert result.success
        assert "primitive_cylinder_add" in result.output

    @pytest.mark.asyncio
    async def test_create_torus(self, tool):
        """Test torus mesh creation."""
        result = await tool.execute(
            mesh_type="torus",
            major_radius=2.0,
            minor_radius=0.5,
        )
        assert result.success
        assert "primitive_torus_add" in result.output

    @pytest.mark.asyncio
    async def test_create_plane(self, tool):
        """Test plane mesh creation."""
        result = await tool.execute(
            mesh_type="plane",
            size=4.0,
        )
        assert result.success
        assert "primitive_plane_add" in result.output

    @pytest.mark.asyncio
    async def test_create_monkey(self, tool):
        """Test monkey (Suzanne) mesh creation."""
        result = await tool.execute(
            mesh_type="monkey",
        )
        assert result.success
        assert "primitive_monkey_add" in result.output

    @pytest.mark.asyncio
    async def test_create_custom_mesh(self, tool):
        """Test custom mesh creation with vertices and faces."""
        vertices = [[0, 0, 0], [1, 0, 0], [0.5, 1, 0]]
        faces = [[0, 1, 2]]
        result = await tool.execute(
            mesh_type="custom",
            vertices=vertices,
            faces=faces,
        )
        assert result.success
        assert "bmesh" in result.output
        assert "bm.verts.new" in result.output

    @pytest.mark.asyncio
    async def test_create_custom_mesh_requires_data(self, tool):
        """Test that custom mesh requires vertices and faces."""
        result = await tool.execute(
            mesh_type="custom",
        )
        assert not result.success
        assert "vertices" in result.error.lower()

    @pytest.mark.asyncio
    async def test_mesh_with_location(self, tool):
        """Test mesh creation with location."""
        result = await tool.execute(
            mesh_type="cube",
            location=[1, 2, 3],
        )
        assert result.success
        assert "(1, 2, 3)" in result.output

    @pytest.mark.asyncio
    async def test_mesh_with_rotation(self, tool):
        """Test mesh creation with rotation."""
        result = await tool.execute(
            mesh_type="cube",
            rotation=[0, 0, 0.785],  # ~45 degrees
        )
        assert result.success
        assert "rotation_euler" in result.output

    @pytest.mark.asyncio
    async def test_mesh_with_name(self, tool):
        """Test mesh creation with custom name."""
        result = await tool.execute(
            mesh_type="cube",
            name="MyCube",
        )
        assert result.success
        assert "MyCube" in result.output

    @pytest.mark.asyncio
    async def test_invalid_mesh_type(self, tool):
        """Test error handling for invalid mesh type."""
        result = await tool.execute(
            mesh_type="invalid_type",
        )
        assert not result.success
        assert "invalid" in result.error.lower()

    @pytest.mark.asyncio
    async def test_mesh_save_to_file(self, tool):
        """Test saving mesh code to file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_file = os.path.join(tmpdir, "mesh.py")
            result = await tool.execute(
                mesh_type="cube",
                output_file=output_file,
            )
            assert result.success
            assert os.path.exists(output_file)


# ============================================================================
# ApplyModifierTool Tests
# ============================================================================


class TestApplyModifierTool:
    """Test ApplyModifierTool."""

    @pytest.fixture
    def tool(self):
        """Create an ApplyModifierTool instance."""
        return ApplyModifierTool()

    @pytest.mark.asyncio
    async def test_subdivision_modifier(self, tool):
        """Test subdivision modifier."""
        result = await tool.execute(
            modifier_type="subdivision",
            levels=2,
            render_levels=3,
        )
        assert result.success
        assert "SUBSURF" in result.output
        assert "levels = 2" in result.output

    @pytest.mark.asyncio
    async def test_bevel_modifier(self, tool):
        """Test bevel modifier."""
        result = await tool.execute(
            modifier_type="bevel",
            width=0.1,
            levels=3,
        )
        assert result.success
        assert "BEVEL" in result.output
        assert "width" in result.output

    @pytest.mark.asyncio
    async def test_solidify_modifier(self, tool):
        """Test solidify modifier."""
        result = await tool.execute(
            modifier_type="solidify",
            thickness=0.1,
        )
        assert result.success
        assert "SOLIDIFY" in result.output
        assert "thickness" in result.output

    @pytest.mark.asyncio
    async def test_boolean_modifier(self, tool):
        """Test boolean modifier."""
        result = await tool.execute(
            modifier_type="boolean",
            operation="difference",
            target_object="Cutter",
        )
        assert result.success
        assert "BOOLEAN" in result.output
        assert "DIFFERENCE" in result.output

    @pytest.mark.asyncio
    async def test_boolean_requires_target(self, tool):
        """Test that boolean modifier requires target object."""
        result = await tool.execute(
            modifier_type="boolean",
            operation="difference",
        )
        assert not result.success
        assert "target_object" in result.error.lower()

    @pytest.mark.asyncio
    async def test_array_modifier(self, tool):
        """Test array modifier."""
        result = await tool.execute(
            modifier_type="array",
            count=5,
            offset=[2, 0, 0],
        )
        assert result.success
        assert "ARRAY" in result.output
        assert "count = 5" in result.output

    @pytest.mark.asyncio
    async def test_mirror_modifier(self, tool):
        """Test mirror modifier."""
        result = await tool.execute(
            modifier_type="mirror",
            axis="X",
        )
        assert result.success
        assert "MIRROR" in result.output
        assert "use_axis" in result.output

    @pytest.mark.asyncio
    async def test_modifier_with_object_name(self, tool):
        """Test modifier with specific object name."""
        result = await tool.execute(
            modifier_type="subdivision",
            object_name="MyCube",
        )
        assert result.success
        assert "MyCube" in result.output

    @pytest.mark.asyncio
    async def test_apply_modifier_flag(self, tool):
        """Test apply modifier flag."""
        result = await tool.execute(
            modifier_type="subdivision",
            apply_modifier=True,
        )
        assert result.success
        assert "modifier_apply" in result.output

    @pytest.mark.asyncio
    async def test_invalid_modifier_type(self, tool):
        """Test error handling for invalid modifier type."""
        result = await tool.execute(
            modifier_type="invalid_modifier",
        )
        assert not result.success
        assert "invalid" in result.error.lower()


# ============================================================================
# CreateMaterialTool Tests
# ============================================================================


class TestCreateMaterialTool:
    """Test CreateMaterialTool."""

    @pytest.fixture
    def tool(self):
        """Create a CreateMaterialTool instance."""
        return CreateMaterialTool()

    @pytest.mark.asyncio
    async def test_basic_material(self, tool):
        """Test basic material creation."""
        result = await tool.execute(
            name="TestMaterial",
        )
        assert result.success
        assert "materials.new" in result.output
        assert "TestMaterial" in result.output

    @pytest.mark.asyncio
    async def test_material_with_color(self, tool):
        """Test material with custom color."""
        result = await tool.execute(
            name="RedMaterial",
            base_color=[1.0, 0.0, 0.0],
        )
        assert result.success
        assert "Base Color" in result.output

    @pytest.mark.asyncio
    async def test_metallic_material(self, tool):
        """Test metallic material."""
        result = await tool.execute(
            name="GoldMetal",
            base_color=[1.0, 0.8, 0.2],
            metallic=1.0,
            roughness=0.3,
        )
        assert result.success
        assert "Metallic" in result.output
        assert "1.0" in result.output or "1" in result.output

    @pytest.mark.asyncio
    async def test_glass_material(self, tool):
        """Test glass/transmissive material."""
        result = await tool.execute(
            name="Glass",
            transmission=1.0,
            ior=1.45,
            roughness=0.0,
        )
        assert result.success
        assert "Transmission" in result.output
        assert "IOR" in result.output

    @pytest.mark.asyncio
    async def test_emission_material(self, tool):
        """Test emissive material."""
        result = await tool.execute(
            name="Glow",
            emission_color=[1.0, 1.0, 1.0],
            emission_strength=5.0,
        )
        assert result.success
        assert "Emission" in result.output
        assert "5.0" in result.output

    @pytest.mark.asyncio
    async def test_procedural_noise_material(self, tool):
        """Test material with procedural noise."""
        result = await tool.execute(
            name="Procedural",
            use_noise=True,
            noise_scale=5.0,
        )
        assert result.success
        assert "ShaderNodeTexNoise" in result.output
        assert "Scale" in result.output

    @pytest.mark.asyncio
    async def test_material_assign_to_object(self, tool):
        """Test assigning material to object."""
        result = await tool.execute(
            name="Material",
            assign_to="Cube",
        )
        assert result.success
        assert "Cube" in result.output
        assert "materials.append" in result.output or "materials[0]" in result.output

    @pytest.mark.asyncio
    async def test_material_with_alpha(self, tool):
        """Test material with alpha transparency."""
        result = await tool.execute(
            name="Transparent",
            alpha=0.5,
        )
        assert result.success
        assert "Alpha" in result.output
        assert "blend_method" in result.output


# ============================================================================
# SetupAnimationTool Tests
# ============================================================================


class TestSetupAnimationTool:
    """Test SetupAnimationTool."""

    @pytest.fixture
    def tool(self):
        """Create a SetupAnimationTool instance."""
        return SetupAnimationTool()

    @pytest.mark.asyncio
    async def test_turntable_animation(self, tool):
        """Test turntable animation preset."""
        result = await tool.execute(
            animation_type="turntable",
            end_frame=120,
        )
        assert result.success
        assert "rotation_euler" in result.output
        assert "keyframe_insert" in result.output

    @pytest.mark.asyncio
    async def test_bounce_animation(self, tool):
        """Test bounce animation preset."""
        result = await tool.execute(
            animation_type="bounce",
            height=3.0,
            cycles=2,
        )
        assert result.success
        assert "location" in result.output.lower()
        assert "keyframe_insert" in result.output

    @pytest.mark.asyncio
    async def test_orbit_animation(self, tool):
        """Test orbit animation preset."""
        result = await tool.execute(
            animation_type="orbit",
            end_frame=120,
        )
        assert result.success
        assert "location" in result.output.lower()
        assert "math.cos" in result.output or "cos" in result.output

    @pytest.mark.asyncio
    async def test_zoom_animation(self, tool):
        """Test zoom animation preset."""
        result = await tool.execute(
            animation_type="zoom",
        )
        assert result.success
        assert "scale" in result.output.lower()

    @pytest.mark.asyncio
    async def test_custom_keyframes(self, tool):
        """Test custom keyframe animation."""
        keyframes = [
            {"frame": 1, "value": [0, 0, 0]},
            {"frame": 60, "value": [5, 0, 0]},
        ]
        result = await tool.execute(
            animation_type="custom",
            property="location",
            keyframes=keyframes,
        )
        assert result.success
        assert "location" in result.output
        assert "keyframe_insert" in result.output

    @pytest.mark.asyncio
    async def test_animation_with_object_name(self, tool):
        """Test animation with specific object."""
        result = await tool.execute(
            object_name="Cube",
            animation_type="turntable",
        )
        assert result.success
        assert "Cube" in result.output

    @pytest.mark.asyncio
    async def test_animation_frame_range(self, tool):
        """Test animation with frame range."""
        result = await tool.execute(
            animation_type="turntable",
            start_frame=10,
            end_frame=200,
        )
        assert result.success
        assert "frame_start = 10" in result.output
        assert "frame_end = 200" in result.output

    @pytest.mark.asyncio
    async def test_animation_interpolation(self, tool):
        """Test animation with custom interpolation."""
        result = await tool.execute(
            animation_type="turntable",
            interpolation="LINEAR",
        )
        assert result.success
        assert "LINEAR" in result.output

    @pytest.mark.asyncio
    async def test_wave_animation(self, tool):
        """Test wave animation preset."""
        result = await tool.execute(
            animation_type="wave",
            amplitude=0.5,
            cycles=3,
        )
        assert result.success
        assert "location" in result.output.lower()


# ============================================================================
# RenderSceneTool Tests
# ============================================================================


class TestRenderSceneTool:
    """Test RenderSceneTool."""

    @pytest.fixture
    def tool(self):
        """Create a RenderSceneTool instance."""
        return RenderSceneTool()

    @pytest.mark.asyncio
    async def test_cycles_render_setup(self, tool):
        """Test Cycles render configuration."""
        result = await tool.execute(
            output_path="/tmp/render.png",
            engine="cycles",
            samples=128,
        )
        assert result.success
        assert "CYCLES" in result.output
        assert "samples = 128" in result.output

    @pytest.mark.asyncio
    async def test_eevee_render_setup(self, tool):
        """Test Eevee render configuration."""
        result = await tool.execute(
            output_path="/tmp/render.png",
            engine="eevee",
            samples=64,
        )
        assert result.success
        assert "EEVEE" in result.output

    @pytest.mark.asyncio
    async def test_resolution_settings(self, tool):
        """Test custom resolution settings."""
        result = await tool.execute(
            output_path="/tmp/render.png",
            resolution=[1920, 1080],
        )
        assert result.success
        assert "resolution_x = 1920" in result.output
        assert "resolution_y = 1080" in result.output

    @pytest.mark.asyncio
    async def test_transparent_background(self, tool):
        """Test transparent background setting."""
        result = await tool.execute(
            output_path="/tmp/render.png",
            transparent=True,
        )
        assert result.success
        assert "film_transparent = True" in result.output

    @pytest.mark.asyncio
    async def test_animation_render(self, tool):
        """Test animation render configuration."""
        result = await tool.execute(
            output_path="/tmp/anim/",
            render_animation=True,
            fps=30,
        )
        assert result.success
        assert "animation=True" in result.output
        assert "fps = 30" in result.output

    @pytest.mark.asyncio
    async def test_render_formats(self, tool):
        """Test different render formats."""
        for fmt in ["PNG", "JPEG", "EXR"]:
            result = await tool.execute(
                output_path=f"/tmp/render.{fmt.lower()}",
                format=fmt,
            )
            assert result.success
            assert fmt in result.output or fmt.replace("EXR", "OPEN_EXR") in result.output

    @pytest.mark.asyncio
    async def test_gpu_rendering(self, tool):
        """Test GPU rendering option."""
        result = await tool.execute(
            output_path="/tmp/render.png",
            engine="cycles",
            use_gpu=True,
        )
        assert result.success
        assert "GPU" in result.output

    @pytest.mark.asyncio
    async def test_render_metadata(self, tool):
        """Test render metadata."""
        result = await tool.execute(
            output_path="/tmp/render.png",
            engine="cycles",
            resolution=[1920, 1080],
            samples=128,
        )
        assert result.success
        assert result.metadata["engine"] == "cycles"
        assert result.metadata["resolution"] == [1920, 1080]
        assert result.metadata["samples"] == 128


# ============================================================================
# Tool Registration Tests
# ============================================================================


class TestToolRegistration:
    """Test that Blender tools are properly registered."""

    @pytest.mark.asyncio
    async def test_tools_registered(self):
        """Test that all Blender tools are registered."""
        from sindri.tools.registry import ToolRegistry

        registry = ToolRegistry.default()

        assert registry.get_tool("blender_script") is not None
        assert registry.get_tool("create_mesh") is not None
        assert registry.get_tool("apply_modifier") is not None
        assert registry.get_tool("create_material") is not None
        assert registry.get_tool("setup_animation") is not None
        assert registry.get_tool("render_scene") is not None

    def test_tool_schemas(self):
        """Test that tools have valid schemas."""
        tools = [
            BlenderScriptTool(),
            CreateMeshTool(),
            ApplyModifierTool(),
            CreateMaterialTool(),
            SetupAnimationTool(),
            RenderSceneTool(),
        ]

        for tool in tools:
            schema = tool.get_schema()
            assert schema["type"] == "function"
            assert "function" in schema
            assert "name" in schema["function"]
            assert "description" in schema["function"]
            assert "parameters" in schema["function"]


# ============================================================================
# Agent Registration Tests
# ============================================================================


class TestAgentRegistration:
    """Test that Dvalin agent is properly registered."""

    @pytest.mark.asyncio
    async def test_dvalin_agent_exists(self):
        """Test that Dvalin agent is defined."""
        from sindri.agents.registry import AGENTS, get_agent

        assert "dvalin" in AGENTS
        dvalin = get_agent("dvalin")
        assert dvalin.name == "dvalin"
        assert "blender" in dvalin.role.lower() or "3d" in dvalin.role.lower()

    @pytest.mark.asyncio
    async def test_dvalin_has_required_tools(self):
        """Test that Dvalin has the required tools."""
        from sindri.agents.registry import get_agent

        dvalin = get_agent("dvalin")
        required_tools = [
            "blender_script",
            "create_mesh",
            "apply_modifier",
            "create_material",
            "setup_animation",
            "render_scene",
            "read_file",
            "write_file",
        ]
        for tool in required_tools:
            assert tool in dvalin.tools, f"Missing tool: {tool}"

    @pytest.mark.asyncio
    async def test_dvalin_cannot_delegate(self):
        """Test that Dvalin is a Tier 2 agent and cannot delegate."""
        from sindri.agents.registry import get_agent

        dvalin = get_agent("dvalin")
        assert not dvalin.can_delegate

    @pytest.mark.asyncio
    async def test_brokkr_can_delegate_to_dvalin(self):
        """Test that Brokkr can delegate to Dvalin."""
        from sindri.agents.registry import get_agent

        brokkr = get_agent("brokkr")
        assert "dvalin" in brokkr.delegate_to


# ============================================================================
# Integration Tests
# ============================================================================


class TestIntegration:
    """Integration tests for Blender tools."""

    @pytest.mark.asyncio
    async def test_full_workflow_script_generation(self):
        """Test generating a complete scene script."""
        # Create a mesh
        mesh_tool = CreateMeshTool()
        mesh_result = await mesh_tool.execute(
            mesh_type="cube",
            name="Box",
            size=2.0,
        )
        assert mesh_result.success

        # Add material
        mat_tool = CreateMaterialTool()
        mat_result = await mat_tool.execute(
            name="BlueMetal",
            base_color=[0.2, 0.4, 0.8],
            metallic=0.8,
            roughness=0.2,
            assign_to="Box",
        )
        assert mat_result.success

        # Set up animation
        anim_tool = SetupAnimationTool()
        anim_result = await anim_tool.execute(
            object_name="Box",
            animation_type="turntable",
            end_frame=120,
        )
        assert anim_result.success

        # Configure render
        render_tool = RenderSceneTool()
        render_result = await render_tool.execute(
            output_path="/tmp/box_render.png",
            engine="cycles",
            samples=64,
        )
        assert render_result.success

    @pytest.mark.asyncio
    async def test_complex_mesh_with_modifier(self):
        """Test creating mesh with modifiers."""
        # Create base mesh
        mesh_tool = CreateMeshTool()
        mesh_result = await mesh_tool.execute(
            mesh_type="ico_sphere",
            radius=1.0,
            segments=16,
        )
        assert mesh_result.success

        # Apply subdivision
        mod_tool = ApplyModifierTool()
        subdiv_result = await mod_tool.execute(
            modifier_type="subdivision",
            levels=2,
        )
        assert subdiv_result.success

        # Apply displace
        displace_result = await mod_tool.execute(
            modifier_type="displace",
            strength=0.3,
        )
        assert displace_result.success

    @pytest.mark.asyncio
    async def test_save_all_to_file(self):
        """Test saving all tool outputs to files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Generate script
            script_tool = BlenderScriptTool()
            result = await script_tool.execute(
                description="Create a scene with cube and lighting",
                output_file=os.path.join(tmpdir, "scene.py"),
            )
            assert result.success
            assert os.path.exists(os.path.join(tmpdir, "scene.py"))

            # Generate mesh code
            mesh_tool = CreateMeshTool()
            result = await mesh_tool.execute(
                mesh_type="torus",
                output_file=os.path.join(tmpdir, "torus.py"),
            )
            assert result.success
            assert os.path.exists(os.path.join(tmpdir, "torus.py"))
