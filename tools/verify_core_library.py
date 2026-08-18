import unittest
from pathlib import Path

from tools.lh60_design.mcp import McpClient


class CoreLibraryContractTest(unittest.TestCase):
    ROOT = Path(__file__).resolve().parents[1]
    LIBRARY_ROOT = ROOT / "lib" / "lh60-core"
    SYMBOL_LIBRARY = LIBRARY_ROOT / "lh60-core.kicad_sym"
    FOOTPRINT_LIBRARY = LIBRARY_ROOT / "lh60-core.pretty"

    def specs(self):
        from tools.lh60_design.core_library import (
            core_footprint_specs,
            core_symbol_specs,
        )

        return core_symbol_specs(), core_footprint_specs()

    def test_symbol_contract_keeps_only_project_support_symbols(self):
        symbols, _ = self.specs()
        by_name = {symbol.name: symbol for symbol in symbols}

        self.assertEqual(
            set(by_name),
            {"TestPoint", "PowerFlag"},
        )
        self.assertEqual(
            [(pin.number, pin.name, pin.pin_type) for pin in by_name["TestPoint"].pins],
            [("1", "TP", "passive")],
        )
        self.assertEqual(
            [(pin.number, pin.name, pin.pin_type) for pin in by_name["PowerFlag"].pins],
            [("1", "PWR_FLAG", "power_out")],
        )

    def test_footprint_contract_is_canonical_and_assembly_aware(self):
        _, footprints = self.specs()
        by_name = {footprint.name: footprint for footprint in footprints}

        self.assertEqual(
            set(by_name),
            {"D_SOD-323_Bottom", "TestPoint_Pad_D1.5mm_Bottom"},
        )
        diode = by_name["D_SOD-323_Bottom"]
        self.assertEqual(len(diode.pads), 2)
        self.assertEqual(
            [(pad.number, pad.x, pad.width, pad.height) for pad in diode.pads],
            [("1", -1.05, 0.6, 0.45), ("2", 1.05, 0.6, 0.45)],
        )
        self.assertTrue(
            all(pad.layers == ("F.Cu", "F.Paste", "F.Mask") for pad in diode.pads)
        )
        self.assertEqual(diode.attributes, ("smd",))

        test_point = by_name["TestPoint_Pad_D1.5mm_Bottom"]
        self.assertEqual(len(test_point.pads), 1)
        self.assertEqual(test_point.pads[0].layers, ("F.Cu", "F.Mask"))
        self.assertEqual(test_point.pads[0].width, 1.5)
        self.assertEqual(
            test_point.attributes,
            ("exclude_from_pos_files", "exclude_from_bom"),
        )

    def test_generated_library_is_parseable_and_registered_portably(self):
        symbols, footprints = self.specs()
        symbol_text = self.SYMBOL_LIBRARY.read_text()
        footprint_table = (self.ROOT / "fp-lib-table").read_text()
        symbol_table = (self.ROOT / "sym-lib-table").read_text()

        for symbol in symbols:
            self.assertEqual(
                symbol_text.count(f'\n  (symbol "{symbol.name}"\n'),
                1,
                symbol.name,
            )
        self.assertNotIn('\n  (symbol "KeySwitch"\n', symbol_text)
        self.assertNotIn('\n  (symbol "MatrixDiode"\n', symbol_text)
        for footprint in footprints:
            path = self.FOOTPRINT_LIBRARY / f"{footprint.name}.kicad_mod"
            text = path.read_text()
            self.assertEqual(text.count("\n  (pad "), len(footprint.pads))
            self.assertIn('(layer "F.Fab")', text)
            self.assertIn('(layer "F.CrtYd")', text)
            self.assertNotIn('(layer "B.Fab")', text)
            self.assertNotIn('(layer "B.CrtYd")', text)

        self.assertIn(
            '${KIPRJMOD}/lib/lh60-core/lh60-core.pretty',
            footprint_table,
        )
        self.assertIn(
            '${KIPRJMOD}/lib/lh60-core/lh60-core.kicad_sym',
            symbol_table,
        )

    def test_provenance_documents_default_symbols_and_custom_footprints(self):
        readme = (self.LIBRARY_ROOT / "README.md").read_text()
        license_text = (self.LIBRARY_ROOT / "LICENSE-KICAD-LIBRARIES.md").read_text()

        self.assertIn("`Switch:SW_Push`", readme)
        self.assertIn("`Device:D`", readme)
        self.assertIn("flipped to the back side during PCB placement", readme)
        self.assertIn("D_SOD-323", readme)
        self.assertIn("TestPoint_Pad_D1.5mm", readme)
        self.assertIn("CC-BY-SA 4.0", license_text)


class McpClientResultTest(unittest.TestCase):
    def test_result_json_returns_object_from_text_block(self):
        result = {"content": [{"type": "text", "text": '{"count": 6}'}]}

        self.assertEqual(McpClient.result_json(result), {"count": 6})

    def test_result_json_raises_for_error_results(self):
        result = {
            "isError": True,
            "content": [{"type": "text", "text": '{"message": "boom"}'}],
        }

        with self.assertRaises(RuntimeError):
            McpClient.result_json(result)

    def test_result_json_raises_when_text_block_is_missing(self):
        result = {"content": [{"type": "resource", "uri": "app://ignored"}]}

        with self.assertRaises(RuntimeError):
            McpClient.result_json(result)

    def test_result_json_raises_when_text_block_is_invalid_json(self):
        result = {"content": [{"type": "text", "text": "not-json"}]}

        with self.assertRaises(RuntimeError):
            McpClient.result_json(result)

    def test_result_json_raises_when_json_value_is_not_object(self):
        result = {"content": [{"type": "text", "text": '["count", 6]'}]}

        with self.assertRaises(RuntimeError):
            McpClient.result_json(result)

    def test_result_json_raises_when_no_text_block_contains_an_object(self):
        result = {
            "content": [
                {"type": "text", "text": "true"},
                {"type": "text", "text": '["count", 6]'},
                {"type": "resource", "uri": "app://ignored"},
            ]
        }

        with self.assertRaises(RuntimeError):
            McpClient.result_json(result)


if __name__ == "__main__":
    unittest.main()
