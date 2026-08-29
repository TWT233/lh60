import unittest
from collections import Counter
from pathlib import Path
from unittest import mock


class SchematicPlanContractTest(unittest.TestCase):
    EXPECTED_PAGE = ("A3", False)
    EXPECTED_MATRIX_LAYOUT = {
        "MATRIX_X0_MM": 20.32,
        "MATRIX_Y0_MM": 20.32,
        "MATRIX_X_PITCH_MM": 30.48,
        "MATRIX_Y_PITCH_MM": 33.02,
        "SWITCH_Y_OFFSETS_MM": (10.16, 17.78),
        "FFC_POSITION_MM": (360.68, 76.2),
    }
    EXPECTED_FFC_PIN_MAP = (
        ("1", "GND"),
        ("2", "COL0"),
        ("3", "COL1"),
        ("4", "COL2"),
        ("5", "GND"),
        ("6", "COL3"),
        ("7", "COL4"),
        ("8", "COL5"),
        ("9", "GND"),
        ("10", "COL6"),
        ("11", "COL7"),
        ("12", "COL8"),
        ("13", "COL9"),
        ("14", "ROW0"),
        ("15", "ROW1"),
        ("16", "GND"),
        ("17", "ROW2"),
        ("18", "ROW3"),
        ("19", "ROW4"),
        ("20", "GND"),
        ("21", "ROW5"),
        ("22", "ROW6"),
        ("24", "GND"),
    )

    def plan(self):
        from tools.lh60_design.schematic import build_schematic_plan

        return build_schematic_plan()

    def field_state(self):
        return {
            visibility.reference: (
                visibility.reference_visible,
                visibility.value_visible,
            )
            for visibility in self.plan().field_visibility
        }

    def component_by_reference(self):
        return {
            component.reference: component
            for component in self.plan().components
        }

    def test_inventory_matches_the_frozen_design(self):
        plan = self.plan()
        by_kind = Counter(component.kind for component in plan.components)

        self.assertEqual(
            by_kind,
            Counter({"switch": 75, "diode": 70, "connector": 1}),
        )
        self.assertEqual([c.reference for c in plan.components if c.kind == "connector"], ["J1"])
        self.assertFalse(any(c.kind in {"mcu", "power_flag"} for c in plan.components))
        self.assertEqual(len(plan.components), 146)
        self.assertEqual(
            len({component.reference for component in plan.components}),
            146,
        )
        self.assertEqual(
            plan.no_connects,
            (__import__("tools.lh60_design.schematic", fromlist=["NoConnectPin"]).NoConnectPin("J1", "23"),),
        )
        self.assertNotIn(
            "SW59",
            {component.reference for component in plan.components},
        )
        self.assertFalse(
            any(
                component.reference.startswith("TP")
                for component in plan.components
            )
        )
        self.assertEqual(
            {component.lib_id for component in plan.components if component.kind == "switch"},
            {"Switch:SW_Push"},
        )
        self.assertEqual(
            {component.lib_id for component in plan.components if component.kind == "diode"},
            {"Device:D"},
        )
        self.assertEqual(
            {component.lib_id for component in plan.components if component.kind == "connector"},
            {"lh60-interconnect:FPC-05F-24PH20"},
        )

    def test_no_components_define_explicit_instance_flag_overrides(self):
        plan = self.plan()
        for component in plan.components:
            self.assertEqual(
                (component.in_bom, component.on_board, component.dnp),
                (None, None, None),
            )

    def test_every_physical_key_has_one_traceable_switch(self):
        from tools.lh60_design.layout import physical_keys
        from tools.lh60_design.schematic import switch_references

        switches = {
            component.physical_key_id: component
            for component in self.plan().components
            if component.kind == "switch"
        }
        keys = physical_keys()

        self.assertEqual(set(switches), {key.physical_key_id for key in keys})
        references = switch_references()
        self.assertNotIn("SW59", set(references.values()))
        self.assertEqual(references["r3_rshift_left_1.75u"], "SW60")
        self.assertEqual(references["r4_right_ctrl_1u"], "SW76")
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

    def test_no_mcu_gpio_power_or_spare_contract_remains_on_root_board(self):
        plan = self.plan()
        prohibited = {"VSYS", "3V3", "D+", "D-", "VBUS", "RUN", "BOOTSEL", "SWDIO", "SWCLK", "GP27", "GP28", "GP29", "NC"}
        self.assertFalse(any(component.reference == "U1" for component in plan.components))
        self.assertFalse(any(connection.reference == "U1" for connection in plan.connections))
        self.assertFalse({connection.net_name for connection in plan.connections} & prohibited)

    def test_single_ffc_connector_covers_only_matrix_ground_and_explicit_nc(self):
        from tools.lh60_design.interconnect import interboard_contract

        plan = self.plan()
        connectors = {
            component.reference: component
            for component in plan.components
            if component.kind == "connector"
        }
        pin_nets = {
            (connection.reference, connection.pin_number): connection.net_name
            for connection in plan.connections
        }

        self.assertEqual(set(connectors), {"J1"})
        component = connectors["J1"]
        self.assertEqual(component.value, "FPC-05F-24PH20")
        self.assertEqual(component.lib_id, "lh60-interconnect:FPC-05F-24PH20")
        self.assertEqual(component.footprint, "lh60-interconnect:FPC-05F-24PH20")
        self.assertEqual(
            dict(component.fields),
            {"Manufacturer": "XUNPU", "MPN": "FPC-05F-24PH20", "LCSC": "C2856805"},
        )
        self.assertEqual(
            tuple((pin.number, pin.net_name) for pin in interboard_contract().pins if not pin.is_no_connect),
            tuple((int(pin_number), net_name) for pin_number, net_name in self.EXPECTED_FFC_PIN_MAP),
        )
        for pin_number, net_name in self.EXPECTED_FFC_PIN_MAP:
            self.assertEqual(pin_nets[("J1", pin_number)], net_name)
        self.assertNotIn(("J1", "23"), pin_nets)

        self.assertEqual(
            [
                (connection.reference, connection.pin_number)
                for connection in plan.connections
                if connection.reference.startswith("J")
                and connection.net_name == "GND"
            ],
            [("J1", "1"), ("J1", "5"), ("J1", "9"), ("J1", "16"), ("J1", "20"), ("J1", "24")],
        )

    def test_page_layout_grid_and_switch_bands_are_frozen(self):
        from tools.lh60_design.matrix import logical_nodes
        from tools.lh60_design.schematic import (
            FFC_POSITION_MM,
            MATRIX_X0_MM,
            MATRIX_X_PITCH_MM,
            MATRIX_Y0_MM,
            MATRIX_Y_PITCH_MM,
            PAGE_PORTRAIT,
            PAGE_SIZE,
            SWITCH_Y_OFFSETS_MM,
        )

        plan = self.plan()
        components = self.component_by_reference()
        diodes = {
            component.logical_node_id: component
            for component in plan.components
            if component.kind == "diode"
        }
        switches_by_node = {}
        switches = [
            component
            for component in plan.components
            if component.kind == "switch"
        ]
        longest_length = max(len(component.value) for component in switches)

        self.assertEqual((PAGE_SIZE, PAGE_PORTRAIT), self.EXPECTED_PAGE)
        self.assertEqual((plan.page_size, plan.portrait), self.EXPECTED_PAGE)
        self.assertEqual(MATRIX_X0_MM, self.EXPECTED_MATRIX_LAYOUT["MATRIX_X0_MM"])
        self.assertEqual(MATRIX_Y0_MM, self.EXPECTED_MATRIX_LAYOUT["MATRIX_Y0_MM"])
        self.assertEqual(longest_length, 26)
        self.assertEqual(
            MATRIX_X_PITCH_MM,
            self.EXPECTED_MATRIX_LAYOUT["MATRIX_X_PITCH_MM"],
        )
        self.assertEqual(
            MATRIX_Y_PITCH_MM,
            self.EXPECTED_MATRIX_LAYOUT["MATRIX_Y_PITCH_MM"],
        )
        self.assertEqual(
            SWITCH_Y_OFFSETS_MM,
            self.EXPECTED_MATRIX_LAYOUT["SWITCH_Y_OFFSETS_MM"],
        )
        self.assertEqual(FFC_POSITION_MM, self.EXPECTED_MATRIX_LAYOUT["FFC_POSITION_MM"])
        self.assertEqual((components["J1"].x, components["J1"].y), self.EXPECTED_MATRIX_LAYOUT["FFC_POSITION_MM"])
        self.assertGreaterEqual(components["J1"].y, 76.2)
        self.assertGreater(components["J1"].x, MATRIX_X0_MM + 10 * MATRIX_X_PITCH_MM)
        self.assertGreaterEqual(SWITCH_Y_OFFSETS_MM[0], 0.0)
        self.assertTrue(
            all(
                earlier < later
                for earlier, later in zip(
                    SWITCH_Y_OFFSETS_MM,
                    SWITCH_Y_OFFSETS_MM[1:],
                )
            )
        )
        self.assertLess(SWITCH_Y_OFFSETS_MM[-1], MATRIX_Y_PITCH_MM)
        for component in plan.components:
            self.assertAlmostEqual(component.x / 1.27, round(component.x / 1.27), places=9)
            self.assertAlmostEqual(component.y / 1.27, round(component.y / 1.27), places=9)

        for switch in switches:
            switches_by_node.setdefault(switch.logical_node_id, []).append(switch)
        for node in logical_nodes():
            diode = diodes[node.logical_node_id]
            self.assertAlmostEqual(
                diode.x,
                MATRIX_X0_MM + node.column * MATRIX_X_PITCH_MM,
                places=9,
            )
            self.assertAlmostEqual(
                diode.y,
                MATRIX_Y0_MM + node.row * MATRIX_Y_PITCH_MM,
                places=9,
            )
            offsets = {
                round(switch.y - diode.y, 9)
                for switch in switches_by_node[node.logical_node_id]
            }
            self.assertEqual(
                offsets,
                {
                    round(offset, 9)
                    for offset in SWITCH_Y_OFFSETS_MM[:len(node.physical_key_ids)]
                },
            )
            if len(node.physical_key_ids) == 2:
                self.assertEqual(
                    offsets,
                    {round(offset, 9) for offset in SWITCH_Y_OFFSETS_MM},
                )

    def test_field_visibility_contract_is_frozen(self):
        from tools.lh60_design.schematic import switch_references

        states = self.field_state()
        expected_switches = set(switch_references().values())
        expected = {
            **{f"D{index}": (False, False) for index in range(1, 71)},
            **{reference: (False, True) for reference in expected_switches},
            "J1": (True, True),
        }

        self.assertEqual(expected_switches, {f"SW{index}" for index in range(1, 77)} - {"SW59"})
        self.assertEqual(set(states), set(expected))
        self.assertEqual(len(states), 146)
        self.assertFalse(any(reference.startswith("#FLG") for reference in states))
        self.assertEqual(states, expected)

    def test_switch_offset_overflow_is_rejected(self):
        from tools.lh60_design import schematic

        with mock.patch.object(schematic, "SWITCH_Y_OFFSETS_MM", (10.16,)):
            with self.assertRaisesRegex(ValueError, "switch offsets"):
                schematic.build_schematic_plan()

    def test_connection_plan_has_one_assignment_per_pin(self):
        plan = self.plan()
        assignments = [
            (connection.reference, connection.pin_number)
            for connection in plan.connections
        ]

        self.assertEqual(len(assignments), len(set(assignments)))
        expected_pin_count = 75 * 2 + 70 * 2 + 23
        self.assertEqual(len(assignments), expected_pin_count)
        self.assertEqual(
            {connection.net_name for connection in plan.connections}
            - {f"KEY_{index:02d}" for index in range(70)},
            {
                *(f"COL{index}" for index in range(10)),
                *(f"ROW{index}" for index in range(7)),
                "GND",
            },
        )


class ProductionSchematicOutputTest(unittest.TestCase):
    SCHEMATIC = Path(__file__).resolve().parents[1] / "lh60.kicad_sch"

    def test_retired_rshift_symbol_is_absent(self):
        text = self.SCHEMATIC.read_text()

        self.assertNotIn('"SW59"', text)
        self.assertNotIn("r3_rshift_2.75u", text)
        self.assertNotIn(
            '(label "KEY_55"\n    (at 123.19 148.59 180)',
            text,
        )
        self.assertNotIn(
            '(label "ROW5"\n    (at 135.89 148.59 0)',
            text,
        )
        self.assertEqual(
            len(
                __import__("re").findall(
                    r'\(property "Reference" "SW[0-9]+"',
                    text,
                )
            ),
            75,
        )

    def test_switches_and_diodes_use_kicad_default_symbols(self):
        text = self.SCHEMATIC.read_text()

        self.assertEqual(text.count('(lib_id "lh60-core:KeySwitch")'), 0)
        self.assertEqual(text.count('(lib_id "lh60-core:MatrixDiode")'), 0)
        self.assertEqual(text.count('(lib_id "Switch:SW_Push")'), 75)
        self.assertEqual(text.count('(lib_id "Device:D")'), 70)


if __name__ == "__main__":
    unittest.main()
