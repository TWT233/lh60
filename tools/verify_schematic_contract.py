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
            {"KeySwitch", "MatrixDiode", "TestPoint", "PowerFlag"},
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


class SchematicPlanContractTest(unittest.TestCase):
    def plan(self):
        from tools.lh60_design.schematic import build_schematic_plan

        return build_schematic_plan()

    def test_inventory_matches_the_frozen_design(self):
        plan = self.plan()
        by_kind = {}
        for component in plan.components:
            by_kind.setdefault(component.kind, []).append(component)

        self.assertEqual(len(by_kind["mcu"]), 1)
        self.assertEqual(len(by_kind["switch"]), 76)
        self.assertEqual(len(by_kind["diode"]), 70)
        self.assertEqual(len(by_kind["test_point"]), 23)
        self.assertEqual(len(by_kind["power_flag"]), 3)
        self.assertEqual(len(plan.components), 173)
        self.assertEqual(len({component.reference for component in plan.components}), 173)

    def test_every_physical_key_has_one_traceable_switch(self):
        from tools.lh60_design.layout import physical_keys

        switches = {
            component.physical_key_id: component
            for component in self.plan().components
            if component.kind == "switch"
        }
        keys = physical_keys()

        self.assertEqual(set(switches), {key.physical_key_id for key in keys})
        for key in keys:
            component = switches[key.physical_key_id]
            self.assertEqual(component.logical_node_id, key.logical_node_id)
            self.assertEqual(component.value, key.physical_key_id)
            expected_series = (
                "Gateron-LP-or-ChocV1"
                if key.region is None
                else "Gateron-LP"
            )
            self.assertEqual(
                component.footprint,
                f"lh60-sockets:{expected_series}-Hotswap-Socket-{key.footprint_size}",
            )

    def test_every_logical_node_has_one_col2row_diode(self):
        from tools.lh60_design.matrix import logical_nodes
        from tools.lh60_design.schematic import switch_references

        plan = self.plan()
        references = switch_references()
        diodes = {
            component.logical_node_id: component
            for component in plan.components
            if component.kind == "diode"
        }
        pin_nets = {
            (connection.reference, connection.pin_number): connection.net_name
            for connection in plan.connections
        }

        self.assertEqual(set(diodes), {node.logical_node_id for node in logical_nodes()})
        for node in logical_nodes():
            diode = diodes[node.logical_node_id]
            self.assertEqual(diode.reference, node.diode_ref)
            self.assertEqual(diode.footprint, "lh60-core:D_SOD-323_Bottom")
            self.assertEqual(pin_nets[(diode.reference, "2")], node.column_net)
            self.assertEqual(
                pin_nets[(diode.reference, "1")],
                f"KEY_{node.logical_index:02d}",
            )
            for physical_key_id in node.physical_key_ids:
                switch_ref = references[physical_key_id]
                self.assertEqual(
                    pin_nets[(switch_ref, "1")],
                    f"KEY_{node.logical_index:02d}",
                )
                self.assertEqual(
                    pin_nets[(switch_ref, "2")],
                    node.row_net,
                )

    def test_mcu_gpio_and_power_contract_is_complete(self):
        plan = self.plan()
        pin_nets = {
            (connection.reference, connection.pin_number): connection.net_name
            for connection in plan.connections
        }
        expected = {
            **{str(index + 1): f"COL{index}" for index in range(10)},
            **{
                str(index + 11): f"ROW{index}"
                for index in range(6)
            },
            "17": "ROW6",
            "18": "GP27",
            "19": "GP28",
            "20": "GP29",
            "21": "3V3",
            "22": "GND",
            "23": "VSYS",
        }

        self.assertEqual(
            {
                pin_number: pin_nets[("U1", pin_number)]
                for pin_number in expected
            },
            expected,
        )
        self.assertEqual(
            {pin_number for reference, pin_number in pin_nets if reference == "U1"},
            set(expected),
        )

    def test_test_points_cover_power_matrix_and_spare_gpio(self):
        plan = self.plan()
        test_points = [
            component
            for component in plan.components
            if component.kind == "test_point"
        ]
        pin_nets = {
            (connection.reference, connection.pin_number): connection.net_name
            for connection in plan.connections
        }
        expected_nets = {
            "VSYS",
            "3V3",
            "GND",
            *(f"COL{index}" for index in range(10)),
            *(f"ROW{index}" for index in range(7)),
            "GP27",
            "GP28",
            "GP29",
        }

        self.assertEqual({component.value for component in test_points}, expected_nets)
        self.assertEqual(
            {
                pin_nets[(component.reference, "1")]
                for component in test_points
            },
            expected_nets,
        )
        self.assertTrue(
            all(
                component.footprint
                == "lh60-core:TestPoint_Pad_D1.5mm_Bottom"
                for component in test_points
            )
        )

    def test_connection_plan_has_one_assignment_per_pin(self):
        plan = self.plan()
        assignments = [
            (connection.reference, connection.pin_number)
            for connection in plan.connections
        ]

        self.assertEqual(len(assignments), len(set(assignments)))
        expected_pin_count = 23 + 76 * 2 + 70 * 2 + 23 + 3
        self.assertEqual(len(assignments), expected_pin_count)
        self.assertEqual(
            {connection.net_name for connection in plan.connections}
            - {f"KEY_{index:02d}" for index in range(70)},
            {
                *(f"COL{index}" for index in range(10)),
                *(f"ROW{index}" for index in range(7)),
                "GP27",
                "GP28",
                "GP29",
                "VSYS",
                "3V3",
                "GND",
            },
        )


if __name__ == "__main__":
    unittest.main()
