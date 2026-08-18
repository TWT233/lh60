import unittest
from unittest import mock


class ConnectorSymbolContractTest(unittest.TestCase):
    def specs(self):
        from tools.lh60_design.core_library import core_symbol_specs

        return {
            symbol.name: symbol
            for symbol in core_symbol_specs()
            if symbol.name.startswith("Conn_01x")
        }

    def test_connector_symbols_use_j_prefix_and_left_side_sequential_passive_pins(self):
        symbols = self.specs()

        self.assertEqual(set(symbols), {"Conn_01x03", "Conn_01x04", "Conn_01x05"})
        for count, name in ((3, "Conn_01x03"), (4, "Conn_01x04"), (5, "Conn_01x05")):
            symbol = symbols[name]
            with self.subTest(symbol=name):
                self.assertEqual(symbol.reference_prefix, "J")
                self.assertEqual(symbol.value, name)
                self.assertEqual(len(symbol.pins), count)
                self.assertEqual(
                    [(pin.number, pin.name, pin.pin_type) for pin in symbol.pins],
                    [(str(index), str(index), "passive") for index in range(1, count + 1)],
                )
                self.assertEqual(
                    [(pin.x, pin.y, pin.angle) for pin in symbol.pins],
                    [
                        (-5.08, index * 2.54, 0.0)
                        for index in range(count)
                    ],
                )


class ConnectorFootprintContractTest(unittest.TestCase):
    def specs(self):
        from tools.lh60_design.core_library import core_footprint_specs

        return {
            footprint.name: footprint
            for footprint in core_footprint_specs()
            if footprint.name.startswith("PinHeader_1x")
        }

    def test_connector_footprints_match_exact_tht_pad_contract(self):
        specs = self.specs()

        self.assertEqual(
            set(specs),
            {
                "PinHeader_1x03_P2.54mm_Vertical",
                "PinHeader_1x04_P2.54mm_Vertical",
                "PinHeader_1x05_P2.54mm_Vertical",
            },
        )
        for count, name in (
            (3, "PinHeader_1x03_P2.54mm_Vertical"),
            (4, "PinHeader_1x04_P2.54mm_Vertical"),
            (5, "PinHeader_1x05_P2.54mm_Vertical"),
        ):
            footprint = specs[name]
            with self.subTest(footprint=name):
                self.assertEqual(footprint.body_width_mm, 2.54)
                self.assertEqual(footprint.body_height_mm, count * 2.54)
                self.assertEqual(footprint.courtyard_clearance_mm, 0.5)
                self.assertEqual(footprint.attributes, ("exclude_from_pos_files",))
                self.assertEqual(len(footprint.pads), count)
                self.assertEqual(
                    [
                        (
                            pad.number,
                            pad.pad_type,
                            pad.shape,
                            pad.x,
                            pad.y,
                            pad.width,
                            pad.height,
                            pad.layers,
                            pad.drill_mm,
                            pad.roundrect_rratio,
                        )
                        for pad in footprint.pads
                    ],
                    [
                        (
                            str(index),
                            "thru_hole",
                            "rect" if index == 1 else "circle",
                            0.0,
                            (index - 1) * 2.54,
                            1.7,
                            1.7,
                            ("*.Cu", "*.Mask"),
                            1.0,
                            None,
                        )
                        for index in range(1, count + 1)
                    ],
                )


class ConnectorPayloadContractTest(unittest.TestCase):
    def test_connector_graphics_match_exact_fab_courtyard_and_silkscreen_contract(self):
        from tools.lh60_design.core_library import _connector_graphics

        graphics = _connector_graphics(5)

        self.assertEqual(
            graphics["F.Fab"],
            [
                {
                    "type": "rect",
                    "start": {"x": -1.27, "y": -1.27},
                    "end": {"x": 1.27, "y": 11.43},
                    "stroke_width_mm": 0.1,
                    "fill": "none",
                }
            ],
        )
        self.assertEqual(
            graphics["F.CrtYd"],
            [
                {
                    "type": "rect",
                    "start": {"x": -1.77, "y": -1.77},
                    "end": {"x": 1.77, "y": 11.93},
                    "stroke_width_mm": 0.05,
                    "fill": "none",
                }
            ],
        )
        self.assertTrue(all(item["stroke_width_mm"] == 0.15 for item in graphics["F.SilkS"]))
        self.assertTrue(any(item["start"]["x"] == -2.2 for item in graphics["F.SilkS"]))

    def test_core_pad_payload_preserves_legacy_smd_behavior_and_optional_fields(self):
        from tools.lh60_design.core_library import CorePadSpec, _footprint_payload, CoreFootprintSpec

        legacy = CoreFootprintSpec(
            name="LegacyPad",
            description="legacy",
            pads=(
                CorePadSpec(
                    number="1",
                    pad_type="smd",
                    shape="rect",
                    x=1.0,
                    y=2.0,
                    width=3.0,
                    height=4.0,
                    layers=("F.Cu", "F.Paste", "F.Mask"),
                ),
            ),
            body_width_mm=1.0,
            body_height_mm=1.0,
            courtyard_clearance_mm=0.25,
            attributes=("smd",),
        )
        payload = _footprint_payload(legacy)

        self.assertEqual(
            payload["pads"],
            [
                {
                    "number": "1",
                    "type": "smd",
                    "shape": "rect",
                    "x": 1.0,
                    "y": 2.0,
                    "width": 3.0,
                    "height": 4.0,
                    "layers": ["F.Cu", "F.Paste", "F.Mask"],
                }
            ],
        )

    def test_core_pad_payload_emits_drill_and_roundrect_only_when_present(self):
        from tools.lh60_design.core_library import CorePadSpec, _footprint_payload, CoreFootprintSpec

        thru_hole = CoreFootprintSpec(
            name="ConnectorPad",
            description="connector",
            pads=(
                CorePadSpec(
                    number="1",
                    pad_type="thru_hole",
                    shape="rect",
                    x=0.0,
                    y=0.0,
                    width=1.7,
                    height=1.7,
                    layers=("*.Cu", "*.Mask"),
                    drill_mm=1.0,
                ),
                CorePadSpec(
                    number="2",
                    pad_type="smd",
                    shape="roundrect",
                    x=2.54,
                    y=0.0,
                    width=1.2,
                    height=1.8,
                    layers=("F.Cu", "F.Paste", "F.Mask"),
                    roundrect_rratio=0.2,
                ),
            ),
            body_width_mm=2.54,
            body_height_mm=5.08,
            courtyard_clearance_mm=0.5,
            attributes=("exclude_from_pos_files",),
        )
        payload = _footprint_payload(thru_hole)

        self.assertEqual(payload["pads"][0]["type"], "thru_hole")
        self.assertEqual(payload["pads"][0]["drill"], 1.0)
        self.assertNotIn("roundrect_rratio", payload["pads"][0])
        self.assertEqual(payload["pads"][1]["type"], "smd")
        self.assertEqual(payload["pads"][1]["roundrect_rratio"], 0.2)
        self.assertNotIn("drill", payload["pads"][1])


class RecordingClient:
    def __init__(self):
        self.schemas = []
        self.calls = []

    def tool_schemas(self, toolset):
        self.schemas.append(toolset)
        return {}

    def call_tool(self, name, arguments):
        self.calls.append((name, arguments))
        return {}


class ConnectorApplyPlanTest(unittest.TestCase):
    def _run_apply(self):
        from tools.lh60_design import core_library

        client = RecordingClient()
        with mock.patch.object(core_library, "_symbol_definition_count", return_value=0):
            core_library.apply_core_library(client)
        return client

    def test_apply_core_library_sends_exact_connector_create_payloads(self):
        from tools.lh60_design.core_library import FOOTPRINT_LIBRARY

        client = self._run_apply()
        create_calls = {
            call["name"]: call
            for tool, call in client.calls
            if tool == "create_footprint" and call["name"].startswith("PinHeader_1x")
        }

        self.assertEqual(
            set(create_calls),
            {
                "PinHeader_1x03_P2.54mm_Vertical",
                "PinHeader_1x04_P2.54mm_Vertical",
                "PinHeader_1x05_P2.54mm_Vertical",
            },
        )
        for count, name in (
            (3, "PinHeader_1x03_P2.54mm_Vertical"),
            (4, "PinHeader_1x04_P2.54mm_Vertical"),
            (5, "PinHeader_1x05_P2.54mm_Vertical"),
        ):
            with self.subTest(footprint=name):
                self.assertEqual(
                    create_calls[name],
                    {
                        "output": str(FOOTPRINT_LIBRARY / f"{name}.kicad_mod"),
                        "name": name,
                        "description": (
                            f"{count}-pin 2.54 mm vertical THT pin header; canonical "
                            "front-side library definition for hand soldering, "
                            "excluded from pick-and-place, retained in the BOM"
                        ),
                        "body_width": 2.54,
                        "body_height": count * 2.54,
                        "courtyard_clearance": 0.5,
                        "pads": [
                            {
                                "number": str(index),
                                "type": "thru_hole",
                                "shape": "rect" if index == 1 else "circle",
                                "x": 0.0,
                                "y": (index - 1) * 2.54,
                                "width": 1.7,
                                "height": 1.7,
                                "layers": ["*.Cu", "*.Mask"],
                                "drill": 1.0,
                            }
                            for index in range(1, count + 1)
                        ],
                    },
                )

    def test_apply_core_library_sends_only_front_side_connector_graphics(self):
        from tools.lh60_design.core_library import FOOTPRINT_LIBRARY, _connector_graphics

        client = self._run_apply()
        graphics_calls = [
            call
            for tool, call in client.calls
            if tool == "set_footprint_graphics"
            and "PinHeader_1x" in call["footprint_path"]
        ]

        self.assertEqual(len(graphics_calls), 9)
        seen = set()
        for count, name in (
            (3, "PinHeader_1x03_P2.54mm_Vertical"),
            (4, "PinHeader_1x04_P2.54mm_Vertical"),
            (5, "PinHeader_1x05_P2.54mm_Vertical"),
        ):
            footprint_path = str(FOOTPRINT_LIBRARY / f"{name}.kicad_mod")
            expected = _connector_graphics(count)
            for layer, graphics in expected.items():
                matches = [
                    call
                    for call in graphics_calls
                    if call["footprint_path"] == footprint_path
                    and call["selector"] == {"layer": layer}
                ]
                with self.subTest(footprint=name, layer=layer):
                    self.assertEqual(
                        matches,
                        [
                            {
                                "footprint_path": footprint_path,
                                "selector": {"layer": layer},
                                "mode": "replace",
                                "graphics": graphics,
                            }
                        ],
                    )
                    seen.add((footprint_path, layer))

        self.assertEqual(len(seen), 9)
        self.assertFalse(
            any(
                call["selector"]["layer"].startswith("B.")
                for call in graphics_calls
            )
        )

    def test_apply_core_library_sends_exact_connector_metadata_and_project_registration(self):
        from tools.lh60_design.core_library import FOOTPRINT_LIBRARY, PROJECT, SYMBOL_LIBRARY

        client = self._run_apply()
        metadata_calls = {
            call["footprint_path"]: call
            for tool, call in client.calls
            if tool == "set_footprint_metadata"
            and "PinHeader_1x" in call["footprint_path"]
        }

        self.assertEqual(
            set(metadata_calls),
            {
                str(FOOTPRINT_LIBRARY / "PinHeader_1x03_P2.54mm_Vertical.kicad_mod"),
                str(FOOTPRINT_LIBRARY / "PinHeader_1x04_P2.54mm_Vertical.kicad_mod"),
                str(FOOTPRINT_LIBRARY / "PinHeader_1x05_P2.54mm_Vertical.kicad_mod"),
            },
        )
        for count, name in (
            (3, "PinHeader_1x03_P2.54mm_Vertical"),
            (4, "PinHeader_1x04_P2.54mm_Vertical"),
            (5, "PinHeader_1x05_P2.54mm_Vertical"),
        ):
            with self.subTest(footprint=name):
                self.assertEqual(
                    metadata_calls[str(FOOTPRINT_LIBRARY / f"{name}.kicad_mod")],
                    {
                        "footprint_path": str(FOOTPRINT_LIBRARY / f"{name}.kicad_mod"),
                        "description": (
                            f"{count}-pin 2.54 mm vertical THT pin header; canonical "
                            "front-side library definition for hand soldering, "
                            "excluded from pick-and-place, retained in the BOM"
                        ),
                        "tags": ["lh60", "pin_header", "through_hole"],
                        "attributes": ["exclude_from_pos_files"],
                    },
                )

        register_calls = [
            (tool, call)
            for tool, call in client.calls
            if tool in {"register_symbol_library", "register_footprint_library"}
        ]
        self.assertEqual(
            register_calls,
            [
                (
                    "register_symbol_library",
                    {
                        "library_path": str(SYMBOL_LIBRARY),
                        "nickname": "lh60-core",
                        "project": str(PROJECT),
                        "scope": "project",
                    },
                ),
                (
                    "register_footprint_library",
                    {
                        "library_path": str(FOOTPRINT_LIBRARY),
                        "nickname": "lh60-core",
                        "project": str(PROJECT),
                        "scope": "project",
                        "replace_existing": True,
                    },
                ),
            ],
        )
        self.assertEqual(client.schemas, ["library"])


if __name__ == "__main__":
    unittest.main()
