import unittest
from pathlib import Path


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

    def test_symbol_contract_has_switch_diode_and_test_point(self):
        symbols, _ = self.specs()
        by_name = {symbol.name: symbol for symbol in symbols}

        self.assertEqual(
            set(by_name),
            {"KeySwitch", "MatrixDiode", "TestPoint"},
        )
        self.assertEqual(
            [(pin.number, pin.name, pin.pin_type) for pin in by_name["KeySwitch"].pins],
            [("1", "1", "passive"), ("2", "2", "passive")],
        )
        self.assertEqual(
            [(pin.number, pin.name, pin.pin_type) for pin in by_name["MatrixDiode"].pins],
            [("1", "K", "passive"), ("2", "A", "passive")],
        )
        self.assertEqual(
            [(pin.number, pin.name, pin.pin_type) for pin in by_name["TestPoint"].pins],
            [("1", "TP", "passive")],
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
            self.assertIn(f'(symbol "{symbol.name}"', symbol_text)
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

    def test_provenance_documents_system_library_gate(self):
        readme = (self.LIBRARY_ROOT / "README.md").read_text()
        license_text = (self.LIBRARY_ROOT / "LICENSE-KICAD-LIBRARIES.md").read_text()

        self.assertIn("system library search returned zero results", readme)
        self.assertIn("flipped to the back side during PCB placement", readme)
        self.assertIn("D_SOD-323", readme)
        self.assertIn("TestPoint_Pad_D1.5mm", readme)
        self.assertIn("CC-BY-SA 4.0", license_text)


if __name__ == "__main__":
    unittest.main()
