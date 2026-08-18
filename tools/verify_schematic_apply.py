import unittest


class SchematicApplyContractTest(unittest.TestCase):
    def test_power_flags_use_pin_connections_without_visible_custom_net_fields(self):
        from tools.lh60_design.schematic import (
            POWER_FLAG_POSITIONS_MM,
            build_schematic_plan,
        )

        plan = build_schematic_plan()
        flags = [
            component
            for component in plan.components
            if component.reference.startswith("#FLG")
        ]
        flag_connections = {
            connection.reference: (connection.pin_number, connection.net_name)
            for connection in plan.connections
            if connection.reference.startswith("#FLG")
        }

        self.assertEqual([flag.fields for flag in flags], [(), (), ()])
        self.assertEqual(
            [POWER_FLAG_POSITIONS_MM[flag.reference][1] for flag in flags],
            [86.36, 106.68, 127.0],
        )
        self.assertEqual(
            flag_connections,
            {
                "#FLG01": ("1", "VSYS"),
                "#FLG02": ("1", "3V3"),
                "#FLG03": ("1", "GND"),
            },
        )

    def test_capability_gate_requires_deployed_tools_and_symbol_anchors(self):
        from tools.lh60_design.schematic import require_schematic_capabilities

        class FakeClient:
            def tool_schemas(self, toolset):
                schemas = {
                    "sch_batch": {
                        "batch_delete_schematic_components": {},
                        "batch_delete": {},
                        "batch_place_components": {},
                        "batch_edit_schematic_components": {},
                        "batch_connect_to_net": {},
                        "batch_set_schematic_field_visibility": {},
                    },
                    "sch_wiring": {"batch_delete_schematic_wire": {}},
                    "sch_components": {
                        "set_schematic_page": {},
                        "update_symbols_from_library": {},
                    },
                    "library": {
                        "create_symbol": {
                            "properties": {"reference_at": {}, "value_at": {}}
                        }
                    },
                }
                return schemas[toolset]

        require_schematic_capabilities(FakeClient())

        class MissingAnchor(FakeClient):
            def tool_schemas(self, toolset):
                schema = super().tool_schemas(toolset)
                if toolset == "library":
                    schema["create_symbol"]["properties"].pop("value_at")
                return schema

        with self.assertRaisesRegex(RuntimeError, "value_at"):
            require_schematic_capabilities(MissingAnchor())

        class MissingDelete(FakeClient):
            def tool_schemas(self, toolset):
                schema = super().tool_schemas(toolset)
                if toolset == "sch_batch":
                    schema.pop("batch_delete")
                return schema

        with self.assertRaisesRegex(RuntimeError, "batch_delete"):
            require_schematic_capabilities(MissingDelete())

    def test_apply_uses_frozen_call_order_and_payloads(self):
        from tools.lh60_design.schematic import apply_schematic, build_schematic_plan

        class FakeClient:
            def __init__(self):
                self.calls = []

            def tool_schemas(self, toolset):
                self.calls.append(("load", toolset))
                if toolset == "sch_batch":
                    return {
                        "batch_delete_schematic_components": {},
                        "batch_delete": {},
                        "batch_place_components": {},
                        "batch_edit_schematic_components": {},
                        "batch_connect_to_net": {},
                        "batch_set_schematic_field_visibility": {},
                    }
                if toolset == "sch_wiring":
                    return {"batch_delete_schematic_wire": {}}
                if toolset == "sch_components":
                    return {"set_schematic_page": {}, "update_symbols_from_library": {}}
                if toolset == "library":
                    return {
                        "create_symbol": {
                            "properties": {"reference_at": {}, "value_at": {}}
                        }
                    }
                return {}

            def call_tool(self, name, arguments):
                self.calls.append((name, arguments))
                return {}

        client = FakeClient()
        apply_schematic(client, "/tmp/lh60-debug.kicad_sch")
        plan = build_schematic_plan()

        expected_tool_names = [
            *("load" for _ in range(4)),
            "set_schematic_page",
            "batch_place_components",
            "batch_edit_schematic_components",
            *(["batch_connect_to_net"] * len({connection.net_name for connection in plan.connections})),
            "batch_set_schematic_field_visibility",
            "update_symbols_from_library",
        ]
        self.assertEqual(
            [name for name, _ in client.calls],
            expected_tool_names,
        )
        self.assertEqual(
            client.calls[:4],
            [
                ("load", "sch_batch"),
                ("load", "sch_wiring"),
                ("load", "sch_components"),
                ("load", "library"),
            ],
        )
        self.assertEqual(
            client.calls[4],
            (
                "set_schematic_page",
                {
                    "schematic": "/tmp/lh60-debug.kicad_sch",
                    "size": "A3",
                    "portrait": False,
                },
            ),
        )
        place_name, place_arguments = client.calls[5]
        self.assertEqual(place_name, "batch_place_components")
        self.assertEqual(place_arguments["schematic"], "/tmp/lh60-debug.kicad_sch")
        self.assertEqual(len(place_arguments["components"]), 155)

        edit_name, edit_arguments = client.calls[6]
        self.assertEqual(edit_name, "batch_edit_schematic_components")
        self.assertEqual(edit_arguments["schematic"], "/tmp/lh60-debug.kicad_sch")
        self.assertEqual(len(edit_arguments["edits"]), 155)

        grouped_connections = {}
        for name, arguments in client.calls[7:-2]:
            self.assertEqual(name, "batch_connect_to_net")
            self.assertEqual(arguments["schematic"], "/tmp/lh60-debug.kicad_sch")
            grouped_connections[arguments["net_name"]] = arguments["pins"]
        self.assertEqual(len(grouped_connections), 93)
        self.assertEqual(
            grouped_connections["GND"],
            [
                {"reference": "U1", "pin_number": "22"},
                {"reference": "J1", "pin_number": "3"},
                {"reference": "#FLG03", "pin_number": "1"},
            ],
        )
        self.assertEqual(
            grouped_connections["COL0"],
            [
                {"reference": "U1", "pin_number": "1"},
                {"reference": "D1", "pin_number": "2"},
                {"reference": "D11", "pin_number": "2"},
                {"reference": "D21", "pin_number": "2"},
                {"reference": "D31", "pin_number": "2"},
                {"reference": "D41", "pin_number": "2"},
                {"reference": "D51", "pin_number": "2"},
                {"reference": "D61", "pin_number": "2"},
                {"reference": "J2", "pin_number": "1"},
            ],
        )
        self.assertEqual(
            grouped_connections["ROW6"],
            [
                {"reference": "U1", "pin_number": "17"},
                {"reference": "SW67", "pin_number": "2"},
                {"reference": "SW68", "pin_number": "2"},
                {"reference": "SW69", "pin_number": "2"},
                {"reference": "SW70", "pin_number": "2"},
                {"reference": "SW71", "pin_number": "2"},
                {"reference": "SW72", "pin_number": "2"},
                {"reference": "SW73", "pin_number": "2"},
                {"reference": "SW74", "pin_number": "2"},
                {"reference": "SW75", "pin_number": "2"},
                {"reference": "SW76", "pin_number": "2"},
                {"reference": "J5", "pin_number": "3"},
            ],
        )

        visibility_name, visibility_arguments = client.calls[-2]
        self.assertEqual(visibility_name, "batch_set_schematic_field_visibility")
        self.assertEqual(
            visibility_arguments["schematic"],
            "/tmp/lh60-debug.kicad_sch",
        )
        self.assertEqual(len(visibility_arguments["edits"]), 152)
        visibility = {
            edit["reference"]: (edit["reference_visible"], edit["value_visible"])
            for edit in visibility_arguments["edits"]
        }
        self.assertEqual(visibility["D1"], (False, False))
        self.assertEqual(visibility["SW1"], (False, True))
        self.assertEqual(visibility["J1"], (True, True))
        self.assertEqual(visibility["U1"], (True, True))
        self.assertFalse(any(reference.startswith("#FLG") for reference in visibility))

        self.assertEqual(
            client.calls[-1],
            (
                "update_symbols_from_library",
                {
                    "schematic": "/tmp/lh60-debug.kicad_sch",
                    "dry_run": False,
                    "allow_pin_moves": False,
                },
            ),
        )


if __name__ == "__main__":
    unittest.main()
