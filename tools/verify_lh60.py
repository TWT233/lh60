import unittest
from pathlib import Path

from shapely.geometry import Polygon


U_SIZES = ("1U", "1.25U", "1.5U", "1.75U", "2U", "2.25U", "2.75U")
SERIES = ("Gateron-LP", "Kailh-Choc-V1V2", "Gateron-LP-or-ChocV1")


class SocketGeometryMathTest(unittest.TestCase):
    def test_sampled_arc_starts_and_ends_at_declared_points(self):
        from tools.lh60_design.socket_library import _sample_arc

        cases = (
            ((-7.275, 1.825), (-7.165165, 1.559835), (-6.9, 1.45)),
            ((-6.9, 6.15), (-7.165165, 6.040165), (-7.275, 5.775)),
            ((-3.425, 1.45), (-3.159835, 1.559835), (-3.05, 1.825)),
        )
        for start, middle, end in cases:
            with self.subTest(start=start, middle=middle, end=end):
                points = _sample_arc(start, middle, end)
                self.assertAlmostEqual(points[0][0], start[0], places=9)
                self.assertAlmostEqual(points[0][1], start[1], places=9)
                self.assertAlmostEqual(points[-1][0], end[0], places=9)
                self.assertAlmostEqual(points[-1][1], end[1], places=9)

    def test_dual_courtyard_graphics_do_not_overlap_each_other(self):
        from tools.lh60_design.socket_library import build_operation_plan

        operation = next(
            operation
            for operation in build_operation_plan()
            if operation["footprint"]
            == "Gateron-LP-or-ChocV1-Hotswap-Socket-1U"
            and operation["tool"] == "set_footprint_graphics"
            and operation["arguments"]["selector"]["layer"] == "B.CrtYd"
        )
        polygons = [
            Polygon([(point["x"], point["y"]) for point in graphic["points"]])
            for graphic in operation["arguments"]["graphics"]
        ]

        self.assertTrue(all(polygon.is_valid for polygon in polygons))
        for left_index, left in enumerate(polygons):
            for right in polygons[left_index + 1 :]:
                self.assertLessEqual(left.intersection(right).area, 1e-9)

    def test_center_stem_hole_does_not_expand_socket_courtyard(self):
        from shapely.geometry import Point

        from tools.lh60_design.socket_library import _courtyard_geometry
        from tools.lh60_design.socket_geometry import build_footprint_specs

        spec = next(
            spec
            for spec in build_footprint_specs()
            if spec.name == "Gateron-LP-Hotswap-Socket-1U"
        )
        courtyard = _courtyard_geometry(spec)
        center_hole_with_clearance = Point(0, 0).buffer(
            5.25 / 2 + spec.courtyard_clearance_mm,
            quad_segs=16,
        )

        self.assertGreater(
            center_hole_with_clearance.difference(courtyard).area,
            1.0,
            "the switch stem hole must not be treated as expanding assembly volume",
        )

    def test_center_stem_hole_remains_in_hole_clearance_checks(self):
        from tools.lh60_design.regions import (
            RegionPlacement,
            _placed_geometry,
        )

        placement = RegionPlacement(
            socket_ref="SW1",
            footprint="Gateron-LP-Hotswap-Socket-1U",
            center_x_mm=0,
            center_y_mm=0,
            rotation_deg=0,
            logical_node_id="node",
        )

        holes = _placed_geometry(placement).holes

        self.assertTrue(
            any(
                label.endswith("NPTH1:hole")
                and x == 0
                and y == 0
                and radius == 5.25 / 2
                for label, x, y, radius in holes
            )
        )


class SocketSpecTest(unittest.TestCase):
    def specs(self):
        from tools.lh60_design.socket_geometry import build_footprint_specs

        return build_footprint_specs()

    def test_inventory_contains_three_complete_seven_size_series(self):
        specs = self.specs()

        self.assertEqual(len(specs), 21)
        self.assertEqual(
            {(spec.series, spec.size) for spec in specs},
            {(series, size) for series in SERIES for size in U_SIZES},
        )
        self.assertEqual(len({spec.name for spec in specs}), 21)

    def test_each_series_has_the_expected_electrical_and_model_contract(self):
        expected_pad_counts = {
            "Gateron-LP": 7,
            "Kailh-Choc-V1V2": 8,
            "Gateron-LP-or-ChocV1": 15,
        }
        expected_model_counts = {
            "Gateron-LP": 1,
            "Kailh-Choc-V1V2": 1,
            "Gateron-LP-or-ChocV1": 2,
        }

        for spec in self.specs():
            with self.subTest(name=spec.name):
                self.assertEqual(len(spec.pads), expected_pad_counts[spec.series])
                self.assertEqual(len(spec.models), expected_model_counts[spec.series])
                self.assertEqual({pad.number for pad in spec.pads} - {""}, {"1", "2"})
                self.assertEqual(spec.courtyard_clearance_mm, 0.5)
                self.assertEqual(spec.keycap_height_mm, 19.05)
                self.assertTrue(spec.exclude_from_position_files)

    def test_u_variants_only_change_the_keycap_envelope(self):
        for series in SERIES:
            variants = [spec for spec in self.specs() if spec.series == series]
            signatures = {spec.series_signature() for spec in variants}
            widths = {spec.keycap_width_mm for spec in variants}

            self.assertEqual(len(signatures), 1, series)
            self.assertEqual(len(widths), 7, series)

    def test_all_smd_contacts_are_bottom_side(self):
        for spec in self.specs():
            for pad in spec.pads:
                if pad.pad_type != "smd":
                    continue
                with self.subTest(name=spec.name, pad=pad.number, x=pad.x, y=pad.y):
                    self.assertIn("B.Cu", pad.layers)
                    self.assertNotIn("F.Cu", pad.layers)

    def test_names_follow_the_approved_product_lines(self):
        expected = {
            f"{series}-Hotswap-Socket-{size}" for series in SERIES for size in U_SIZES
        }

        self.assertEqual({spec.name for spec in self.specs()}, expected)


class SocketOperationPlanTest(unittest.TestCase):
    def plan(self):
        from tools.lh60_design.socket_library import build_operation_plan

        return build_operation_plan()

    def test_every_footprint_has_one_complete_operation_sequence(self):
        plan = self.plan()
        operations_by_footprint = {}
        for operation in plan:
            operations_by_footprint.setdefault(operation["footprint"], []).append(
                operation["tool"]
            )

        self.assertEqual(len(plan), 189)
        self.assertEqual(len(operations_by_footprint), 21)
        for name, tools in operations_by_footprint.items():
            with self.subTest(name=name):
                self.assertEqual(
                    tools,
                    [
                        "create_footprint",
                        "set_footprint_graphics",
                        "set_footprint_graphics",
                        "set_footprint_graphics",
                        "set_footprint_graphics",
                        "set_footprint_graphics",
                        "set_footprint_graphics",
                        "set_footprint_metadata",
                        "set_footprint_models",
                    ],
                )

    def test_gateron_create_payload_preserves_bottom_side_contact_contract(self):
        operation = next(
            operation
            for operation in self.plan()
            if operation["footprint"] == "Gateron-LP-Hotswap-Socket-1U"
            and operation["tool"] == "create_footprint"
        )
        pads = operation["arguments"]["pads"]

        self.assertEqual(len(pads), 7)
        self.assertEqual(pads[1]["layers"], ["B.Cu", "B.Paste", "B.Mask"])
        self.assertEqual(pads[1]["roundrect_rratio"], 0.2)
        self.assertEqual(pads[2]["layers"], ["B.Cu"])
        self.assertEqual(pads[3]["layers"], ["*.Cu", "B.Mask"])

    def test_graphic_operations_replace_only_approved_layers(self):
        allowed = {
            ("F.SilkS", "delete"),
            ("F.CrtYd", "delete"),
            ("F.Fab", "delete"),
            ("Dwgs.User", "replace"),
            ("B.Fab", "replace"),
            ("B.CrtYd", "replace"),
        }
        graphic_operations = [
            operation
            for operation in self.plan()
            if operation["tool"] == "set_footprint_graphics"
        ]

        self.assertEqual(
            {
                (
                    operation["arguments"]["selector"]["layer"],
                    operation["arguments"]["mode"],
                )
                for operation in graphic_operations
            },
            allowed,
        )

    def test_dual_models_and_kailh_v2_hole_are_present(self):
        plan = self.plan()
        dual_models = next(
            operation["arguments"]["models"]
            for operation in plan
            if operation["footprint"]
            == "Gateron-LP-or-ChocV1-Hotswap-Socket-2.75U"
            and operation["tool"] == "set_footprint_models"
        )
        kailh_pads = next(
            operation["arguments"]["pads"]
            for operation in plan
            if operation["footprint"] == "Kailh-Choc-V1V2-Hotswap-Socket-1U"
            and operation["tool"] == "create_footprint"
        )

        self.assertEqual(len(dual_models), 2)
        self.assertTrue(
            any(
                pad["number"] == ""
                and pad["type"] == "thru_hole"
                and pad["x"] == 5.0
                and pad["y"] == -5.15
                for pad in kailh_pads
            )
        )


class SocketMcpCapabilityTest(unittest.TestCase):
    def test_required_capabilities_include_bottom_pad_fields(self):
        from tools.lh60_design.socket_library import REQUIRED_TOOL_FIELDS

        self.assertEqual(
            REQUIRED_TOOL_FIELDS["create_footprint"],
            {
                "output",
                "name",
                "pads",
                "layers",
                "rotation",
                "roundrect_rratio",
            },
        )
        self.assertIn("graphics", REQUIRED_TOOL_FIELDS["set_footprint_graphics"])
        self.assertIn("attributes", REQUIRED_TOOL_FIELDS["set_footprint_metadata"])
        self.assertIn("models", REQUIRED_TOOL_FIELDS["set_footprint_models"])

    def test_missing_capabilities_reports_nested_pad_fields(self):
        from tools.lh60_design.socket_library import missing_capabilities

        schemas = {
            "create_footprint": {
                "properties": {
                    "output": {},
                    "name": {},
                    "pads": {"items": {"properties": {"number": {}, "layers": {}}}},
                }
            },
            "set_footprint_graphics": {
                "properties": {
                    "footprint_path": {},
                    "selector": {},
                    "mode": {},
                    "graphics": {},
                }
            },
            "set_footprint_metadata": {
                "properties": {
                    "footprint_path": {},
                    "description": {},
                    "tags": {},
                    "attributes": {},
                }
            },
            "set_footprint_models": {
                "properties": {
                    "footprint_path": {},
                    "mode": {},
                    "models": {},
                }
            },
        }

        self.assertEqual(
            missing_capabilities(schemas),
            {"create_footprint": ["pad.rotation", "pad.roundrect_rratio"]},
        )


class SocketLibraryOutputTest(unittest.TestCase):
    LIBRARY = Path(__file__).resolve().parents[1] / "lib" / "lh60-sockets"

    def test_generated_library_has_exactly_the_approved_inventory(self):
        from tools.lh60_design.socket_geometry import build_footprint_specs

        expected = {f"{spec.name}.kicad_mod" for spec in build_footprint_specs()}
        actual = {path.name for path in self.LIBRARY.glob("*.kicad_mod")}

        self.assertEqual(actual, expected)

    def test_each_generated_footprint_has_only_bottom_side_production_graphics(self):
        from tools.lh60_design.socket_geometry import build_footprint_specs

        for spec in build_footprint_specs():
            path = self.LIBRARY / f"{spec.name}.kicad_mod"
            text = path.read_text()
            graphic_lines = [
                line.strip()
                for line in text.splitlines()
                if line.lstrip().startswith(
                    ("(fp_arc ", "(fp_circle ", "(fp_line ", "(fp_poly ", "(fp_rect ")
                )
            ]
            with self.subTest(name=spec.name):
                self.assertFalse(
                    any(
                        f'(layer "{layer}")' in line
                        for line in graphic_lines
                        for layer in ("F.CrtYd", "F.Fab", "F.SilkS")
                    )
                )
                self.assertIn('(layer "Dwgs.User")', text)
                self.assertIn('(layer "B.Fab")', text)
                self.assertIn('(layer "B.CrtYd")', text)
                self.assertIn("exclude_from_pos_files", text)

    def test_each_generated_footprint_has_expected_pad_and_model_counts(self):
        from tools.lh60_design.socket_geometry import build_footprint_specs

        expected_pad_counts = {
            "Gateron-LP": 7,
            "Kailh-Choc-V1V2": 8,
            "Gateron-LP-or-ChocV1": 15,
        }
        for spec in build_footprint_specs():
            text = (self.LIBRARY / f"{spec.name}.kicad_mod").read_text()
            with self.subTest(name=spec.name):
                self.assertEqual(text.count("\n  (pad "), expected_pad_counts[spec.series])
                self.assertEqual(text.count("\n  (model "), len(spec.models))


class Rp2040TinyContractTest(unittest.TestCase):
    ROOT = Path(__file__).resolve().parents[1]
    SYMBOL_LIBRARY = ROOT / "lib" / "lh60-mcu" / "lh60-mcu.kicad_sym"
    FOOTPRINT = (
        ROOT
        / "lib"
        / "lh60-mcu"
        / "lh60-mcu.pretty"
        / "MCU_RP2040-Tiny_SMD.kicad_mod"
    )
    MODEL = ROOT / "lib" / "lh60-mcu" / "RP2040-Tiny-V1.1.step"
    README = ROOT / "lib" / "lh60-mcu" / "README.md"

    def specs(self):
        from tools.lh60_design.mcu_library import (
            rp2040_tiny_footprint_spec,
            rp2040_tiny_symbol_pins,
        )

        return rp2040_tiny_symbol_pins(), rp2040_tiny_footprint_spec()

    def test_symbol_contract_has_23_unique_official_pins(self):
        pins, _ = self.specs()
        expected = {
            **{str(index + 1): f"GP{index}" for index in range(16)},
            "17": "GP26",
            "18": "GP27",
            "19": "GP28",
            "20": "GP29",
            "21": "3V3",
            "22": "GND",
            "23": "VSYS",
        }

        self.assertEqual(len(pins), 23)
        self.assertEqual(len({pin.number for pin in pins}), 23)
        self.assertEqual({pin.number: pin.name for pin in pins}, expected)
        self.assertNotIn("5V", {pin.name for pin in pins})

    def test_symbol_power_pins_are_carrier_power_inputs(self):
        pins, _ = self.specs()
        pin_types = {pin.name: pin.pin_type for pin in pins}

        self.assertEqual(pin_types["3V3"], "power_in")
        self.assertEqual(pin_types["GND"], "power_in")
        self.assertEqual(pin_types["VSYS"], "power_in")

    def test_bottom_gpio_pins_have_readable_seven_millimetre_spacing(self):
        pins, _ = self.specs()
        bottom = [pin for pin in pins if 10 <= int(pin.number) <= 14]

        self.assertEqual(
            [(pin.number, pin.name, pin.pin_type) for pin in bottom],
            [
                ("10", "GP9", "bidirectional"),
                ("11", "GP10", "bidirectional"),
                ("12", "GP11", "bidirectional"),
                ("13", "GP12", "bidirectional"),
                ("14", "GP13", "bidirectional"),
            ],
        )
        self.assertEqual([pin.x for pin in bottom], [15.24, 7.62, 0.0, -7.62, -15.24])
        self.assertTrue(all(pin.y == -15.24 and pin.angle == 90.0 for pin in bottom))

    def test_footprint_contract_matches_lambdakb_smd_coordinates(self):
        _, spec = self.specs()
        expected_positions = {
            **{
                str(index + 1): (8.2, index * 2.54)
                for index in range(9)
            },
            **{
                str(index + 10): (5.08 - index * 2.54, 20.9)
                for index in range(5)
            },
            **{
                str(index + 15): (-8.2, 20.32 - index * 2.54)
                for index in range(9)
            },
        }

        self.assertEqual(spec.name, "MCU_RP2040-Tiny_SMD")
        self.assertEqual(spec.body_width_mm, 18.0)
        self.assertEqual(spec.body_height_mm, 23.5)
        self.assertEqual(spec.courtyard_clearance_mm, 0.5)
        self.assertEqual(len(spec.pads), 23)
        self.assertEqual(
            {pad.number: (pad.x, pad.y) for pad in spec.pads},
            expected_positions,
        )
        self.assertTrue(all((pad.width, pad.height) == (2.4, 1.6) for pad in spec.pads))
        self.assertEqual(spec.fpc_edge, "rear")

    def test_symbol_payload_has_reference_at_anchor(self):
        from tools.lh60_design.mcu_library import symbol_payload

        payload = symbol_payload()
        self.assertEqual(
            payload["reference_at"],
            {"x": 0.0, "y": 17.78, "rotation": 0.0},
        )

    def test_symbol_payload_has_value_at_anchor(self):
        from tools.lh60_design.mcu_library import symbol_payload

        payload = symbol_payload()
        self.assertEqual(
            payload["value_at"],
            {"x": 0.0, "y": -25.40, "rotation": 0.0},
        )

    def test_generated_library_contains_symbol_footprint_model_and_provenance(self):
        symbol_text = self.SYMBOL_LIBRARY.read_text()
        footprint_text = self.FOOTPRINT.read_text()
        readme_text = self.README.read_text()

        self.assertTrue(self.MODEL.is_file())
        self.assertGreater(self.MODEL.stat().st_size, 1_000_000)
        self.assertEqual(
            symbol_text.count('\n  (symbol "RP2040-Tiny"\n'),
            1,
        )
        self.assertIn('(name "VSYS"', symbol_text)
        self.assertNotIn('(name "5V"', symbol_text)
        self.assertEqual(footprint_text.count("\n  (pad "), 23)
        self.assertIn("RP2040-Tiny-V1.1.step", footprint_text)
        self.assertIn("FPC", footprint_text)
        self.assertIn("9bb38d7e67c561dfa24428686992abeb17d0a9aa", readme_text)
        self.assertIn("MIT", readme_text)
        self.assertIn("Waveshare", readme_text)


if __name__ == "__main__":
    unittest.main()
