import unittest
from copy import deepcopy


def complete_schematic_schemas():
    def schema(required, *properties):
        return {"required": list(required), "properties": {name: {} for name in properties}}

    return {
        "sch_batch": {
            "batch_delete_schematic_components": schema(("schematic", "references"), "schematic", "references"),
            "batch_delete": schema(("schematic",), "schematic", "references", "uuids"),
            "batch_place_components": schema(("schematic", "components"), "schematic", "components"),
            "batch_edit_schematic_components": schema(("schematic", "edits"), "schematic", "edits"),
            "batch_connect_to_net": schema(("schematic", "net_name", "pins"), "schematic", "net_name", "pins"),
            "batch_set_schematic_field_visibility": schema(("schematic", "edits"), "schematic", "edits"),
        },
        "sch_wiring": {
            "batch_delete_schematic_wire": schema(("schematic", "uuids"), "schematic", "uuids"),
        },
        "sch_components": {
            "set_schematic_page": schema(("schematic", "size"), "schematic", "size", "portrait"),
            "update_symbols_from_library": schema(("schematic",), "schematic", "dry_run", "allow_pin_moves", "references"),
        },
        "library": {
            "create_symbol": schema(("library_path", "name", "reference_prefix"), "library_path", "name", "reference_prefix", "reference_at", "value_at"),
        },
    }


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
                return deepcopy(complete_schematic_schemas()[toolset])

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

    def test_capability_gate_requires_all_invoked_input_contracts(self):
        from tools.lh60_design.schematic import require_schematic_capabilities

        class FakeClient:
            def __init__(self, toolset, tool, field, container):
                self.toolset = toolset
                self.tool = tool
                self.field = field
                self.container = container

            def tool_schemas(self, toolset):
                schemas = deepcopy(complete_schematic_schemas()[toolset])
                if toolset == self.toolset:
                    if self.container == "properties":
                        schemas[self.tool][self.container].pop(self.field)
                    else:
                        schemas[self.tool][self.container].remove(self.field)
                return schemas

        cases = (
            ("sch_components", "set_schematic_page", "size", "required"),
            ("sch_wiring", "batch_delete_schematic_wire", "uuids", "properties"),
            ("sch_batch", "batch_delete", "uuids", "properties"),
            ("sch_batch", "batch_place_components", "components", "required"),
            ("sch_batch", "batch_edit_schematic_components", "edits", "properties"),
            ("sch_batch", "batch_connect_to_net", "pins", "required"),
            ("sch_batch", "batch_set_schematic_field_visibility", "edits", "properties"),
            ("sch_components", "update_symbols_from_library", "allow_pin_moves", "properties"),
        )
        for toolset, tool, field, container in cases:
            with self.subTest(tool=tool, field=field, container=container):
                with self.assertRaisesRegex(RuntimeError, f"{tool}.*{field}"):
                    require_schematic_capabilities(FakeClient(toolset, tool, field, container))

    def test_apply_uses_frozen_call_order_and_payloads(self):
        from tools.lh60_design.schematic import apply_schematic, build_schematic_plan

        class FakeClient:
            def __init__(self):
                self.calls = []

            def tool_schemas(self, toolset):
                self.calls.append(("load", toolset))
                return deepcopy(complete_schematic_schemas()[toolset])

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
