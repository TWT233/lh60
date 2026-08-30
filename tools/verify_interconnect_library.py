import unittest
from pathlib import Path
import tempfile
from unittest import mock


class InterconnectSymbolContractTest(unittest.TestCase):
    def test_symbol_matches_frozen_c2856805_identity_and_passive_pinout(self):
        from tools.lh60_design.interconnect import DATASHEET_URL
        from tools.lh60_design.interconnect_library import interconnect_symbol_spec

        spec = interconnect_symbol_spec()

        self.assertEqual(spec.name, "FPC-05F-24PH20")
        self.assertEqual(spec.reference_prefix, "J")
        self.assertEqual(spec.value, "FPC-05F-24PH20")
        self.assertEqual(spec.manufacturer, "XUNPU")
        self.assertEqual(spec.mpn, "FPC-05F-24PH20")
        self.assertEqual(spec.lcsc_part, "C2856805")
        self.assertEqual(spec.datasheet_url, DATASHEET_URL)
        self.assertEqual(spec.footprint, "lh60-interconnect:FPC-05F-24PH20")
        self.assertEqual(len(spec.pins), 24)
        self.assertEqual(
            [(pin.number, pin.name, pin.pin_type) for pin in spec.pins],
            [(str(index), str(index), "passive") for index in range(1, 25)],
        )


class InterconnectFootprintContractTest(unittest.TestCase):
    def test_signal_and_hold_down_pads_match_c2856805(self):
        from tools.lh60_design.interconnect_library import interconnect_footprint_spec

        spec = interconnect_footprint_spec()
        signal = [pad for pad in spec.pads if pad.number]
        hold_downs = [pad for pad in spec.pads if not pad.number]
        self.assertEqual(len(signal), 24)
        self.assertEqual(
            [(pad.number, pad.x, pad.y, pad.width, pad.height) for pad in signal],
            [(str(index + 1), -5.75 + index * 0.5, 0.0, 0.30, 1.25) for index in range(24)],
        )
        self.assertEqual(
            [(pad.x, pad.y, pad.width, pad.height) for pad in hold_downs],
            [(-7.44, 2.575, 2.00, 2.50), (7.44, 2.575, 2.00, 2.50)],
        )

    def test_footprint_geometry_and_metadata_match_drawing(self):
        from tools.lh60_design.interconnect import DATASHEET_URL
        from tools.lh60_design.interconnect_library import interconnect_footprint_spec

        spec = interconnect_footprint_spec()

        self.assertEqual(spec.name, "FPC-05F-24PH20")
        self.assertIn("XUNPU FPC-05F-24PH20", spec.description)
        self.assertIn("C2856805", spec.description)
        self.assertEqual(spec.manufacturer, "XUNPU")
        self.assertEqual(spec.mpn, "FPC-05F-24PH20")
        self.assertEqual(spec.lcsc_part, "C2856805")
        self.assertEqual(spec.datasheet_url, DATASHEET_URL)
        self.assertEqual(spec.body_width_mm, 16.40)
        self.assertEqual(spec.body_depth_mm, 5.12)
        self.assertEqual(spec.body_height_mm, 2.00)
        self.assertEqual(spec.fab_min_x, -8.20)
        self.assertEqual(spec.fab_max_x, 8.20)
        self.assertEqual(spec.fab_min_y, 0.68)
        self.assertEqual(spec.fab_max_y, 5.80)
        self.assertEqual(spec.courtyard_clearance_mm, 0.25)
        self.assertEqual(spec.mouth_direction, "+Y")
        self.assertEqual(spec.pin1_top_view, "leftmost signal pad")
        self.assertEqual(spec.attributes, ("smd",))
        self.assertEqual(spec.tags, ("lh60", "ffc", "fpc", "xunpu", "c2856805"))
        self.assertIsNone(spec.step_model)
        self.assertEqual(
            {pad.layers for pad in spec.pads},
            {("F.Cu", "F.Paste", "F.Mask")},
        )
        self.assertEqual([pad.number for pad in spec.pads[-2:]], ["", ""])
        self.assertNotIn("25", [pad.number for pad in spec.pads])
        self.assertNotIn("26", [pad.number for pad in spec.pads])

    def test_courtyard_encloses_body_and_lands_with_clearance(self):
        from tools.lh60_design.interconnect_library import (
            interconnect_footprint_spec,
            interconnect_graphics_by_layer,
        )

        spec = interconnect_footprint_spec()
        graphics = interconnect_graphics_by_layer()
        courtyard = graphics["F.CrtYd"]

        self.assertEqual(
            courtyard,
            [
                {
                    "type": "rect",
                    "start": {"x": -8.69, "y": -0.875},
                    "end": {"x": 8.69, "y": 6.05},
                    "stroke_width_mm": 0.05,
                    "fill": "none",
                }
            ],
        )
        left = min(pad.x - pad.width / 2 for pad in spec.pads)
        right = max(pad.x + pad.width / 2 for pad in spec.pads)
        bottom = min(pad.y - pad.height / 2 for pad in spec.pads)
        top = max(pad.y + pad.height / 2 for pad in spec.pads)
        self.assertAlmostEqual(courtyard[0]["start"]["x"], min(left, spec.fab_min_x) - 0.25)
        self.assertAlmostEqual(courtyard[0]["end"]["x"], max(right, spec.fab_max_x) + 0.25)
        self.assertAlmostEqual(courtyard[0]["start"]["y"], min(bottom, spec.fab_min_y) - 0.25)
        self.assertAlmostEqual(courtyard[0]["end"]["y"], spec.fab_max_y + 0.25)
        self.assertAlmostEqual(top, 3.825)

    def test_graphics_mark_body_mouth_and_pin_1_without_back_layer_items(self):
        from tools.lh60_design.interconnect_library import interconnect_graphics_by_layer

        graphics = interconnect_graphics_by_layer()

        self.assertEqual(set(graphics), {"F.Fab", "F.CrtYd", "F.SilkS"})
        self.assertEqual(
            graphics["F.Fab"],
            [
                {
                    "type": "rect",
                    "start": {"x": -8.20, "y": 0.68},
                    "end": {"x": 8.20, "y": 5.80},
                    "stroke_width_mm": 0.1,
                    "fill": "none",
                },
                {
                    "type": "line",
                    "start": {"x": -6.25, "y": 0.68},
                    "end": {"x": 6.25, "y": 0.68},
                    "stroke_width_mm": 0.1,
                },
                {
                    "type": "line",
                    "start": {"x": -6.25, "y": 5.80},
                    "end": {"x": 6.25, "y": 5.80},
                    "stroke_width_mm": 0.1,
                },
            ],
        )
        self.assertIn(
            {
                "type": "circle",
                "center": {"x": -6.45, "y": -0.95},
                "radius_mm": 0.20,
                "stroke_width_mm": 0.1,
                "fill": "solid",
            },
            graphics["F.SilkS"],
        )
        self.assertIn(
            {
                "type": "line",
                "start": {"x": -7.0, "y": 6.15},
                "end": {"x": 7.0, "y": 6.15},
                "stroke_width_mm": 0.12,
            },
            graphics["F.SilkS"],
        )


class InterconnectPayloadContractTest(unittest.TestCase):
    def test_symbol_payload_contains_supported_kicad_properties(self):
        from tools.lh60_design.interconnect import DATASHEET_URL
        from tools.lh60_design.interconnect_library import interconnect_symbol_payload

        payload = interconnect_symbol_payload()

        self.assertEqual(payload["name"], "FPC-05F-24PH20")
        self.assertEqual(payload["reference_prefix"], "J")
        self.assertEqual(payload["value"], "FPC-05F-24PH20")
        self.assertEqual(payload["datasheet"], DATASHEET_URL)
        self.assertEqual(len(payload["pins"]), 24)
        self.assertTrue(all(pin["type"] == "passive" for pin in payload["pins"]))

    def test_footprint_payload_preserves_empty_hold_down_pad_numbers(self):
        from tools.lh60_design.interconnect_library import interconnect_footprint_payload

        payload = interconnect_footprint_payload()
        pads = payload["pads"]

        self.assertEqual(len(pads), 26)
        self.assertEqual([pad["number"] for pad in pads[:24]], [str(i) for i in range(1, 25)])
        self.assertEqual([pad["number"] for pad in pads[24:]], ["", ""])
        self.assertTrue(all(pad["layers"] == ["F.Cu", "F.Paste", "F.Mask"] for pad in pads))
        self.assertFalse(any(pad["number"] in {"25", "26"} for pad in pads))

    def test_custom_clearance_rule_uses_kicad_proven_same_footprint_discriminator(self):
        from tools.lh60_design import interconnect_library

        self.assertEqual(
            interconnect_library.CUSTOM_CLEARANCE_RULE_CONDITION,
            "!(A.Type == 'Pad' && B.Type == 'Pad' && "
            "A.memberOfFootprint('FPC-05F-24PH20') && "
            "B.memberOfFootprint('FPC-05F-24PH20') && "
            "A.Reference == B.Reference)",
        )
        self.assertNotIn("Parent.Reference", interconnect_library.CUSTOM_CLEARANCE_RULE_CONDITION)

    def test_effective_rule_stack_rejects_layer_wide_025_clearance(self):
        from tools.check_interconnect_library_acceptance import (
            _assert_effective_clearance_stack,
        )
        from tools.lh60_design import interconnect_library

        conflicting_rules = [
            {
                "name": "konnect:F.Cu:clearance",
                "constraint": "clearance",
                "minimum_mm": 0.25,
                "condition": "",
                "layer": "F.Cu",
            },
            {
                "name": interconnect_library.CUSTOM_CLEARANCE_RULE_NAME,
                "constraint": "clearance",
                "minimum_mm": 0.25,
                "condition": interconnect_library.CUSTOM_CLEARANCE_RULE_CONDITION,
                "layer": None,
            },
        ]

        with self.assertRaisesRegex(AssertionError, "conflicting unconditional layer clearance"):
            _assert_effective_clearance_stack(conflicting_rules)

    def test_effective_rule_stack_accepts_020_layer_floor_plus_exact_exception(self):
        from tools.check_interconnect_library_acceptance import (
            _assert_effective_clearance_stack,
        )
        from tools.lh60_design import interconnect_library

        rules = [
            {
                "name": "konnect:F.Cu:clearance",
                "constraint": "clearance",
                "minimum_mm": 0.20,
                "condition": "",
                "layer": "F.Cu",
            },
            {
                "name": "konnect:B.Cu:clearance",
                "constraint": "clearance",
                "minimum_mm": 0.20,
                "condition": "",
                "layer": "B.Cu",
            },
            {
                "name": interconnect_library.CUSTOM_CLEARANCE_RULE_NAME,
                "constraint": "clearance",
                "minimum_mm": 0.25,
                "condition": interconnect_library.CUSTOM_CLEARANCE_RULE_CONDITION,
                "layer": None,
            },
        ]

        _assert_effective_clearance_stack(rules)

    def test_symbol_definition_count_reads_existing_library(self):
        from tools.lh60_design import interconnect_library

        with tempfile.TemporaryDirectory() as tmpdir:
            symbol_library = Path(tmpdir) / "probe.kicad_sym"
            symbol_library.write_text(
                '\n'.join(
                    [
                        '(kicad_symbol_lib',
                        '  (symbol "FPC-05F-24PH20"',
                        '  )',
                        '  (symbol "Other"',
                        '  )',
                        '  (symbol "FPC-05F-24PH20"',
                        '  )',
                        ')',
                    ]
                )
            )
            with mock.patch.object(interconnect_library, "SYMBOL_LIBRARY", symbol_library):
                self.assertEqual(interconnect_library._symbol_definition_count(), 2)

    def test_apply_sends_only_konnect_protected_file_operations(self):
        from tools.lh60_design import interconnect_library

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

            def call_tool_json(self, name, arguments):
                self.calls.append((name, arguments))
                if name == "get_design_rules":
                    return {
                        "rules": {
                            "min_clearance": 0.20,
                            "min_trace_width": 0.25,
                            "min_via_drill": 0.3,
                            "min_via_size": 0.7,
                            "min_hole_to_hole": 0.45,
                        }
                    }
                if name == "list_custom_rules":
                    return {
                        "rules": [
                            {
                                "name": "konnect:F.Cu:clearance",
                                "constraint": "clearance",
                                "minimum_mm": 0.20,
                                "condition": "",
                                "layer": "F.Cu",
                            },
                            {
                                "name": "konnect:B.Cu:clearance",
                                "constraint": "clearance",
                                "minimum_mm": 0.20,
                                "condition": "",
                                "layer": "B.Cu",
                            },
                            {
                                "name": interconnect_library.CUSTOM_CLEARANCE_RULE_NAME,
                                "constraint": "clearance",
                                "minimum_mm": 0.25,
                                "condition": interconnect_library.CUSTOM_CLEARANCE_RULE_CONDITION,
                                "layer": None,
                            }
                        ]
                    }
                return {}

        client = RecordingClient()
        with mock.patch.object(interconnect_library, "_symbol_definition_count", return_value=0):
            interconnect_library.apply_interconnect_library(client)

        self.assertEqual(client.schemas, ["library", "verification"])
        self.assertIn(("create_symbol", interconnect_library.interconnect_symbol_payload()), client.calls)
        self.assertIn(("create_footprint", interconnect_library.interconnect_footprint_payload()), client.calls)
        self.assertIn(
            (
                "set_design_rules",
                {
                    "board": str(interconnect_library.BOARD),
                    "min_clearance": 0.20,
                    "min_trace_width": 0.25,
                    "min_via_drill": 0.30,
                    "min_via_size": 0.70,
                    "min_hole_to_hole": 0.45,
                },
            ),
            client.calls,
        )
        for layer in interconnect_library.COPPER_LAYERS:
            self.assertIn(
                (
                    "set_layer_constraints",
                    {
                        "board": str(interconnect_library.BOARD),
                        "layer": layer,
                        "min_clearance": 0.20,
                        "min_trace_width": 0.25,
                    },
                ),
                client.calls,
            )
        self.assertIn(
            (
                "set_custom_rule",
                {
                    "board": str(interconnect_library.BOARD),
                    "name": interconnect_library.CUSTOM_CLEARANCE_RULE_NAME,
                    "constraint": "clearance",
                    "minimum_mm": 0.25,
                    "condition": interconnect_library.CUSTOM_CLEARANCE_RULE_CONDITION,
                },
            ),
            client.calls,
        )


class InterconnectReadbackParserTest(unittest.TestCase):
    def test_footprint_parser_preserves_empty_pad_numbers_and_layers(self):
        from tools.check_interconnect_library_acceptance import _parse_footprint_pads

        text = """
        (footprint "Probe"
          (pad "" smd rect (at -7.44 2.575) (size 2.00 2.50) (layers "F.Cu" "F.Paste" "F.Mask"))
          (pad "1" smd roundrect (at -5.75 0) (size 0.30 1.25) (layers "F.Cu" "F.Paste" "F.Mask"))
        )
        """

        self.assertEqual(
            _parse_footprint_pads(text),
            [
                {
                    "number": "",
                    "type": "smd",
                    "shape": "rect",
                    "x": -7.44,
                    "y": 2.575,
                    "width": 2.0,
                    "height": 2.5,
                    "layers": ("F.Cu", "F.Paste", "F.Mask"),
                },
                {
                    "number": "1",
                    "type": "smd",
                    "shape": "roundrect",
                    "x": -5.75,
                    "y": 0.0,
                    "width": 0.3,
                    "height": 1.25,
                    "layers": ("F.Cu", "F.Paste", "F.Mask"),
                },
            ],
        )


if __name__ == "__main__":
    unittest.main()
