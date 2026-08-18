import unittest
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
        "MCU_POSITION_MM": (350.52, 45.72),
        "CONNECTOR_POSITIONS_MM": {
            "J1": (330.20, 96.52),
            "J2": (330.20, 134.62),
            "J3": (330.20, 177.80),
            "J4": (373.38, 134.62),
            "J5": (373.38, 175.26),
            "J6": (373.38, 215.90),
        },
        "POWER_FLAG_POSITIONS_MM": {
            "#FLG01": (381.00, 86.36),
            "#FLG02": (381.00, 96.52),
            "#FLG03": (381.00, 106.68),
        },
    }
    EXPECTED_CONNECTORS = {
        "J1": (
            "PWR",
            "lh60-core:Conn_01x03",
            "lh60-core:PinHeader_1x03_P2.54mm_Vertical",
            (("1", "VSYS"), ("2", "3V3"), ("3", "GND")),
        ),
        "J2": (
            "COL_A",
            "lh60-core:Conn_01x05",
            "lh60-core:PinHeader_1x05_P2.54mm_Vertical",
            (
                ("1", "COL0"),
                ("2", "COL1"),
                ("3", "COL2"),
                ("4", "COL3"),
                ("5", "COL4"),
            ),
        ),
        "J3": (
            "COL_B",
            "lh60-core:Conn_01x05",
            "lh60-core:PinHeader_1x05_P2.54mm_Vertical",
            (
                ("1", "COL5"),
                ("2", "COL6"),
                ("3", "COL7"),
                ("4", "COL8"),
                ("5", "COL9"),
            ),
        ),
        "J4": (
            "ROW_A",
            "lh60-core:Conn_01x04",
            "lh60-core:PinHeader_1x04_P2.54mm_Vertical",
            (("1", "ROW0"), ("2", "ROW1"), ("3", "ROW2"), ("4", "ROW3")),
        ),
        "J5": (
            "ROW_B",
            "lh60-core:Conn_01x03",
            "lh60-core:PinHeader_1x03_P2.54mm_Vertical",
            (("1", "ROW4"), ("2", "ROW5"), ("3", "ROW6")),
        ),
        "J6": (
            "AUX",
            "lh60-core:Conn_01x03",
            "lh60-core:PinHeader_1x03_P2.54mm_Vertical",
            (("1", "GP27"), ("2", "GP28"), ("3", "GP29")),
        ),
    }

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
        by_kind = {}
        for component in plan.components:
            by_kind.setdefault(component.kind, []).append(component)

        self.assertEqual(len(by_kind["mcu"]), 1)
        self.assertEqual(len(by_kind["switch"]), 75)
        self.assertEqual(len(by_kind["diode"]), 70)
        self.assertEqual(len(by_kind["connector"]), 6)
        self.assertEqual(len(by_kind["power_flag"]), 3)
        self.assertEqual(len(plan.components), 155)
        self.assertEqual(
            len({component.reference for component in plan.components}),
            155,
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
            {component.lib_id for component in by_kind["switch"]},
            {"Switch:SW_Push"},
        )
        self.assertEqual(
            {component.lib_id for component in by_kind["diode"]},
            {"Device:D"},
        )
        self.assertEqual(
            {component.lib_id for component in by_kind["connector"]},
            {"lh60-core:Conn_01x03", "lh60-core:Conn_01x04", "lh60-core:Conn_01x05"},
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

    def test_connector_groups_cover_power_matrix_and_spare_gpio(self):
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

        self.assertEqual(set(connectors), set(self.EXPECTED_CONNECTORS))
        for reference, (
            value,
            lib_id,
            footprint,
            pin_map,
        ) in self.EXPECTED_CONNECTORS.items():
            component = connectors[reference]
            self.assertEqual(component.value, value)
            self.assertEqual(component.lib_id, lib_id)
            self.assertEqual(component.footprint, footprint)
            for pin_number, net_name in pin_map:
                self.assertEqual(pin_nets[(reference, pin_number)], net_name)

        self.assertEqual(
            [
                (connection.reference, connection.pin_number)
                for connection in plan.connections
                if connection.reference.startswith("J")
                and connection.net_name == "GND"
            ],
            [("J1", "3")],
        )

    def test_page_layout_grid_and_switch_bands_are_frozen(self):
        from tools.lh60_design.matrix import logical_nodes
        from tools.lh60_design.schematic import (
            CONNECTOR_POSITIONS_MM,
            MCU_POSITION_MM,
            MATRIX_X0_MM,
            MATRIX_X_PITCH_MM,
            MATRIX_Y0_MM,
            MATRIX_Y_PITCH_MM,
            PAGE_PORTRAIT,
            PAGE_SIZE,
            POWER_FLAG_POSITIONS_MM,
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
        self.assertEqual(
            MCU_POSITION_MM,
            self.EXPECTED_MATRIX_LAYOUT["MCU_POSITION_MM"],
        )
        self.assertEqual(
            CONNECTOR_POSITIONS_MM,
            self.EXPECTED_MATRIX_LAYOUT["CONNECTOR_POSITIONS_MM"],
        )
        self.assertEqual(
            POWER_FLAG_POSITIONS_MM,
            self.EXPECTED_MATRIX_LAYOUT["POWER_FLAG_POSITIONS_MM"],
        )
        self.assertEqual(
            (components["U1"].x, components["U1"].y),
            self.EXPECTED_MATRIX_LAYOUT["MCU_POSITION_MM"],
        )
        for reference, position in self.EXPECTED_MATRIX_LAYOUT["CONNECTOR_POSITIONS_MM"].items():
            self.assertEqual((components[reference].x, components[reference].y), position)
        for reference, position in self.EXPECTED_MATRIX_LAYOUT["POWER_FLAG_POSITIONS_MM"].items():
            self.assertEqual((components[reference].x, components[reference].y), position)
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
            **{f"J{index}": (True, True) for index in range(1, 7)},
            "U1": (True, True),
        }

        self.assertEqual(expected_switches, {f"SW{index}" for index in range(1, 77)} - {"SW59"})
        self.assertEqual(set(states), set(expected))
        self.assertEqual(len(states), 152)
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
        expected_pin_count = 23 + 75 * 2 + 70 * 2 + 23 + 3
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
