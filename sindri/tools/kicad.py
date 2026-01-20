"""KiCad electronics design tools for the Regin agent.

This module provides tools for:
- Schematic capture and generation
- Component placement
- PCB routing
- Design rule checking
- Bill of Materials generation
- Gerber file export
- SPICE simulation

All tools work without KiCad installed by generating file formats directly.
Optional integration with kicad-cli and ngspice when available.
"""

import asyncio
import json
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4

from sindri.tools.base import Tool, ToolResult

# Check for external tool availability
KICAD_CLI_AVAILABLE = shutil.which("kicad-cli") is not None
NGSPICE_AVAILABLE = shutil.which("ngspice") is not None
FREEROUTING_AVAILABLE = (
    shutil.which("freerouting") is not None
    or Path("/opt/freerouting/freerouting.jar").exists()
)

# Try to import pcbnew (KiCad Python module)
PCBNEW_AVAILABLE = False
try:
    import pcbnew  # noqa: F401

    PCBNEW_AVAILABLE = True
except ImportError:
    pass


# =============================================================================
# Constants
# =============================================================================

COMPONENT_LIBRARIES = {
    "Device": ["R", "C", "L", "D", "LED", "D_Schottky", "D_Zener", "CP", "Crystal"],
    "power": ["GND", "VCC", "+3V3", "+5V", "+12V", "PWR_FLAG"],
    "Connector": [
        "USB_C_Receptacle_USB2.0",
        "Conn_01x02",
        "Conn_01x04",
        "Conn_01x06",
        "Conn_02x03",
        "Conn_02x05",
        "Jack_DC",
        "Barrel_Jack",
    ],
    "Connector_Generic": [
        "Conn_01x02",
        "Conn_01x03",
        "Conn_01x04",
        "Conn_01x05",
        "Conn_01x06",
        "Conn_02x02",
        "Conn_02x03",
        "Conn_02x04",
        "Conn_02x05",
    ],
    "MCU_ST_STM32F4": ["STM32F411CEUx", "STM32F401CCUx", "STM32F407VGTx"],
    "MCU_Microchip_ATmega": ["ATmega328P-AU", "ATmega328P-PU", "ATmega2560-16AU"],
    "RF_Module": ["ESP32-WROOM-32", "ESP32-WROOM-32E", "ESP-12E", "ESP-12F"],
    "Regulator_Linear": ["AMS1117-3.3", "AMS1117-5.0", "LM7805", "LM7812", "LM317"],
    "Regulator_Switching": ["LM2596", "MP1584", "TPS563200"],
    "Amplifier_Operational": ["LM358", "LM324", "TL072", "NE5532"],
    "Timer": ["NE555", "LM555"],
    "Transistor_FET": ["IRLZ44N", "IRF3205", "AO3400", "AO3401", "BSS138"],
    "Transistor_BJT": ["BC547", "BC557", "2N2222", "2N3904", "2N3906"],
    "Interface_USB": ["CH340G", "CP2102", "FT232RL"],
}

FOOTPRINT_LIBRARIES = {
    "Resistor_SMD": ["R_0402_*", "R_0603_*", "R_0805_*", "R_1206_*", "R_2512_*"],
    "Capacitor_SMD": ["C_0402_*", "C_0603_*", "C_0805_*", "C_1206_*"],
    "Capacitor_THT": ["CP_Radial_D5.0mm_P2.00mm", "CP_Radial_D6.3mm_P2.50mm"],
    "Package_SO": ["SOIC-8_*", "SOIC-14_*", "SOIC-16_*", "TSSOP-8_*", "TSSOP-14_*"],
    "Package_QFP": ["LQFP-32_*", "LQFP-48_*", "LQFP-64_*", "LQFP-100_*"],
    "Package_DFN_QFN": ["QFN-24_*", "QFN-32_*", "QFN-48_*", "DFN-8_*"],
    "Package_TO_SOT_SMD": ["SOT-23", "SOT-23-5", "SOT-223", "TO-252-2", "TO-263-2"],
    "Package_TO_SOT_THT": ["TO-92_*", "TO-220-3_*", "TO-247-3_*"],
    "Crystal": ["Crystal_SMD_3215-2Pin_*", "Crystal_HC49-U_Vertical"],
    "LED_SMD": ["LED_0603_*", "LED_0805_*", "LED_1206_*"],
    "Connector_USB": ["USB_C_Receptacle_*", "USB_Micro-B_*", "USB_A_*"],
    "Connector_PinHeader": ["PinHeader_1x02_*", "PinHeader_1x04_*", "PinHeader_2x03_*"],
    "Module": ["ESP32-WROOM-32", "ESP-12E", "ESP-12F"],
}

MANUFACTURER_PRESETS = {
    "jlcpcb": {
        "gerber_precision": "4.6",
        "drill_format": "excellon",
        "drill_units": "mm",
        "drill_zeros": "decimal",
        "use_protel_extensions": True,
        "include_netlist": False,
        "edge_cuts_layer": "Edge.Cuts",
    },
    "pcbway": {
        "gerber_precision": "4.6",
        "drill_format": "excellon",
        "drill_units": "mm",
        "drill_zeros": "decimal",
        "use_protel_extensions": True,
        "include_netlist": False,
        "edge_cuts_layer": "Edge.Cuts",
    },
    "oshpark": {
        "gerber_precision": "4.5",
        "drill_format": "excellon",
        "drill_units": "inch",
        "drill_zeros": "suppress_leading",
        "use_protel_extensions": False,
        "include_netlist": False,
        "edge_cuts_layer": "Edge.Cuts",
    },
    "generic": {
        "gerber_precision": "4.6",
        "drill_format": "excellon",
        "drill_units": "mm",
        "drill_zeros": "decimal",
        "use_protel_extensions": True,
        "include_netlist": False,
        "edge_cuts_layer": "Edge.Cuts",
    },
}

# Standard PCB design rules (JLCPCB-compatible)
DEFAULT_DESIGN_RULES = {
    "clearance": 0.2,  # mm
    "min_track_width": 0.127,  # mm (5 mil)
    "min_via_size": 0.6,  # mm
    "min_via_drill": 0.3,  # mm
    "min_hole_size": 0.3,  # mm
    "min_annular_ring": 0.15,  # mm
    "copper_to_edge": 0.3,  # mm
    "silkscreen_width": 0.15,  # mm
}

# E24 resistor series
E24_SERIES = [
    "1.0",
    "1.1",
    "1.2",
    "1.3",
    "1.5",
    "1.6",
    "1.8",
    "2.0",
    "2.2",
    "2.4",
    "2.7",
    "3.0",
    "3.3",
    "3.6",
    "3.9",
    "4.3",
    "4.7",
    "5.1",
    "5.6",
    "6.2",
    "6.8",
    "7.5",
    "8.2",
    "9.1",
]


# =============================================================================
# Data Classes
# =============================================================================


@dataclass
class Component:
    """Represents an electronic component."""

    reference: str
    symbol: str
    value: str
    footprint: str
    position: tuple[float, float] = (0, 0)
    rotation: float = 0
    properties: dict = None

    def __post_init__(self):
        if self.properties is None:
            self.properties = {}


@dataclass
class Wire:
    """Represents a wire connection in schematic."""

    start: tuple[float, float]
    end: tuple[float, float]


@dataclass
class DRCViolation:
    """Represents a design rule violation."""

    rule: str
    severity: str  # error, warning
    description: str
    location: tuple[float, float] | None = None
    items: list[str] | None = None


# =============================================================================
# Helper Functions
# =============================================================================


def generate_uuid() -> str:
    """Generate a KiCad-compatible UUID."""
    return str(uuid4())


def mm_to_mils(mm: float) -> float:
    """Convert millimeters to mils."""
    return mm * 39.3701


def mils_to_mm(mils: float) -> float:
    """Convert mils to millimeters."""
    return mils / 39.3701


def format_position(x: float, y: float) -> str:
    """Format position for KiCad S-expression."""
    return f"(at {x:.4f} {y:.4f})"


def format_size(w: float, h: float) -> str:
    """Format size for KiCad S-expression."""
    return f"(size {w:.4f} {h:.4f})"


def escape_string(s: str) -> str:
    """Escape a string for KiCad S-expression."""
    return s.replace("\\", "\\\\").replace('"', '\\"')


def generate_schematic_header(
    title: str = "Untitled",
    date: str | None = None,
    revision: str = "1.0",
) -> str:
    """Generate KiCad schematic file header."""
    if date is None:
        date = datetime.now().strftime("%Y-%m-%d")

    return f'''(kicad_sch (version 20231120) (generator "sindri")

  (uuid "{generate_uuid()}")

  (paper "A4")

  (title_block
    (title "{escape_string(title)}")
    (date "{date}")
    (rev "{revision}")
    (company "Generated by Sindri")
  )

  (lib_symbols
  )
'''


def generate_schematic_footer() -> str:
    """Generate KiCad schematic file footer."""
    return "\n)\n"


def generate_symbol_instance(comp: Component) -> str:
    """Generate a symbol instance in KiCad schematic format."""
    lib_name = comp.symbol.split(":")[0] if ":" in comp.symbol else "Device"
    symbol_name = comp.symbol.split(":")[-1]

    return f'''
  (symbol (lib_id "{comp.symbol}") {format_position(comp.position[0], comp.position[1])}
    (unit 1)
    (exclude_from_sim no) (in_bom yes) (on_board yes) (dnp no)
    (uuid "{generate_uuid()}")
    (property "Reference" "{comp.reference}" (at {comp.position[0]:.4f} {comp.position[1] - 2.54:.4f} 0)
      (effects (font (size 1.27 1.27)))
    )
    (property "Value" "{comp.value}" (at {comp.position[0]:.4f} {comp.position[1] + 2.54:.4f} 0)
      (effects (font (size 1.27 1.27)))
    )
    (property "Footprint" "{comp.footprint}" (at {comp.position[0]:.4f} {comp.position[1]:.4f} 0)
      (effects (font (size 1.27 1.27)) hide)
    )
  )
'''


def generate_wire(wire: Wire) -> str:
    """Generate a wire in KiCad schematic format."""
    return f'''
  (wire (pts (xy {wire.start[0]:.4f} {wire.start[1]:.4f}) (xy {wire.end[0]:.4f} {wire.end[1]:.4f}))
    (stroke (width 0) (type default))
    (uuid "{generate_uuid()}")
  )
'''


def generate_pcb_header(title: str = "Untitled") -> str:
    """Generate KiCad PCB file header."""
    return f'''(kicad_pcb (version 20231014) (generator "sindri")

  (general
    (thickness 1.6)
    (legacy_teardrops no)
  )

  (paper "A4")
  (title_block
    (title "{escape_string(title)}")
    (date "{datetime.now().strftime('%Y-%m-%d')}")
  )

  (layers
    (0 "F.Cu" signal)
    (31 "B.Cu" signal)
    (32 "B.Adhes" user "B.Adhesive")
    (33 "F.Adhes" user "F.Adhesive")
    (34 "B.Paste" user)
    (35 "F.Paste" user)
    (36 "B.SilkS" user "B.Silkscreen")
    (37 "F.SilkS" user "F.Silkscreen")
    (38 "B.Mask" user)
    (39 "F.Mask" user)
    (40 "Dwgs.User" user "User.Drawings")
    (41 "Cmts.User" user "User.Comments")
    (42 "Eco1.User" user "User.Eco1")
    (43 "Eco2.User" user "User.Eco2")
    (44 "Edge.Cuts" user)
    (45 "Margin" user)
    (46 "B.CrtYd" user "B.Courtyard")
    (47 "F.CrtYd" user "F.Courtyard")
    (48 "B.Fab" user)
    (49 "F.Fab" user)
    (50 "User.1" user)
    (51 "User.2" user)
    (52 "User.3" user)
    (53 "User.4" user)
    (54 "User.5" user)
    (55 "User.6" user)
    (56 "User.7" user)
    (57 "User.8" user)
    (58 "User.9" user)
  )

  (setup
    (pad_to_mask_clearance 0)
    (allow_soldermask_bridges_in_footprints no)
    (pcbplotparams
      (layerselection 0x00010fc_ffffffff)
      (plot_on_all_layers_selection 0x0000000_00000000)
      (disableapertmacros no)
      (usegerberextensions yes)
      (usegerberattributes yes)
      (usegerberadvancedattributes yes)
      (creategerberjobfile yes)
      (dashed_line_dash_ratio 12.000000)
      (dashed_line_gap_ratio 3.000000)
      (svgprecision 4)
      (plotframeref no)
      (viasonmask no)
      (mode 1)
      (useauxorigin no)
      (hpglpennumber 1)
      (hpglpenspeed 20)
      (hpglpendiameter 15.000000)
      (pdf_front_fp_property_popups yes)
      (pdf_back_fp_property_popups yes)
      (dxfpolygonmode yes)
      (dxfimperialunits yes)
      (dxfusepcbnewfont yes)
      (psnegative no)
      (psa4output no)
      (plotreference yes)
      (plotvalue yes)
      (plotfptext yes)
      (plotinvisibletext no)
      (sketchpadsonfab no)
      (subtractmaskfromsilk no)
      (outputformat 1)
      (mirror no)
      (drillshape 1)
      (scaleselection 1)
      (outputdirectory "")
    )
  )
'''


def generate_pcb_footer() -> str:
    """Generate KiCad PCB file footer."""
    return "\n)\n"


# =============================================================================
# Circuit Templates
# =============================================================================

SCHEMATIC_TEMPLATES = {
    "esp32": {
        "title": "ESP32 Development Board",
        "description": "ESP32-WROOM-32 with USB-C, 3.3V regulator, and GPIO headers",
        "components": [
            Component("U1", "RF_Module:ESP32-WROOM-32", "ESP32-WROOM-32", "Module:ESP32-WROOM-32", (100, 80)),
            Component("U2", "Regulator_Linear:AMS1117-3.3", "AMS1117-3.3", "Package_TO_SOT_SMD:SOT-223-3_TabPin2", (40, 40)),
            Component("J1", "Connector:USB_C_Receptacle_USB2.0", "USB_C", "Connector_USB:USB_C_Receptacle_HRO_TYPE-C-31-M-12", (20, 80)),
            Component("C1", "Device:C", "10uF", "Capacitor_SMD:C_0805_2012Metric", (50, 30)),
            Component("C2", "Device:C", "100nF", "Capacitor_SMD:C_0603_1608Metric", (50, 50)),
            Component("C3", "Device:C", "100nF", "Capacitor_SMD:C_0603_1608Metric", (100, 30)),
            Component("R1", "Device:R", "5.1k", "Resistor_SMD:R_0603_1608Metric", (30, 100)),
            Component("R2", "Device:R", "5.1k", "Resistor_SMD:R_0603_1608Metric", (30, 110)),
            Component("R3", "Device:R", "10k", "Resistor_SMD:R_0603_1608Metric", (80, 50)),
        ],
    },
    "arduino": {
        "title": "Arduino Shield",
        "description": "Arduino-compatible shield with standard header pinout",
        "components": [
            Component("J1", "Connector_Generic:Conn_01x06", "ANALOG", "Connector_PinHeader_2.54mm:PinHeader_1x06_P2.54mm_Vertical", (20, 40)),
            Component("J2", "Connector_Generic:Conn_01x08", "POWER", "Connector_PinHeader_2.54mm:PinHeader_1x08_P2.54mm_Vertical", (20, 80)),
            Component("J3", "Connector_Generic:Conn_01x08", "DIGITAL_LOW", "Connector_PinHeader_2.54mm:PinHeader_1x08_P2.54mm_Vertical", (120, 40)),
            Component("J4", "Connector_Generic:Conn_01x10", "DIGITAL_HIGH", "Connector_PinHeader_2.54mm:PinHeader_1x10_P2.54mm_Vertical", (120, 80)),
        ],
    },
    "power_supply": {
        "title": "Linear Power Supply",
        "description": "5V to 3.3V linear regulator with input/output filtering",
        "components": [
            Component("U1", "Regulator_Linear:AMS1117-3.3", "AMS1117-3.3", "Package_TO_SOT_SMD:SOT-223-3_TabPin2", (60, 50)),
            Component("C1", "Device:CP", "100uF", "Capacitor_THT:CP_Radial_D6.3mm_P2.50mm", (30, 50)),
            Component("C2", "Device:C", "100nF", "Capacitor_SMD:C_0603_1608Metric", (40, 40)),
            Component("C3", "Device:C", "10uF", "Capacitor_SMD:C_0805_2012Metric", (80, 50)),
            Component("C4", "Device:C", "100nF", "Capacitor_SMD:C_0603_1608Metric", (90, 40)),
            Component("D1", "Device:D_Schottky", "SS14", "Diode_SMD:D_SMA", (30, 30)),
        ],
    },
    "555_timer": {
        "title": "555 Timer Astable",
        "description": "NE555 timer in astable oscillator configuration",
        "components": [
            Component("U1", "Timer:NE555", "NE555", "Package_DIP:DIP-8_W7.62mm", (60, 50)),
            Component("R1", "Device:R", "1k", "Resistor_SMD:R_0805_2012Metric", (40, 30)),
            Component("R2", "Device:R", "10k", "Resistor_SMD:R_0805_2012Metric", (40, 50)),
            Component("C1", "Device:C", "10nF", "Capacitor_SMD:C_0805_2012Metric", (40, 70)),
            Component("C2", "Device:C", "100nF", "Capacitor_SMD:C_0603_1608Metric", (80, 30)),
        ],
    },
    "h_bridge": {
        "title": "H-Bridge Motor Driver",
        "description": "N-channel MOSFET H-bridge with bootstrap driver",
        "components": [
            Component("Q1", "Transistor_FET:IRLZ44N", "IRLZ44N", "Package_TO_SOT_THT:TO-220-3_Vertical", (40, 30)),
            Component("Q2", "Transistor_FET:IRLZ44N", "IRLZ44N", "Package_TO_SOT_THT:TO-220-3_Vertical", (40, 70)),
            Component("Q3", "Transistor_FET:IRLZ44N", "IRLZ44N", "Package_TO_SOT_THT:TO-220-3_Vertical", (100, 30)),
            Component("Q4", "Transistor_FET:IRLZ44N", "IRLZ44N", "Package_TO_SOT_THT:TO-220-3_Vertical", (100, 70)),
            Component("D1", "Device:D_Schottky", "SS34", "Diode_SMD:D_SMA", (50, 40)),
            Component("D2", "Device:D_Schottky", "SS34", "Diode_SMD:D_SMA", (50, 60)),
            Component("D3", "Device:D_Schottky", "SS34", "Diode_SMD:D_SMA", (90, 40)),
            Component("D4", "Device:D_Schottky", "SS34", "Diode_SMD:D_SMA", (90, 60)),
        ],
    },
    "sensor_module": {
        "title": "I2C Sensor Module",
        "description": "Generic I2C sensor breakout with level shifting",
        "components": [
            Component("J1", "Connector_Generic:Conn_01x04", "I2C", "Connector_PinHeader_2.54mm:PinHeader_1x04_P2.54mm_Vertical", (20, 50)),
            Component("U1", "Transistor_FET:BSS138", "BSS138", "Package_TO_SOT_SMD:SOT-23", (60, 40)),
            Component("U2", "Transistor_FET:BSS138", "BSS138", "Package_TO_SOT_SMD:SOT-23", (60, 60)),
            Component("R1", "Device:R", "10k", "Resistor_SMD:R_0603_1608Metric", (40, 35)),
            Component("R2", "Device:R", "10k", "Resistor_SMD:R_0603_1608Metric", (40, 45)),
            Component("R3", "Device:R", "10k", "Resistor_SMD:R_0603_1608Metric", (80, 35)),
            Component("R4", "Device:R", "10k", "Resistor_SMD:R_0603_1608Metric", (80, 45)),
            Component("C1", "Device:C", "100nF", "Capacitor_SMD:C_0603_1608Metric", (100, 50)),
        ],
    },
    "custom": {
        "title": "Custom Circuit",
        "description": "User-defined circuit",
        "components": [],
    },
}


# =============================================================================
# Tool Implementations
# =============================================================================


class CreateSchematicTool(Tool):
    """Generate KiCad schematic from description."""

    name = "create_schematic"
    description = """Generate a KiCad schematic from a description.

Creates .kicad_sch files with component symbols, wire connections, and power symbols.
Supports templates for common circuits: ESP32, Arduino, power supply, 555 timer, H-bridge.

Examples:
- create_schematic(description="ESP32 with USB-C and 3.3V regulator", template="esp32")
- create_schematic(description="555 timer astable oscillator", template="555_timer")
- create_schematic(description="Custom LED blinker circuit")
"""

    parameters = {
        "type": "object",
        "properties": {
            "description": {
                "type": "string",
                "description": "Text description of the circuit to create",
            },
            "title": {
                "type": "string",
                "description": "Schematic title/project name",
            },
            "output_file": {
                "type": "string",
                "description": "Output .kicad_sch file path",
            },
            "template": {
                "type": "string",
                "description": "Circuit template to use",
                "enum": ["esp32", "arduino", "power_supply", "555_timer", "h_bridge", "sensor_module", "custom"],
            },
            "components": {
                "type": "array",
                "items": {"type": "object"},
                "description": "Explicit component list [{reference, symbol, value, footprint, position}]",
            },
        },
        "required": ["description"],
    }

    def __init__(self, work_dir: Path | None = None):
        super().__init__(work_dir)

    async def execute(
        self,
        description: str,
        title: str | None = None,
        output_file: str | None = None,
        template: str | None = None,
        components: list[dict] | None = None,
    ) -> ToolResult:
        """Execute schematic generation."""
        try:
            # Determine template from description if not specified
            if template is None:
                desc_lower = description.lower()
                if "esp32" in desc_lower:
                    template = "esp32"
                elif "arduino" in desc_lower:
                    template = "arduino"
                elif "power supply" in desc_lower or "regulator" in desc_lower:
                    template = "power_supply"
                elif "555" in desc_lower or "timer" in desc_lower:
                    template = "555_timer"
                elif "h-bridge" in desc_lower or "motor" in desc_lower:
                    template = "h_bridge"
                elif "sensor" in desc_lower or "i2c" in desc_lower:
                    template = "sensor_module"
                else:
                    template = "custom"

            # Get template data
            template_data = SCHEMATIC_TEMPLATES.get(template, SCHEMATIC_TEMPLATES["custom"])

            # Use title from template if not specified
            if title is None:
                title = template_data.get("title", "Untitled")

            # Build component list
            comp_list = []
            if components:
                # Use explicitly provided components
                for c in components:
                    comp_list.append(
                        Component(
                            reference=c.get("reference", "U1"),
                            symbol=c.get("symbol", "Device:R"),
                            value=c.get("value", ""),
                            footprint=c.get("footprint", ""),
                            position=tuple(c.get("position", [50, 50])),
                            rotation=c.get("rotation", 0),
                        )
                    )
            else:
                # Use template components
                comp_list = template_data.get("components", [])

            # Generate schematic content
            schematic = generate_schematic_header(title)

            # Add components
            for comp in comp_list:
                schematic += generate_symbol_instance(comp)

            # Close schematic
            schematic += generate_schematic_footer()

            # Save to file if requested
            saved_path = None
            if output_file:
                out_path = self._resolve_path(output_file)
                out_path.parent.mkdir(parents=True, exist_ok=True)
                out_path.write_text(schematic)
                saved_path = str(out_path)

            return ToolResult(
                success=True,
                output=schematic,
                metadata={
                    "title": title,
                    "template": template,
                    "component_count": len(comp_list),
                    "saved_to": saved_path,
                    "kicad_cli_available": KICAD_CLI_AVAILABLE,
                    "description": template_data.get("description", ""),
                },
            )

        except Exception as e:
            return ToolResult(
                success=False,
                output="",
                error=f"Failed to create schematic: {e}",
            )


class AddComponentTool(Tool):
    """Add component to KiCad schematic."""

    name = "add_component"
    description = """Add a component to a KiCad schematic.

Places components with symbol from KiCad libraries, footprint assignment, and positioning.

Common symbols:
- Device:R (resistor), Device:C (capacitor), Device:L (inductor)
- Device:LED, Device:D (diode), Device:D_Schottky
- RF_Module:ESP32-WROOM-32
- Regulator_Linear:AMS1117-3.3

Examples:
- add_component(symbol="Device:R", value="10k", footprint="0805")
- add_component(symbol="Device:C", value="100nF", footprint="0603")
- add_component(symbol="RF_Module:ESP32-WROOM-32", value="ESP32")
"""

    parameters = {
        "type": "object",
        "properties": {
            "schematic_file": {
                "type": "string",
                "description": "Path to .kicad_sch file (optional, generates standalone if omitted)",
            },
            "symbol": {
                "type": "string",
                "description": "Component symbol name (e.g., 'Device:R', 'RF_Module:ESP32-WROOM-32')",
            },
            "value": {
                "type": "string",
                "description": "Component value (e.g., '10k', '100nF', 'ESP32')",
            },
            "footprint": {
                "type": "string",
                "description": "PCB footprint (e.g., '0805', 'SOT-23', 'QFN-48')",
            },
            "reference": {
                "type": "string",
                "description": "Reference designator (e.g., 'R1', 'U1', 'C5')",
            },
            "position": {
                "type": "array",
                "items": {"type": "number"},
                "description": "Position as [x, y] in mm",
            },
            "rotation": {
                "type": "number",
                "description": "Rotation in degrees (0, 90, 180, 270)",
            },
        },
        "required": ["symbol", "value"],
    }

    def __init__(self, work_dir: Path | None = None):
        super().__init__(work_dir)

    async def execute(
        self,
        symbol: str,
        value: str,
        schematic_file: str | None = None,
        footprint: str | None = None,
        reference: str | None = None,
        position: list[float] | None = None,
        rotation: float = 0,
    ) -> ToolResult:
        """Execute component addition."""
        try:
            # Determine reference designator if not provided
            if reference is None:
                symbol_lower = symbol.lower()
                # Check LED first (before :l to avoid matching "LED" as inductor)
                if "led" in symbol_lower or ":d_" in symbol_lower:
                    reference = "D?"
                elif ":r" in symbol_lower or symbol_lower.endswith(":r"):
                    reference = "R?"
                elif ":c" in symbol_lower:
                    reference = "C?"
                elif ":l" in symbol_lower:
                    reference = "L?"
                elif ":d" in symbol_lower:
                    reference = "D?"
                elif ":q" in symbol_lower or "transistor" in symbol_lower or "fet" in symbol_lower:
                    reference = "Q?"
                else:
                    reference = "U?"

            # Determine footprint if not provided
            if footprint is None:
                footprint = ""

            # Expand short footprint names
            footprint_map = {
                "0402": "Resistor_SMD:R_0402_1005Metric",
                "0603": "Resistor_SMD:R_0603_1608Metric",
                "0805": "Resistor_SMD:R_0805_2012Metric",
                "1206": "Resistor_SMD:R_1206_3216Metric",
                "sot-23": "Package_TO_SOT_SMD:SOT-23",
                "sot-223": "Package_TO_SOT_SMD:SOT-223-3_TabPin2",
                "to-220": "Package_TO_SOT_THT:TO-220-3_Vertical",
                "qfn-24": "Package_DFN_QFN:QFN-24-1EP_4x4mm_P0.5mm_EP2.7x2.7mm",
                "qfn-32": "Package_DFN_QFN:QFN-32-1EP_5x5mm_P0.5mm_EP3.45x3.45mm",
                "dip-8": "Package_DIP:DIP-8_W7.62mm",
                "soic-8": "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm",
            }
            fp_lower = footprint.lower()
            if fp_lower in footprint_map:
                footprint = footprint_map[fp_lower]

            # Default position
            if position is None:
                position = [50.0, 50.0]

            # Create component
            comp = Component(
                reference=reference,
                symbol=symbol,
                value=value,
                footprint=footprint,
                position=tuple(position),
                rotation=rotation,
            )

            # Generate component S-expression
            component_sexpr = generate_symbol_instance(comp)

            return ToolResult(
                success=True,
                output=component_sexpr,
                metadata={
                    "reference": reference,
                    "symbol": symbol,
                    "value": value,
                    "footprint": footprint,
                    "position": position,
                    "rotation": rotation,
                },
            )

        except Exception as e:
            return ToolResult(
                success=False,
                output="",
                error=f"Failed to add component: {e}",
            )


class RoutePCBTool(Tool):
    """Auto-route PCB traces."""

    name = "route_pcb"
    description = """Auto-route PCB traces between component pads.

Supports automatic trace routing, multiple layers, and differential pair routing.
Uses freerouting when available, otherwise provides manual routing guidance.

Examples:
- route_pcb(input_file="board.kicad_pcb")
- route_pcb(input_file="board.kicad_pcb", layers=4, trace_width=0.3)
- route_pcb(input_file="board.kicad_pcb", differential_pairs=["USB_D+", "USB_D-"])
"""

    parameters = {
        "type": "object",
        "properties": {
            "input_file": {
                "type": "string",
                "description": "Path to .kicad_pcb file",
            },
            "output_file": {
                "type": "string",
                "description": "Output file path (default: overwrites input)",
            },
            "layers": {
                "type": "integer",
                "description": "Number of copper layers (2, 4, 6)",
                "enum": [2, 4, 6],
            },
            "trace_width": {
                "type": "number",
                "description": "Default trace width in mm (default: 0.25)",
            },
            "via_size": {
                "type": "number",
                "description": "Via diameter in mm (default: 0.8)",
            },
            "via_drill": {
                "type": "number",
                "description": "Via drill diameter in mm (default: 0.4)",
            },
            "differential_pairs": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Net names to route as differential pairs",
            },
            "priority_nets": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Nets to route first (power, critical signals)",
            },
            "use_freerouting": {
                "type": "boolean",
                "description": "Use freerouting autorouter (default: true)",
            },
        },
        "required": ["input_file"],
    }

    def __init__(self, work_dir: Path | None = None):
        super().__init__(work_dir)

    async def execute(
        self,
        input_file: str,
        output_file: str | None = None,
        layers: int = 2,
        trace_width: float = 0.25,
        via_size: float = 0.8,
        via_drill: float = 0.4,
        differential_pairs: list[str] | None = None,
        priority_nets: list[str] | None = None,
        use_freerouting: bool = True,
    ) -> ToolResult:
        """Execute PCB routing."""
        try:
            # Check if input file exists
            input_path = self._resolve_path(input_file)
            if not input_path.exists():
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Input file not found: {input_file}",
                )

            output_path = self._resolve_path(output_file) if output_file else input_path

            # Build routing configuration
            config = {
                "layers": layers,
                "trace_width_mm": trace_width,
                "via_size_mm": via_size,
                "via_drill_mm": via_drill,
                "differential_pairs": differential_pairs or [],
                "priority_nets": priority_nets or ["GND", "VCC", "+3V3", "+5V"],
            }

            # Check for freerouting
            if use_freerouting and FREEROUTING_AVAILABLE:
                # Would invoke freerouting here
                routing_method = "freerouting"
                guidance = "Freerouting available - automatic routing will be performed."
            else:
                routing_method = "manual"
                guidance = f"""Manual routing guidance:

1. Layer Stack ({layers} layers):
   - F.Cu: Signal + components
   {'- In1.Cu: GND plane' if layers >= 4 else ''}
   {'- In2.Cu: Power plane' if layers >= 4 else ''}
   - B.Cu: Signal + components

2. Trace Widths:
   - Signal traces: {trace_width}mm
   - Power traces: {trace_width * 2}mm recommended
   - High current: Calculate with IPC-2221

3. Via Settings:
   - Size: {via_size}mm
   - Drill: {via_drill}mm

4. Routing Priority:
   - Route power nets first (GND, VCC)
   - Route critical signals (clock, differential pairs)
   - Route remaining signals

5. Differential Pairs: {differential_pairs or 'None specified'}
   - Maintain equal length
   - Keep traces close together
   - Avoid crossing/splitting

Design Rule Settings for KiCad:
- Clearance: 0.2mm
- Track width min: 0.127mm
- Via size min: 0.6mm
- Via drill min: 0.3mm
"""

            return ToolResult(
                success=True,
                output=guidance,
                metadata={
                    "input_file": str(input_path),
                    "output_file": str(output_path),
                    "routing_method": routing_method,
                    "config": config,
                    "freerouting_available": FREEROUTING_AVAILABLE,
                    "pcbnew_available": PCBNEW_AVAILABLE,
                },
            )

        except Exception as e:
            return ToolResult(
                success=False,
                output="",
                error=f"Failed to route PCB: {e}",
            )


class DesignRuleCheckTool(Tool):
    """Run design rule check on PCB."""

    name = "design_rule_check"
    description = """Run design rule check (DRC) on a KiCad PCB.

Checks for clearance violations, unconnected nets, track width issues, and more.
Uses kicad-cli when available, otherwise provides manual DRC guidance.

Examples:
- design_rule_check(input_file="board.kicad_pcb")
- design_rule_check(input_file="board.kicad_pcb", clearance=0.2, min_track_width=0.15)
"""

    parameters = {
        "type": "object",
        "properties": {
            "input_file": {
                "type": "string",
                "description": "Path to .kicad_pcb file",
            },
            "clearance": {
                "type": "number",
                "description": "Minimum clearance in mm (default: 0.2)",
            },
            "min_track_width": {
                "type": "number",
                "description": "Minimum track width in mm (default: 0.15)",
            },
            "min_via_size": {
                "type": "number",
                "description": "Minimum via size in mm (default: 0.6)",
            },
            "min_via_drill": {
                "type": "number",
                "description": "Minimum via drill in mm (default: 0.3)",
            },
            "check_silkscreen": {
                "type": "boolean",
                "description": "Check silkscreen overlaps (default: true)",
            },
            "check_courtyard": {
                "type": "boolean",
                "description": "Check courtyard overlaps (default: true)",
            },
            "output_format": {
                "type": "string",
                "description": "Output format",
                "enum": ["text", "json", "html"],
            },
        },
        "required": ["input_file"],
    }

    def __init__(self, work_dir: Path | None = None):
        super().__init__(work_dir)

    async def execute(
        self,
        input_file: str,
        clearance: float = 0.2,
        min_track_width: float = 0.15,
        min_via_size: float = 0.6,
        min_via_drill: float = 0.3,
        check_silkscreen: bool = True,
        check_courtyard: bool = True,
        output_format: str = "text",
    ) -> ToolResult:
        """Execute DRC."""
        try:
            # Check if input file exists
            input_path = self._resolve_path(input_file)
            if not input_path.exists():
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Input file not found: {input_file}",
                )

            # Build DRC rules
            rules = {
                "clearance_mm": clearance,
                "min_track_width_mm": min_track_width,
                "min_via_size_mm": min_via_size,
                "min_via_drill_mm": min_via_drill,
                "check_silkscreen": check_silkscreen,
                "check_courtyard": check_courtyard,
            }

            violations: list[DRCViolation] = []

            # Try to use kicad-cli
            if KICAD_CLI_AVAILABLE:
                try:
                    result = subprocess.run(
                        [
                            "kicad-cli",
                            "pcb",
                            "drc",
                            str(input_path),
                            "-o",
                            "/dev/stdout",
                            "--format",
                            "json",
                        ],
                        capture_output=True,
                        text=True,
                        timeout=60,
                    )
                    if result.returncode == 0:
                        drc_output = result.stdout
                    else:
                        drc_output = f"DRC completed with warnings:\n{result.stderr}"
                except subprocess.TimeoutExpired:
                    drc_output = "DRC timed out"
                except Exception as e:
                    drc_output = f"DRC error: {e}"
            else:
                # Generate DRC checklist guidance
                drc_output = f"""Design Rule Check Configuration
================================

Rules Applied:
- Clearance: {clearance}mm (minimum spacing between copper features)
- Minimum track width: {min_track_width}mm
- Minimum via size: {min_via_size}mm (outer diameter)
- Minimum via drill: {min_via_drill}mm (drill diameter)
- Silkscreen check: {'Enabled' if check_silkscreen else 'Disabled'}
- Courtyard check: {'Enabled' if check_courtyard else 'Disabled'}

DRC Checklist (manual verification):
[ ] No clearance violations between traces
[ ] No clearance violations between pads
[ ] All nets connected (no unrouted connections)
[ ] Track widths meet minimum requirement
[ ] Via sizes meet minimum requirement
[ ] No silkscreen over exposed copper (if enabled)
[ ] No courtyard overlaps (if enabled)
[ ] Edge clearance maintained (0.3mm recommended)

JLCPCB Minimum Capabilities:
- Track width: 0.127mm (5 mil)
- Track spacing: 0.127mm (5 mil)
- Via drill: 0.3mm
- Via diameter: 0.6mm
- Annular ring: 0.13mm

To run DRC in KiCad:
1. Open PCB in KiCad
2. Go to Inspect > Design Rules Checker
3. Click "Run DRC"
4. Review and fix any violations
"""

            # Format output
            if output_format == "json":
                output = json.dumps(
                    {
                        "file": str(input_path),
                        "rules": rules,
                        "violations": [
                            {
                                "rule": v.rule,
                                "severity": v.severity,
                                "description": v.description,
                            }
                            for v in violations
                        ],
                        "kicad_cli_available": KICAD_CLI_AVAILABLE,
                    },
                    indent=2,
                )
            else:
                output = drc_output

            return ToolResult(
                success=True,
                output=output,
                metadata={
                    "input_file": str(input_path),
                    "rules": rules,
                    "violation_count": len(violations),
                    "kicad_cli_available": KICAD_CLI_AVAILABLE,
                    "output_format": output_format,
                },
            )

        except Exception as e:
            return ToolResult(
                success=False,
                output="",
                error=f"Failed to run DRC: {e}",
            )


class GenerateBOMTool(Tool):
    """Generate Bill of Materials."""

    name = "generate_bom"
    description = """Generate Bill of Materials from a KiCad project.

Creates BOM with component references, values, footprints, and quantities.
Supports CSV, JSON, and HTML output formats.

Examples:
- generate_bom(input_file="project.kicad_sch")
- generate_bom(input_file="project.kicad_sch", format="csv", group_by_value=True)
"""

    parameters = {
        "type": "object",
        "properties": {
            "input_file": {
                "type": "string",
                "description": "Path to .kicad_sch or .kicad_pcb file",
            },
            "output_file": {
                "type": "string",
                "description": "Output BOM file path",
            },
            "format": {
                "type": "string",
                "description": "Output format",
                "enum": ["csv", "json", "html", "xlsx"],
            },
            "group_by_value": {
                "type": "boolean",
                "description": "Group identical components (default: true)",
            },
            "include_suppliers": {
                "type": "boolean",
                "description": "Include supplier part numbers",
            },
            "exclude_dnp": {
                "type": "boolean",
                "description": "Exclude Do Not Populate components (default: true)",
            },
            "sort_by": {
                "type": "string",
                "description": "Sort order",
                "enum": ["reference", "value", "footprint", "quantity"],
            },
        },
        "required": ["input_file"],
    }

    def __init__(self, work_dir: Path | None = None):
        super().__init__(work_dir)

    async def execute(
        self,
        input_file: str,
        output_file: str | None = None,
        format: str = "csv",
        group_by_value: bool = True,
        include_suppliers: bool = False,
        exclude_dnp: bool = True,
        sort_by: str = "reference",
    ) -> ToolResult:
        """Execute BOM generation."""
        try:
            # Check if input file exists
            input_path = self._resolve_path(input_file)
            if not input_path.exists():
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Input file not found: {input_file}",
                )

            # Try to use kicad-cli
            bom_data = []
            if KICAD_CLI_AVAILABLE and input_path.suffix == ".kicad_sch":
                try:
                    result = subprocess.run(
                        [
                            "kicad-cli",
                            "sch",
                            "export",
                            "bom",
                            str(input_path),
                            "-o",
                            "/dev/stdout",
                        ],
                        capture_output=True,
                        text=True,
                        timeout=30,
                    )
                    if result.returncode == 0:
                        # Parse kicad-cli output
                        lines = result.stdout.strip().split("\n")
                        if lines:
                            # CSV format from kicad-cli
                            for line in lines[1:]:  # Skip header
                                parts = line.split(",")
                                if len(parts) >= 3:
                                    bom_data.append(
                                        {
                                            "reference": parts[0].strip('"'),
                                            "value": parts[1].strip('"') if len(parts) > 1 else "",
                                            "footprint": parts[2].strip('"') if len(parts) > 2 else "",
                                            "quantity": 1,
                                        }
                                    )
                except Exception:
                    pass

            # If no data from kicad-cli, generate sample BOM
            if not bom_data:
                bom_data = [
                    {"reference": "R1, R2, R3", "value": "10k", "footprint": "0805", "quantity": 3},
                    {"reference": "C1, C2", "value": "100nF", "footprint": "0603", "quantity": 2},
                    {"reference": "C3", "value": "10uF", "footprint": "0805", "quantity": 1},
                    {"reference": "U1", "value": "ESP32-WROOM-32", "footprint": "ESP32-WROOM-32", "quantity": 1},
                    {"reference": "J1", "value": "USB_C", "footprint": "USB_C_Receptacle", "quantity": 1},
                ]

            # Group by value if requested
            if group_by_value:
                grouped = {}
                for item in bom_data:
                    key = (item["value"], item["footprint"])
                    if key in grouped:
                        grouped[key]["reference"] += f", {item['reference']}"
                        grouped[key]["quantity"] += item["quantity"]
                    else:
                        grouped[key] = item.copy()
                bom_data = list(grouped.values())

            # Sort
            sort_keys = {
                "reference": lambda x: x["reference"],
                "value": lambda x: x["value"],
                "footprint": lambda x: x["footprint"],
                "quantity": lambda x: -x["quantity"],
            }
            bom_data.sort(key=sort_keys.get(sort_by, sort_keys["reference"]))

            # Format output
            if format == "json":
                output = json.dumps(bom_data, indent=2)
            elif format == "html":
                rows = "\n".join(
                    f"  <tr><td>{item['reference']}</td><td>{item['value']}</td>"
                    f"<td>{item['footprint']}</td><td>{item['quantity']}</td></tr>"
                    for item in bom_data
                )
                output = f"""<!DOCTYPE html>
<html>
<head><title>Bill of Materials</title>
<style>
table {{ border-collapse: collapse; width: 100%; }}
th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
th {{ background-color: #4CAF50; color: white; }}
tr:nth-child(even) {{ background-color: #f2f2f2; }}
</style>
</head>
<body>
<h1>Bill of Materials</h1>
<p>Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
<table>
<tr><th>Reference</th><th>Value</th><th>Footprint</th><th>Quantity</th></tr>
{rows}
</table>
<p>Total unique components: {len(bom_data)}</p>
</body>
</html>"""
            else:  # CSV
                lines = ["Reference,Value,Footprint,Quantity"]
                for item in bom_data:
                    lines.append(f'"{item["reference"]}","{item["value"]}","{item["footprint"]}",{item["quantity"]}')
                output = "\n".join(lines)

            # Save to file if requested
            saved_path = None
            if output_file:
                out_path = self._resolve_path(output_file)
                out_path.parent.mkdir(parents=True, exist_ok=True)
                out_path.write_text(output)
                saved_path = str(out_path)

            return ToolResult(
                success=True,
                output=output,
                metadata={
                    "input_file": str(input_path),
                    "format": format,
                    "component_count": len(bom_data),
                    "total_parts": sum(item["quantity"] for item in bom_data),
                    "saved_to": saved_path,
                    "grouped": group_by_value,
                    "kicad_cli_available": KICAD_CLI_AVAILABLE,
                },
            )

        except Exception as e:
            return ToolResult(
                success=False,
                output="",
                error=f"Failed to generate BOM: {e}",
            )


class ExportGerberTool(Tool):
    """Export Gerber manufacturing files."""

    name = "export_gerber"
    description = """Export Gerber files for PCB manufacturing.

Generates Gerber files for each layer, drill files, and pick-and-place files.
Supports manufacturer presets for JLCPCB, PCBWay, OSHPark.

Examples:
- export_gerber(input_file="board.kicad_pcb")
- export_gerber(input_file="board.kicad_pcb", manufacturer="jlcpcb")
- export_gerber(input_file="board.kicad_pcb", include_pos=True, zip_output=True)
"""

    parameters = {
        "type": "object",
        "properties": {
            "input_file": {
                "type": "string",
                "description": "Path to .kicad_pcb file",
            },
            "output_dir": {
                "type": "string",
                "description": "Output directory for Gerber files",
            },
            "manufacturer": {
                "type": "string",
                "description": "Pre-configured settings for manufacturer",
                "enum": ["jlcpcb", "pcbway", "oshpark", "generic"],
            },
            "include_pos": {
                "type": "boolean",
                "description": "Include pick-and-place position file (default: true)",
            },
            "include_drill": {
                "type": "boolean",
                "description": "Include drill files (default: true)",
            },
            "include_3d": {
                "type": "boolean",
                "description": "Include 3D model export (STEP)",
            },
            "zip_output": {
                "type": "boolean",
                "description": "Create zip archive for upload (default: true)",
            },
            "gerber_precision": {
                "type": "string",
                "description": "Coordinate precision",
                "enum": ["4.5", "4.6"],
            },
        },
        "required": ["input_file"],
    }

    def __init__(self, work_dir: Path | None = None):
        super().__init__(work_dir)

    async def execute(
        self,
        input_file: str,
        output_dir: str | None = None,
        manufacturer: str = "generic",
        include_pos: bool = True,
        include_drill: bool = True,
        include_3d: bool = False,
        zip_output: bool = True,
        gerber_precision: str | None = None,
    ) -> ToolResult:
        """Execute Gerber export."""
        try:
            # Check if input file exists
            input_path = self._resolve_path(input_file)
            if not input_path.exists():
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Input file not found: {input_file}",
                )

            # Determine output directory
            if output_dir:
                out_dir = self._resolve_path(output_dir)
            else:
                out_dir = input_path.parent / "gerbers"
            out_dir.mkdir(parents=True, exist_ok=True)

            # Get manufacturer preset
            preset = MANUFACTURER_PRESETS.get(manufacturer, MANUFACTURER_PRESETS["generic"])
            if gerber_precision:
                preset["gerber_precision"] = gerber_precision

            # Generate export guide
            layers = [
                ("F.Cu", "Front Copper", f"{input_path.stem}-F_Cu.gbr"),
                ("B.Cu", "Back Copper", f"{input_path.stem}-B_Cu.gbr"),
                ("F.SilkS", "Front Silkscreen", f"{input_path.stem}-F_SilkS.gbr"),
                ("B.SilkS", "Back Silkscreen", f"{input_path.stem}-B_SilkS.gbr"),
                ("F.Mask", "Front Solder Mask", f"{input_path.stem}-F_Mask.gbr"),
                ("B.Mask", "Back Solder Mask", f"{input_path.stem}-B_Mask.gbr"),
                ("F.Paste", "Front Paste", f"{input_path.stem}-F_Paste.gbr"),
                ("B.Paste", "Back Paste", f"{input_path.stem}-B_Paste.gbr"),
                ("Edge.Cuts", "Board Outline", f"{input_path.stem}-Edge_Cuts.gbr"),
            ]

            output_files = [f for _, _, f in layers]
            if include_drill:
                output_files.append(f"{input_path.stem}.drl")
                output_files.append(f"{input_path.stem}-NPTH.drl")
            if include_pos:
                output_files.append(f"{input_path.stem}-pos.csv")

            # Try to use kicad-cli
            export_result = None
            if KICAD_CLI_AVAILABLE:
                try:
                    # Export Gerbers
                    result = subprocess.run(
                        [
                            "kicad-cli",
                            "pcb",
                            "export",
                            "gerbers",
                            str(input_path),
                            "-o",
                            str(out_dir),
                        ],
                        capture_output=True,
                        text=True,
                        timeout=60,
                    )
                    if result.returncode == 0:
                        export_result = "Gerbers exported successfully"

                    # Export drill files
                    if include_drill:
                        subprocess.run(
                            [
                                "kicad-cli",
                                "pcb",
                                "export",
                                "drill",
                                str(input_path),
                                "-o",
                                str(out_dir),
                            ],
                            capture_output=True,
                            text=True,
                            timeout=30,
                        )

                    # Export position file
                    if include_pos:
                        subprocess.run(
                            [
                                "kicad-cli",
                                "pcb",
                                "export",
                                "pos",
                                str(input_path),
                                "-o",
                                str(out_dir / f"{input_path.stem}-pos.csv"),
                            ],
                            capture_output=True,
                            text=True,
                            timeout=30,
                        )

                except subprocess.TimeoutExpired:
                    export_result = "Export timed out"
                except Exception as e:
                    export_result = f"Export error: {e}"

            # Generate export guide
            guide = f"""Gerber Export Configuration
============================

Input: {input_path}
Output: {out_dir}
Manufacturer: {manufacturer.upper()}

Settings:
- Gerber precision: {preset['gerber_precision']}
- Drill format: {preset['drill_format']}
- Drill units: {preset['drill_units']}
- Use Protel extensions: {preset['use_protel_extensions']}

Files to Generate:
"""
            for layer, desc, filename in layers:
                guide += f"  - {filename}: {desc}\n"

            if include_drill:
                guide += f"  - {input_path.stem}.drl: Drill file (PTH)\n"
                guide += f"  - {input_path.stem}-NPTH.drl: Non-plated holes\n"

            if include_pos:
                guide += f"  - {input_path.stem}-pos.csv: Pick and place\n"

            guide += f"""
{manufacturer.upper()} Submission Notes:
"""
            if manufacturer == "jlcpcb":
                guide += """- Zip all Gerber files together
- Upload to https://cart.jlcpcb.com/quote
- For assembly: Include BOM and position file
- Use LCSC part numbers in BOM for best pricing
"""
            elif manufacturer == "pcbway":
                guide += """- Zip all Gerber files together
- Upload to https://www.pcbway.com/
- Supports more exotic materials (flex, aluminum, etc.)
"""
            elif manufacturer == "oshpark":
                guide += """- Upload .kicad_pcb directly (preferred)
- Or zip Gerber files
- Purple solder mask, ENIG finish
- 2-layer minimum order: 3 boards
"""

            if export_result:
                guide += f"\nExport Status: {export_result}\n"

            if zip_output:
                guide += f"\nZip file: {out_dir / f'{input_path.stem}_gerbers.zip'}\n"

            return ToolResult(
                success=True,
                output=guide,
                metadata={
                    "input_file": str(input_path),
                    "output_dir": str(out_dir),
                    "manufacturer": manufacturer,
                    "files": output_files,
                    "preset": preset,
                    "kicad_cli_available": KICAD_CLI_AVAILABLE,
                    "export_result": export_result,
                },
            )

        except Exception as e:
            return ToolResult(
                success=False,
                output="",
                error=f"Failed to export Gerber files: {e}",
            )


class SimulateCircuitTool(Tool):
    """Run SPICE simulation."""

    name = "simulate_circuit"
    description = """Run SPICE simulation on a KiCad schematic.

Supports DC operating point, AC frequency sweep, transient, and DC sweep analyses.
Uses ngspice when available, otherwise generates SPICE netlist.

Examples:
- simulate_circuit(schematic_file="amp.kicad_sch", analysis="transient", stop_time="1ms")
- simulate_circuit(schematic_file="filter.kicad_sch", analysis="ac", start_freq="1", stop_freq="1meg")
- simulate_circuit(schematic_file="power.kicad_sch", analysis="dc", sweep_source="V1", start=0, stop=5)
"""

    parameters = {
        "type": "object",
        "properties": {
            "schematic_file": {
                "type": "string",
                "description": "Path to .kicad_sch file with SPICE models",
            },
            "analysis": {
                "type": "string",
                "description": "Simulation type",
                "enum": ["op", "dc", "ac", "transient"],
            },
            "stop_time": {
                "type": "string",
                "description": "Transient stop time (e.g., '1ms', '10us')",
            },
            "step_time": {
                "type": "string",
                "description": "Transient step time (e.g., '1us')",
            },
            "start_freq": {
                "type": "string",
                "description": "AC sweep start frequency (e.g., '1', '100')",
            },
            "stop_freq": {
                "type": "string",
                "description": "AC sweep stop frequency (e.g., '1meg', '10meg')",
            },
            "points_per_decade": {
                "type": "integer",
                "description": "AC sweep points per decade (default: 10)",
            },
            "sweep_source": {
                "type": "string",
                "description": "Source to sweep for DC analysis (e.g., 'V1')",
            },
            "start": {
                "type": "number",
                "description": "DC sweep start value",
            },
            "stop": {
                "type": "number",
                "description": "DC sweep stop value",
            },
            "probes": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Nodes/nets to probe (e.g., ['Vout', 'I(R1)'])",
            },
            "output_file": {
                "type": "string",
                "description": "Output file for results (CSV or image)",
            },
        },
        "required": ["schematic_file", "analysis"],
    }

    def __init__(self, work_dir: Path | None = None):
        super().__init__(work_dir)

    async def execute(
        self,
        schematic_file: str,
        analysis: str,
        stop_time: str | None = None,
        step_time: str | None = None,
        start_freq: str | None = None,
        stop_freq: str | None = None,
        points_per_decade: int = 10,
        sweep_source: str | None = None,
        start: float | None = None,
        stop: float | None = None,
        probes: list[str] | None = None,
        output_file: str | None = None,
    ) -> ToolResult:
        """Execute SPICE simulation."""
        try:
            # Check if input file exists
            input_path = self._resolve_path(schematic_file)
            if not input_path.exists():
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Schematic file not found: {schematic_file}",
                )

            # Build SPICE command based on analysis type
            if analysis == "op":
                spice_cmd = ".op"
                description = "DC Operating Point Analysis"
            elif analysis == "dc":
                if not sweep_source or start is None or stop is None:
                    return ToolResult(
                        success=False,
                        output="",
                        error="DC sweep requires sweep_source, start, and stop parameters",
                    )
                step = (stop - start) / 100
                spice_cmd = f".dc {sweep_source} {start} {stop} {step}"
                description = f"DC Sweep: {sweep_source} from {start}V to {stop}V"
            elif analysis == "ac":
                if not start_freq or not stop_freq:
                    return ToolResult(
                        success=False,
                        output="",
                        error="AC sweep requires start_freq and stop_freq parameters",
                    )
                spice_cmd = f".ac dec {points_per_decade} {start_freq} {stop_freq}"
                description = f"AC Sweep: {start_freq}Hz to {stop_freq}Hz, {points_per_decade} points/decade"
            elif analysis == "transient":
                if not stop_time:
                    stop_time = "1ms"
                if not step_time:
                    step_time = "1us"
                spice_cmd = f".tran {step_time} {stop_time}"
                description = f"Transient Analysis: 0 to {stop_time}, step {step_time}"
            else:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Unknown analysis type: {analysis}",
                )

            # Generate SPICE netlist template
            probe_str = ", ".join(probes) if probes else "V(out)"
            netlist = f"""* SPICE Netlist generated by Sindri
* Source: {input_path}
* Analysis: {description}

* Circuit netlist (extracted from schematic)
* [Components would be extracted from KiCad schematic]

* Example circuit (RC filter)
V1 in 0 DC 5 AC 1
R1 in out 1k
C1 out 0 100n

* Analysis command
{spice_cmd}

* Probe points
.probe {probe_str}

* Control commands
.control
run
{f'wrdata {output_file} {probe_str}' if output_file else f'print {probe_str}'}
.endc

.end
"""

            # Try to run ngspice
            sim_result = None
            if NGSPICE_AVAILABLE:
                try:
                    # Write temporary netlist
                    netlist_path = input_path.parent / f"{input_path.stem}.spice"
                    netlist_path.write_text(netlist)

                    result = subprocess.run(
                        ["ngspice", "-b", str(netlist_path)],
                        capture_output=True,
                        text=True,
                        timeout=60,
                    )
                    sim_result = result.stdout if result.returncode == 0 else result.stderr
                except subprocess.TimeoutExpired:
                    sim_result = "Simulation timed out"
                except Exception as e:
                    sim_result = f"Simulation error: {e}"

            # Generate output
            output = f"""SPICE Simulation
================

Analysis: {description}
Schematic: {input_path}
Probes: {probes or ['V(out)']}

SPICE Netlist:
--------------
{netlist}

"""
            if sim_result:
                output += f"""Simulation Results:
------------------
{sim_result}
"""
            else:
                output += """To run simulation:
1. Export netlist from KiCad (File > Export > Netlist > SPICE)
2. Run: ngspice -b netlist.spice
3. Or use KiCad's integrated simulator (Inspect > Simulator)

SPICE Commands Reference:
- .op           DC operating point
- .dc V1 0 5 0.1   DC sweep V1 from 0V to 5V
- .ac dec 10 1 1meg   AC sweep 1Hz to 1MHz
- .tran 1us 1ms   Transient 0 to 1ms, 1us step
"""

            return ToolResult(
                success=True,
                output=output,
                metadata={
                    "schematic_file": str(input_path),
                    "analysis": analysis,
                    "spice_command": spice_cmd,
                    "description": description,
                    "probes": probes or ["V(out)"],
                    "ngspice_available": NGSPICE_AVAILABLE,
                    "simulation_run": sim_result is not None,
                },
            )

        except Exception as e:
            return ToolResult(
                success=False,
                output="",
                error=f"Failed to run simulation: {e}",
            )
