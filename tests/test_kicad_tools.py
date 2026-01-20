"""Tests for KiCad electronics design tools.

This module tests the KiCad tools for the Regin agent:
- CreateSchematicTool
- AddComponentTool
- RoutePCBTool
- DesignRuleCheckTool
- GenerateBOMTool
- ExportGerberTool
- SimulateCircuitTool
"""

import json
import pytest
import tempfile
from pathlib import Path

from sindri.tools.kicad import (
    KICAD_CLI_AVAILABLE,
    NGSPICE_AVAILABLE,
    FREEROUTING_AVAILABLE,
    COMPONENT_LIBRARIES,
    FOOTPRINT_LIBRARIES,
    MANUFACTURER_PRESETS,
    DEFAULT_DESIGN_RULES,
    SCHEMATIC_TEMPLATES,
    CreateSchematicTool,
    AddComponentTool,
    RoutePCBTool,
    DesignRuleCheckTool,
    GenerateBOMTool,
    ExportGerberTool,
    SimulateCircuitTool,
    Component,
    Wire,
    DRCViolation,
    generate_uuid,
    mm_to_mils,
    mils_to_mm,
    format_position,
    escape_string,
)


# =============================================================================
# Constants Tests
# =============================================================================


class TestKiCadConstants:
    """Test KiCad constants are properly defined."""

    def test_component_libraries_defined(self):
        """Test that expected component libraries are defined."""
        expected = ["Device", "power", "Connector", "RF_Module", "Regulator_Linear"]
        for lib in expected:
            assert lib in COMPONENT_LIBRARIES

    def test_device_library_components(self):
        """Test Device library has common components."""
        assert "R" in COMPONENT_LIBRARIES["Device"]
        assert "C" in COMPONENT_LIBRARIES["Device"]
        assert "LED" in COMPONENT_LIBRARIES["Device"]
        assert "D" in COMPONENT_LIBRARIES["Device"]

    def test_power_library_components(self):
        """Test power library has common symbols."""
        assert "GND" in COMPONENT_LIBRARIES["power"]
        assert "VCC" in COMPONENT_LIBRARIES["power"]
        assert "+3V3" in COMPONENT_LIBRARIES["power"]
        assert "+5V" in COMPONENT_LIBRARIES["power"]

    def test_footprint_libraries_defined(self):
        """Test that expected footprint libraries are defined."""
        expected = ["Resistor_SMD", "Capacitor_SMD", "Package_SO", "Package_QFP"]
        for lib in expected:
            assert lib in FOOTPRINT_LIBRARIES

    def test_manufacturer_presets_defined(self):
        """Test that manufacturer presets are defined."""
        expected = ["jlcpcb", "pcbway", "oshpark", "generic"]
        for mfr in expected:
            assert mfr in MANUFACTURER_PRESETS

    def test_manufacturer_preset_keys(self):
        """Test manufacturer presets have required keys."""
        required_keys = ["gerber_precision", "drill_format", "drill_units"]
        for mfr, preset in MANUFACTURER_PRESETS.items():
            for key in required_keys:
                assert key in preset, f"{mfr} missing {key}"

    def test_default_design_rules(self):
        """Test default design rules are defined."""
        assert "clearance" in DEFAULT_DESIGN_RULES
        assert "min_track_width" in DEFAULT_DESIGN_RULES
        assert "min_via_size" in DEFAULT_DESIGN_RULES
        assert "min_via_drill" in DEFAULT_DESIGN_RULES

    def test_schematic_templates_defined(self):
        """Test that schematic templates are defined."""
        expected = ["esp32", "arduino", "power_supply", "555_timer", "h_bridge", "sensor_module", "custom"]
        for template in expected:
            assert template in SCHEMATIC_TEMPLATES

    def test_esp32_template_has_components(self):
        """Test ESP32 template has components."""
        template = SCHEMATIC_TEMPLATES["esp32"]
        assert "components" in template
        assert len(template["components"]) > 0
        # Should have ESP32 module
        refs = [c.reference for c in template["components"]]
        assert "U1" in refs


# =============================================================================
# Helper Functions Tests
# =============================================================================


class TestHelperFunctions:
    """Test helper functions."""

    def test_generate_uuid(self):
        """Test UUID generation."""
        uuid1 = generate_uuid()
        uuid2 = generate_uuid()
        assert uuid1 != uuid2
        assert len(uuid1) == 36  # Standard UUID format

    def test_mm_to_mils(self):
        """Test mm to mils conversion."""
        assert abs(mm_to_mils(1.0) - 39.3701) < 0.0001
        assert abs(mm_to_mils(2.54) - 100.0) < 0.01  # 2.54mm = 100 mils

    def test_mils_to_mm(self):
        """Test mils to mm conversion."""
        assert abs(mils_to_mm(100) - 2.54) < 0.01
        assert abs(mils_to_mm(1) - 0.0254) < 0.0001

    def test_format_position(self):
        """Test position formatting."""
        pos = format_position(10.5, 20.25)
        assert "(at 10.5000 20.2500)" == pos

    def test_escape_string(self):
        """Test string escaping."""
        assert escape_string('Hello "World"') == 'Hello \\"World\\"'
        assert escape_string("Back\\slash") == "Back\\\\slash"


# =============================================================================
# Data Classes Tests
# =============================================================================


class TestDataClasses:
    """Test data classes."""

    def test_component_creation(self):
        """Test Component dataclass."""
        comp = Component(
            reference="R1",
            symbol="Device:R",
            value="10k",
            footprint="Resistor_SMD:R_0805_2012Metric",
        )
        assert comp.reference == "R1"
        assert comp.symbol == "Device:R"
        assert comp.value == "10k"
        assert comp.position == (0, 0)
        assert comp.rotation == 0

    def test_component_with_position(self):
        """Test Component with custom position."""
        comp = Component(
            reference="C1",
            symbol="Device:C",
            value="100nF",
            footprint="0603",
            position=(50.0, 100.0),
            rotation=90,
        )
        assert comp.position == (50.0, 100.0)
        assert comp.rotation == 90

    def test_wire_creation(self):
        """Test Wire dataclass."""
        wire = Wire(start=(10, 20), end=(30, 40))
        assert wire.start == (10, 20)
        assert wire.end == (30, 40)

    def test_drc_violation_creation(self):
        """Test DRCViolation dataclass."""
        violation = DRCViolation(
            rule="clearance",
            severity="error",
            description="Trace too close to pad",
            location=(15.5, 22.3),
        )
        assert violation.rule == "clearance"
        assert violation.severity == "error"
        assert violation.location == (15.5, 22.3)


# =============================================================================
# CreateSchematicTool Tests
# =============================================================================


class TestCreateSchematicTool:
    """Test CreateSchematicTool."""

    @pytest.fixture
    def tool(self):
        return CreateSchematicTool()

    @pytest.mark.asyncio
    async def test_basic_schematic_generation(self, tool):
        """Test basic schematic generation."""
        result = await tool.execute(
            description="Simple LED circuit with resistor",
            title="LED_Test",
        )
        assert result.success
        assert "kicad_sch" in result.output
        assert "LED_Test" in result.output

    @pytest.mark.asyncio
    async def test_esp32_template(self, tool):
        """Test ESP32 template generation."""
        result = await tool.execute(
            description="ESP32 development board",
            template="esp32",
        )
        assert result.success
        assert "ESP32" in result.output or "esp32" in result.output.lower()
        assert result.metadata["template"] == "esp32"
        assert result.metadata["component_count"] > 0

    @pytest.mark.asyncio
    async def test_555_timer_template(self, tool):
        """Test 555 timer template generation."""
        result = await tool.execute(
            description="555 timer astable oscillator",
            template="555_timer",
        )
        assert result.success
        assert result.metadata["template"] == "555_timer"

    @pytest.mark.asyncio
    async def test_power_supply_template(self, tool):
        """Test power supply template generation."""
        result = await tool.execute(
            description="3.3V linear power supply",
            template="power_supply",
        )
        assert result.success
        assert result.metadata["template"] == "power_supply"

    @pytest.mark.asyncio
    async def test_auto_template_detection_esp32(self, tool):
        """Test automatic template detection for ESP32."""
        result = await tool.execute(
            description="ESP32 based IoT device with WiFi",
        )
        assert result.success
        assert result.metadata["template"] == "esp32"

    @pytest.mark.asyncio
    async def test_auto_template_detection_timer(self, tool):
        """Test automatic template detection for 555 timer."""
        result = await tool.execute(
            description="555 timer oscillator circuit",
        )
        assert result.success
        assert result.metadata["template"] == "555_timer"

    @pytest.mark.asyncio
    async def test_custom_components(self, tool):
        """Test schematic with custom component list."""
        result = await tool.execute(
            description="Custom circuit",
            template="custom",
            components=[
                {"reference": "R1", "symbol": "Device:R", "value": "1k", "footprint": "0805"},
                {"reference": "LED1", "symbol": "Device:LED", "value": "Red", "footprint": "0603"},
            ],
        )
        assert result.success
        assert result.metadata["component_count"] == 2

    @pytest.mark.asyncio
    async def test_output_to_file(self, tool):
        """Test saving schematic to file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_file = Path(tmpdir) / "test.kicad_sch"
            result = await tool.execute(
                description="Simple RC circuit",
                output_file=str(output_file),
            )
            assert result.success
            assert output_file.exists()
            content = output_file.read_text()
            assert "kicad_sch" in content

    @pytest.mark.asyncio
    async def test_metadata_returned(self, tool):
        """Test that metadata is returned."""
        result = await tool.execute(
            description="Test circuit",
        )
        assert result.success
        assert "title" in result.metadata
        assert "template" in result.metadata
        assert "component_count" in result.metadata
        assert "kicad_cli_available" in result.metadata


# =============================================================================
# AddComponentTool Tests
# =============================================================================


class TestAddComponentTool:
    """Test AddComponentTool."""

    @pytest.fixture
    def tool(self):
        return AddComponentTool()

    @pytest.mark.asyncio
    async def test_add_resistor(self, tool):
        """Test adding a resistor."""
        result = await tool.execute(
            symbol="Device:R",
            value="10k",
            footprint="0805",
        )
        assert result.success
        assert "R" in result.output
        assert result.metadata["value"] == "10k"

    @pytest.mark.asyncio
    async def test_add_capacitor(self, tool):
        """Test adding a capacitor."""
        result = await tool.execute(
            symbol="Device:C",
            value="100nF",
            footprint="0603",
        )
        assert result.success
        assert result.metadata["symbol"] == "Device:C"

    @pytest.mark.asyncio
    async def test_add_led(self, tool):
        """Test adding an LED."""
        result = await tool.execute(
            symbol="Device:LED",
            value="Red",
        )
        assert result.success
        # Should auto-assign D? reference
        assert "D" in result.metadata["reference"]

    @pytest.mark.asyncio
    async def test_add_ic(self, tool):
        """Test adding an IC."""
        result = await tool.execute(
            symbol="RF_Module:ESP32-WROOM-32",
            value="ESP32-WROOM-32E",
        )
        assert result.success
        assert "U" in result.metadata["reference"]

    @pytest.mark.asyncio
    async def test_add_with_position(self, tool):
        """Test adding component with position."""
        result = await tool.execute(
            symbol="Device:R",
            value="4.7k",
            position=[50, 100],
            rotation=90,
        )
        assert result.success
        assert result.metadata["position"] == [50, 100]
        assert result.metadata["rotation"] == 90

    @pytest.mark.asyncio
    async def test_add_with_explicit_reference(self, tool):
        """Test adding component with explicit reference."""
        result = await tool.execute(
            symbol="Device:R",
            value="1k",
            reference="R42",
        )
        assert result.success
        assert result.metadata["reference"] == "R42"

    @pytest.mark.asyncio
    async def test_footprint_expansion(self, tool):
        """Test that short footprint names are expanded."""
        result = await tool.execute(
            symbol="Device:R",
            value="10k",
            footprint="0805",
        )
        assert result.success
        # Should expand to full footprint name
        assert "Resistor_SMD" in result.metadata["footprint"]


# =============================================================================
# RoutePCBTool Tests
# =============================================================================


class TestRoutePCBTool:
    """Test RoutePCBTool."""

    @pytest.fixture
    def tool(self):
        return RoutePCBTool()

    @pytest.fixture
    def sample_pcb_file(self, tmp_path):
        """Create a minimal PCB file for testing."""
        content = "(kicad_pcb (version 20231014) (generator pcbnew))"
        file_path = tmp_path / "test.kicad_pcb"
        file_path.write_text(content)
        return file_path

    @pytest.mark.asyncio
    async def test_file_not_found(self, tool):
        """Test handling of non-existent file."""
        result = await tool.execute(
            input_file="/nonexistent/file.kicad_pcb",
        )
        assert not result.success
        assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_basic_routing(self, tool, sample_pcb_file):
        """Test basic routing operation."""
        result = await tool.execute(
            input_file=str(sample_pcb_file),
        )
        assert result.success
        assert "routing" in result.output.lower() or "layer" in result.output.lower()

    @pytest.mark.asyncio
    async def test_layer_configuration(self, tool, sample_pcb_file):
        """Test layer configuration."""
        result = await tool.execute(
            input_file=str(sample_pcb_file),
            layers=4,
        )
        assert result.success
        assert result.metadata["config"]["layers"] == 4

    @pytest.mark.asyncio
    async def test_trace_width_setting(self, tool, sample_pcb_file):
        """Test trace width configuration."""
        result = await tool.execute(
            input_file=str(sample_pcb_file),
            trace_width=0.3,
            via_size=0.8,
        )
        assert result.success
        assert result.metadata["config"]["trace_width_mm"] == 0.3
        assert result.metadata["config"]["via_size_mm"] == 0.8

    @pytest.mark.asyncio
    async def test_differential_pairs(self, tool, sample_pcb_file):
        """Test differential pair routing."""
        result = await tool.execute(
            input_file=str(sample_pcb_file),
            differential_pairs=["USB_D+", "USB_D-"],
        )
        assert result.success
        assert "USB_D+" in result.metadata["config"]["differential_pairs"]

    @pytest.mark.asyncio
    async def test_priority_nets(self, tool, sample_pcb_file):
        """Test priority net routing."""
        result = await tool.execute(
            input_file=str(sample_pcb_file),
            priority_nets=["GND", "VCC", "3V3"],
        )
        assert result.success
        assert "GND" in result.metadata["config"]["priority_nets"]


# =============================================================================
# DesignRuleCheckTool Tests
# =============================================================================


class TestDesignRuleCheckTool:
    """Test DesignRuleCheckTool."""

    @pytest.fixture
    def tool(self):
        return DesignRuleCheckTool()

    @pytest.fixture
    def sample_pcb_file(self, tmp_path):
        """Create a minimal PCB file for testing."""
        content = "(kicad_pcb (version 20231014) (generator pcbnew))"
        file_path = tmp_path / "test.kicad_pcb"
        file_path.write_text(content)
        return file_path

    @pytest.mark.asyncio
    async def test_file_not_found(self, tool):
        """Test handling of non-existent file."""
        result = await tool.execute(
            input_file="/nonexistent/file.kicad_pcb",
        )
        assert not result.success
        assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_basic_drc(self, tool, sample_pcb_file):
        """Test basic DRC operation."""
        result = await tool.execute(
            input_file=str(sample_pcb_file),
        )
        assert result.success
        assert "clearance" in result.output.lower() or "design rule" in result.output.lower()

    @pytest.mark.asyncio
    async def test_custom_clearance(self, tool, sample_pcb_file):
        """Test custom clearance setting."""
        result = await tool.execute(
            input_file=str(sample_pcb_file),
            clearance=0.25,
            min_track_width=0.2,
        )
        assert result.success
        assert result.metadata["rules"]["clearance_mm"] == 0.25
        assert result.metadata["rules"]["min_track_width_mm"] == 0.2

    @pytest.mark.asyncio
    async def test_output_format_text(self, tool, sample_pcb_file):
        """Test text output format."""
        result = await tool.execute(
            input_file=str(sample_pcb_file),
            output_format="text",
        )
        assert result.success
        assert result.metadata["output_format"] == "text"

    @pytest.mark.asyncio
    async def test_output_format_json(self, tool, sample_pcb_file):
        """Test JSON output format."""
        result = await tool.execute(
            input_file=str(sample_pcb_file),
            output_format="json",
        )
        assert result.success
        # Should be valid JSON
        data = json.loads(result.output)
        assert "rules" in data

    @pytest.mark.asyncio
    async def test_silkscreen_check_option(self, tool, sample_pcb_file):
        """Test silkscreen check option."""
        result = await tool.execute(
            input_file=str(sample_pcb_file),
            check_silkscreen=False,
        )
        assert result.success
        assert result.metadata["rules"]["check_silkscreen"] is False


# =============================================================================
# GenerateBOMTool Tests
# =============================================================================


class TestGenerateBOMTool:
    """Test GenerateBOMTool."""

    @pytest.fixture
    def tool(self):
        return GenerateBOMTool()

    @pytest.fixture
    def sample_sch_file(self, tmp_path):
        """Create a minimal schematic file for testing."""
        content = "(kicad_sch (version 20231120) (generator sindri))"
        file_path = tmp_path / "test.kicad_sch"
        file_path.write_text(content)
        return file_path

    @pytest.mark.asyncio
    async def test_file_not_found(self, tool):
        """Test handling of non-existent file."""
        result = await tool.execute(
            input_file="/nonexistent/file.kicad_sch",
        )
        assert not result.success
        assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_basic_bom_generation(self, tool, sample_sch_file):
        """Test basic BOM generation."""
        result = await tool.execute(
            input_file=str(sample_sch_file),
        )
        assert result.success
        assert result.metadata["component_count"] > 0

    @pytest.mark.asyncio
    async def test_csv_format(self, tool, sample_sch_file):
        """Test CSV output format."""
        result = await tool.execute(
            input_file=str(sample_sch_file),
            format="csv",
        )
        assert result.success
        assert "Reference" in result.output
        assert "Value" in result.output
        assert "," in result.output

    @pytest.mark.asyncio
    async def test_json_format(self, tool, sample_sch_file):
        """Test JSON output format."""
        result = await tool.execute(
            input_file=str(sample_sch_file),
            format="json",
        )
        assert result.success
        data = json.loads(result.output)
        assert isinstance(data, list)
        assert len(data) > 0

    @pytest.mark.asyncio
    async def test_html_format(self, tool, sample_sch_file):
        """Test HTML output format."""
        result = await tool.execute(
            input_file=str(sample_sch_file),
            format="html",
        )
        assert result.success
        assert "<table>" in result.output
        assert "</table>" in result.output

    @pytest.mark.asyncio
    async def test_grouping_option(self, tool, sample_sch_file):
        """Test component grouping option."""
        result = await tool.execute(
            input_file=str(sample_sch_file),
            group_by_value=True,
        )
        assert result.success
        assert result.metadata["grouped"] is True

    @pytest.mark.asyncio
    async def test_save_to_file(self, tool, sample_sch_file, tmp_path):
        """Test saving BOM to file."""
        output_file = tmp_path / "bom.csv"
        result = await tool.execute(
            input_file=str(sample_sch_file),
            output_file=str(output_file),
            format="csv",
        )
        assert result.success
        assert output_file.exists()


# =============================================================================
# ExportGerberTool Tests
# =============================================================================


class TestExportGerberTool:
    """Test ExportGerberTool."""

    @pytest.fixture
    def tool(self):
        return ExportGerberTool()

    @pytest.fixture
    def sample_pcb_file(self, tmp_path):
        """Create a minimal PCB file for testing."""
        content = "(kicad_pcb (version 20231014) (generator pcbnew))"
        file_path = tmp_path / "test.kicad_pcb"
        file_path.write_text(content)
        return file_path

    @pytest.mark.asyncio
    async def test_file_not_found(self, tool):
        """Test handling of non-existent file."""
        result = await tool.execute(
            input_file="/nonexistent/file.kicad_pcb",
        )
        assert not result.success
        assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_basic_gerber_export(self, tool, sample_pcb_file):
        """Test basic Gerber export."""
        result = await tool.execute(
            input_file=str(sample_pcb_file),
        )
        assert result.success
        assert "gerber" in result.output.lower()

    @pytest.mark.asyncio
    async def test_jlcpcb_preset(self, tool, sample_pcb_file):
        """Test JLCPCB manufacturer preset."""
        result = await tool.execute(
            input_file=str(sample_pcb_file),
            manufacturer="jlcpcb",
        )
        assert result.success
        assert "JLCPCB" in result.output
        assert result.metadata["manufacturer"] == "jlcpcb"

    @pytest.mark.asyncio
    async def test_pcbway_preset(self, tool, sample_pcb_file):
        """Test PCBWay manufacturer preset."""
        result = await tool.execute(
            input_file=str(sample_pcb_file),
            manufacturer="pcbway",
        )
        assert result.success
        assert result.metadata["manufacturer"] == "pcbway"

    @pytest.mark.asyncio
    async def test_oshpark_preset(self, tool, sample_pcb_file):
        """Test OSH Park manufacturer preset."""
        result = await tool.execute(
            input_file=str(sample_pcb_file),
            manufacturer="oshpark",
        )
        assert result.success
        assert result.metadata["manufacturer"] == "oshpark"

    @pytest.mark.asyncio
    async def test_include_position_file(self, tool, sample_pcb_file):
        """Test including position file."""
        result = await tool.execute(
            input_file=str(sample_pcb_file),
            include_pos=True,
        )
        assert result.success
        assert "pos" in result.output.lower() or "position" in result.output.lower()

    @pytest.mark.asyncio
    async def test_custom_output_dir(self, tool, sample_pcb_file, tmp_path):
        """Test custom output directory."""
        output_dir = tmp_path / "gerbers"
        result = await tool.execute(
            input_file=str(sample_pcb_file),
            output_dir=str(output_dir),
        )
        assert result.success
        assert str(output_dir) in result.metadata["output_dir"]

    @pytest.mark.asyncio
    async def test_gerber_precision(self, tool, sample_pcb_file):
        """Test Gerber precision setting."""
        result = await tool.execute(
            input_file=str(sample_pcb_file),
            gerber_precision="4.5",
        )
        assert result.success
        assert result.metadata["preset"]["gerber_precision"] == "4.5"


# =============================================================================
# SimulateCircuitTool Tests
# =============================================================================


class TestSimulateCircuitTool:
    """Test SimulateCircuitTool."""

    @pytest.fixture
    def tool(self):
        return SimulateCircuitTool()

    @pytest.fixture
    def sample_sch_file(self, tmp_path):
        """Create a minimal schematic file for testing."""
        content = "(kicad_sch (version 20231120) (generator sindri))"
        file_path = tmp_path / "test.kicad_sch"
        file_path.write_text(content)
        return file_path

    @pytest.mark.asyncio
    async def test_file_not_found(self, tool):
        """Test handling of non-existent file."""
        result = await tool.execute(
            schematic_file="/nonexistent/file.kicad_sch",
            analysis="op",
        )
        assert not result.success
        assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_op_analysis(self, tool, sample_sch_file):
        """Test DC operating point analysis."""
        result = await tool.execute(
            schematic_file=str(sample_sch_file),
            analysis="op",
        )
        assert result.success
        assert ".op" in result.output
        assert result.metadata["analysis"] == "op"

    @pytest.mark.asyncio
    async def test_transient_analysis(self, tool, sample_sch_file):
        """Test transient analysis."""
        result = await tool.execute(
            schematic_file=str(sample_sch_file),
            analysis="transient",
            stop_time="10ms",
            step_time="1us",
        )
        assert result.success
        assert ".tran" in result.output
        assert "10ms" in result.output

    @pytest.mark.asyncio
    async def test_ac_analysis(self, tool, sample_sch_file):
        """Test AC frequency sweep analysis."""
        result = await tool.execute(
            schematic_file=str(sample_sch_file),
            analysis="ac",
            start_freq="1",
            stop_freq="1meg",
            points_per_decade=20,
        )
        assert result.success
        assert ".ac" in result.output
        assert "1meg" in result.output

    @pytest.mark.asyncio
    async def test_dc_sweep_analysis(self, tool, sample_sch_file):
        """Test DC sweep analysis."""
        result = await tool.execute(
            schematic_file=str(sample_sch_file),
            analysis="dc",
            sweep_source="V1",
            start=0,
            stop=5,
        )
        assert result.success
        assert ".dc" in result.output
        assert "V1" in result.output

    @pytest.mark.asyncio
    async def test_dc_sweep_missing_params(self, tool, sample_sch_file):
        """Test DC sweep with missing parameters."""
        result = await tool.execute(
            schematic_file=str(sample_sch_file),
            analysis="dc",
        )
        assert not result.success
        assert "sweep_source" in result.error.lower() or "start" in result.error.lower()

    @pytest.mark.asyncio
    async def test_ac_sweep_missing_params(self, tool, sample_sch_file):
        """Test AC sweep with missing parameters."""
        result = await tool.execute(
            schematic_file=str(sample_sch_file),
            analysis="ac",
        )
        assert not result.success
        assert "freq" in result.error.lower()

    @pytest.mark.asyncio
    async def test_custom_probes(self, tool, sample_sch_file):
        """Test custom probe points."""
        result = await tool.execute(
            schematic_file=str(sample_sch_file),
            analysis="transient",
            stop_time="1ms",
            probes=["V(out)", "I(R1)"],
        )
        assert result.success
        assert "V(out)" in result.output or "out" in str(result.metadata["probes"])

    @pytest.mark.asyncio
    async def test_invalid_analysis_type(self, tool, sample_sch_file):
        """Test invalid analysis type."""
        result = await tool.execute(
            schematic_file=str(sample_sch_file),
            analysis="invalid",
        )
        assert not result.success
        assert "unknown" in result.error.lower() or "invalid" in result.error.lower()


# =============================================================================
# Integration Tests
# =============================================================================


class TestKiCadToolsIntegration:
    """Integration tests for KiCad tools."""

    @pytest.mark.asyncio
    async def test_tools_registered(self):
        """Test that all KiCad tools are registered in the registry."""
        from sindri.tools.registry import ToolRegistry

        registry = ToolRegistry.default()

        assert registry.get_tool("create_schematic") is not None
        assert registry.get_tool("add_component") is not None
        assert registry.get_tool("route_pcb") is not None
        assert registry.get_tool("design_rule_check") is not None
        assert registry.get_tool("generate_bom") is not None
        assert registry.get_tool("export_gerber") is not None
        assert registry.get_tool("simulate_circuit") is not None

    @pytest.mark.asyncio
    async def test_regin_agent_exists(self):
        """Test that Regin agent is defined."""
        from sindri.agents.registry import AGENTS, get_agent

        assert "regin" in AGENTS
        regin = get_agent("regin")
        assert regin.name == "regin"
        assert "kicad" in regin.role.lower() or "electronics" in regin.role.lower()

    @pytest.mark.asyncio
    async def test_regin_has_required_tools(self):
        """Test that Regin has the required tools."""
        from sindri.agents.registry import get_agent

        regin = get_agent("regin")
        required_tools = [
            "create_schematic",
            "add_component",
            "route_pcb",
            "design_rule_check",
            "generate_bom",
            "export_gerber",
            "simulate_circuit",
            "read_file",
            "write_file",
        ]
        for tool in required_tools:
            assert tool in regin.tools, f"Missing tool: {tool}"

    @pytest.mark.asyncio
    async def test_regin_cannot_delegate(self):
        """Test that Regin is a Tier 3 agent and cannot delegate."""
        from sindri.agents.registry import get_agent

        regin = get_agent("regin")
        assert not regin.can_delegate

    @pytest.mark.asyncio
    async def test_brokkr_can_delegate_to_regin(self):
        """Test that Brokkr can delegate to Regin."""
        from sindri.agents.registry import get_agent

        brokkr = get_agent("brokkr")
        assert "regin" in brokkr.delegate_to

    @pytest.mark.asyncio
    async def test_workflow_schematic_to_bom(self):
        """Test workflow: create schematic then generate BOM."""
        sch_tool = CreateSchematicTool()
        bom_tool = GenerateBOMTool()

        # Create schematic
        sch_result = await sch_tool.execute(
            description="LED with 1k resistor",
            title="LED_Circuit",
        )
        assert sch_result.success

        # Save schematic to file
        with tempfile.TemporaryDirectory() as tmpdir:
            sch_file = Path(tmpdir) / "circuit.kicad_sch"
            sch_file.write_text(sch_result.output)

            # Generate BOM
            bom_result = await bom_tool.execute(
                input_file=str(sch_file),
                format="csv",
            )
            assert bom_result.success

    @pytest.mark.asyncio
    async def test_tool_schemas_valid(self):
        """Test that all tool schemas are valid."""
        tools = [
            CreateSchematicTool(),
            AddComponentTool(),
            RoutePCBTool(),
            DesignRuleCheckTool(),
            GenerateBOMTool(),
            ExportGerberTool(),
            SimulateCircuitTool(),
        ]

        for tool in tools:
            schema = tool.get_schema()
            assert schema["type"] == "function"
            assert "function" in schema
            assert "name" in schema["function"]
            assert "description" in schema["function"]
            assert "parameters" in schema["function"]
            assert tool.name == schema["function"]["name"]
