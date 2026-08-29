import unittest
from copy import deepcopy
import json


def complete_schematic_schemas():
    def schema(required, *properties):
        return {"required": list(required), "properties": {name: {} for name in properties}}

    batch_edit_schema = schema(("schematic", "edits"), "schematic", "edits")
    batch_edit_schema["properties"]["edits"] = {
        "type": "array",
        "items": {
            "type": "object",
            "properties": {
                name: {"type": kind}
                for name, kind in (
                    ("reference", "string"),
                    ("value", "string"),
                    ("footprint", "string"),
                    ("fields", "object"),
                    ("in_bom", "boolean"),
                    ("on_board", "boolean"),
                    ("dnp", "boolean"),
                )
            },
        },
    }

    return {
        "sch_batch": {
            "batch_delete_schematic_components": schema(("schematic", "references"), "schematic", "references"),
            "batch_delete": schema(("schematic",), "schematic", "references", "uuids"),
            "batch_place_components": schema(("schematic", "components"), "schematic", "components"),
            "batch_edit_schematic_components": batch_edit_schema,
            "batch_set_schematic_field_visibility": schema(("schematic", "edits"), "schematic", "edits"),
            "batch_connect_to_net": schema(("schematic", "net_name", "pins"), "schematic", "net_name", "pins"),
        },
        "sch_wiring": {
            "batch_delete_schematic_wire": schema(("schematic", "uuids"), "schematic", "uuids"),
            "batch_add_no_connect": schema(("schematic", "positions"), "schematic", "positions"),
        },
        "sch_components": {
            "get_schematic_component": schema(("schematic", "reference"), "schematic", "reference"),
            "get_schematic_pin_locations": schema(("schematic", "reference"), "schematic", "reference"),
            "list_schematic_components": schema(("schematic",), "schematic"),
            "set_schematic_page": schema(("schematic", "size"), "schematic", "size", "portrait"),
            "update_symbols_from_library": schema(("schematic",), "schematic", "dry_run", "allow_pin_moves", "references"),
        },
    }


def tool_text_result(payload):
    return {"content": [{"type": "text", "text": json.dumps(payload)}]}


def empty_tool_result():
    return {"content": []}


def non_json_text_result(text="not-json"):
    return {"content": [{"type": "text", "text": text}]}


def json_scalar_result(value):
    return {"content": [{"type": "text", "text": json.dumps(value)}]}


class SchematicApplyContractTest(unittest.TestCase):
    def test_edit_payload_omits_fields_only_for_standard_matrix_symbols(self):
        from tools.lh60_design.schematic import (
            CORE_DIODE,
            CORE_SWITCH,
            SchematicComponent,
            _edit_payload,
            build_schematic_plan,
        )

        def component(kind, lib_id, reference):
            return SchematicComponent(
                kind=kind,
                lib_id=lib_id,
                reference=reference,
                value=reference,
                footprint="Test:Footprint",
                x=0.0,
                y=0.0,
                fields=(("LogicalNode", "KEY_1"),),
            )

        self.assertNotIn(
            "fields",
            _edit_payload(component("switch", CORE_SWITCH, "SW1")),
        )
        self.assertNotIn(
            "fields",
            _edit_payload(component("diode", CORE_DIODE, "D1")),
        )
        self.assertEqual(
            _edit_payload(component("switch", "custom:Switch", "SW2"))["fields"],
            {"LogicalNode": "KEY_1"},
        )
        self.assertEqual(
            _edit_payload(component("diode", "custom:Diode", "D2"))["fields"],
            {"LogicalNode": "KEY_1"},
        )

        plan_by_reference = {
            component.reference: component
            for component in build_schematic_plan().components
        }
        for reference in ("SW1", "D1"):
            planned = plan_by_reference[reference]
            self.assertTrue(planned.fields)
            self.assertNotIn("fields", _edit_payload(planned))
            self.assertEqual(_edit_payload(planned)["value"], planned.value)

    def test_ffc_connector_uses_interconnect_fields_without_power_flags(self):
        from tools.lh60_design.schematic import build_schematic_plan

        plan = build_schematic_plan()
        connectors = [component for component in plan.components if component.kind == "connector"]

        self.assertEqual([component.reference for component in connectors], ["J1"])
        self.assertEqual(connectors[0].lib_id, "lh60-interconnect:FPC-05F-24PH20")
        self.assertEqual(connectors[0].footprint, "lh60-interconnect:FPC-05F-24PH20")
        self.assertEqual(
            dict(connectors[0].fields),
            {"Manufacturer": "XUNPU", "MPN": "FPC-05F-24PH20", "LCSC": "C2856805"},
        )
        self.assertFalse(any(component.reference.startswith("#FLG") for component in plan.components))
        self.assertEqual(plan.no_connects, (__import__("tools.lh60_design.schematic", fromlist=["NoConnectPin"]).NoConnectPin("J1", "23"),))

    def test_capability_gate_requires_deployed_apply_tools(self):
        from tools.lh60_design.schematic import require_schematic_capabilities

        class FakeClient:
            def tool_schemas(self, toolset):
                return deepcopy(complete_schematic_schemas()[toolset])

        require_schematic_capabilities(FakeClient())

        class MissingDelete(FakeClient):
            def tool_schemas(self, toolset):
                schema = super().tool_schemas(toolset)
                if toolset == "sch_batch":
                    schema.pop("batch_delete")
                return schema

        with self.assertRaisesRegex(RuntimeError, "batch_delete"):
            require_schematic_capabilities(MissingDelete())

    def test_capability_gate_requires_read_tools(self):
        from tools.lh60_design.schematic import require_schematic_capabilities

        class FakeClient:
            def tool_schemas(self, toolset):
                schemas = deepcopy(complete_schematic_schemas()[toolset])
                if toolset == "sch_batch":
                    schemas["batch_edit_schematic_components"]["properties"]["edits"] = {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                name: {"type": kind}
                                for name, kind in (
                                    ("reference", "string"),
                                    ("value", "string"),
                                    ("footprint", "string"),
                                    ("fields", "object"),
                                    ("in_bom", "boolean"),
                                    ("on_board", "boolean"),
                                    ("dnp", "boolean"),
                                )
                            },
                        },
                    }
                return schemas

        require_schematic_capabilities(FakeClient())

        class MissingGetter(FakeClient):
            def tool_schemas(self, toolset):
                schemas = super().tool_schemas(toolset)
                if toolset == "sch_components":
                    schemas.pop("get_schematic_component")
                return schemas

        with self.assertRaisesRegex(RuntimeError, "get_schematic_component"):
            require_schematic_capabilities(MissingGetter())

        class MissingList(FakeClient):
            def tool_schemas(self, toolset):
                schemas = super().tool_schemas(toolset)
                if toolset == "sch_components":
                    schemas.pop("list_schematic_components")
                return schemas

        with self.assertRaisesRegex(RuntimeError, "list_schematic_components"):
            require_schematic_capabilities(MissingList())

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
            ("sch_batch", "batch_set_schematic_field_visibility", "edits", "required"),
            ("sch_batch", "batch_set_schematic_field_visibility", "edits", "properties"),
            ("sch_batch", "batch_connect_to_net", "pins", "required"),
            ("sch_components", "update_symbols_from_library", "allow_pin_moves", "properties"),
            ("sch_components", "update_symbols_from_library", "references", "properties"),
            ("sch_components", "get_schematic_pin_locations", "reference", "required"),
            ("sch_wiring", "batch_add_no_connect", "positions", "required"),
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
                if name == "update_symbols_from_library":
                    return tool_text_result(
                        {
                            "errors": [],
                            "pins_moved": [],
                            "updated": [],
                            "unchanged": [
                                "Device:D",
                                "Switch:SW_Push",
                                "lh60-interconnect:FPC-05F-24PH20",
                            ],
                        }
                    )
                if name == "get_schematic_pin_locations":
                    return tool_text_result({"pins": [{"pin_number": "23", "x": 302.26, "y": 101.6}]})
                if name == "batch_add_no_connect":
                    return tool_text_result({"added_count": 1})
                if name == "batch_set_schematic_field_visibility":
                    return tool_text_result(
                        {
                            "updated_count": 0,
                            "unchanged_count": len(arguments["edits"]),
                            "results": [
                                {
                                    "reference": edit["reference"],
                                    "reference_visible": {
                                        "old": edit["reference_visible"],
                                        "new": edit["reference_visible"],
                                    },
                                    "value_visible": {
                                        "old": edit["value_visible"],
                                        "new": edit["value_visible"],
                                    },
                                }
                                for edit in arguments["edits"]
                            ],
                        }
                    )
                if name == "reset_schematic_field_positions":
                    return tool_text_result(
                        {
                            "no_library_anchor": [],
                            "no_property": [],
                            "not_found": [],
                            "moved": ["U1.Reference", "U1.Value"],
                            "unchanged": [],
                        }
                    )
                if name == "batch_edit_schematic_components" and len(arguments["edits"]) == 3:
                    return tool_text_result(
                        {
                            "atomic": True,
                            "updated_count": 3,
                            "updated": [
                                {
                                    "reference": f"#FLG0{index}",
                                    "flags": {"in_bom": True, "on_board": False, "dnp": False},
                                    "changed_flags": ["dnp", "in_bom", "on_board"],
                                }
                                for index in range(1, 4)
                            ],
                            "unchanged": [],
                        }
                    )
                return {"content": [{"type": "text", "text": json.dumps({"ok": True})}]}

        client = FakeClient()
        apply_schematic(client, "/tmp/lh60-debug.kicad_sch")
        plan = build_schematic_plan()

        expected_tool_names = [
            *("load" for _ in range(3)),
            "set_schematic_page",
            "batch_place_components",
            "batch_edit_schematic_components",
            "update_symbols_from_library",
            "batch_set_schematic_field_visibility",
            "get_schematic_pin_locations",
            "batch_add_no_connect",
            *(["batch_connect_to_net"] * len({connection.net_name for connection in plan.connections})),
        ]
        self.assertEqual(
            [name for name, _ in client.calls],
            expected_tool_names,
        )
        self.assertEqual(
            client.calls[:3],
            [
                ("load", "sch_batch"),
                ("load", "sch_wiring"),
                ("load", "sch_components"),
            ],
        )
        self.assertEqual(
            client.calls[3],
            (
                "set_schematic_page",
                {
                    "schematic": "/tmp/lh60-debug.kicad_sch",
                    "size": "A3",
                    "portrait": False,
                },
            ),
        )
        place_name, place_arguments = client.calls[4]
        self.assertEqual(place_name, "batch_place_components")
        self.assertEqual(place_arguments["schematic"], "/tmp/lh60-debug.kicad_sch")
        self.assertEqual(len(place_arguments["components"]), 146)

        edit_name, edit_arguments = client.calls[5]
        self.assertEqual(edit_name, "batch_edit_schematic_components")
        self.assertEqual(edit_arguments["schematic"], "/tmp/lh60-debug.kicad_sch")
        self.assertEqual(len(edit_arguments["edits"]), 146)

        self.assertEqual(
            client.calls[6],
            (
                "update_symbols_from_library",
                {
                    "schematic": "/tmp/lh60-debug.kicad_sch",
                    "dry_run": False,
                    "allow_pin_moves": False,
                },
            ),
        )
        visibility_name, visibility_arguments = client.calls[7]
        self.assertEqual(visibility_name, "batch_set_schematic_field_visibility")
        self.assertEqual(visibility_arguments["schematic"], "/tmp/lh60-debug.kicad_sch")
        self.assertEqual(len(visibility_arguments["edits"]), 146)
        visibility_payload = {
            edit["reference"]: (edit["reference_visible"], edit["value_visible"])
            for edit in visibility_arguments["edits"]
        }
        self.assertEqual(visibility_payload["D1"], (False, False))
        self.assertEqual(visibility_payload["D70"], (False, False))
        self.assertEqual(visibility_payload["SW1"], (False, True))
        self.assertEqual(visibility_payload["SW76"], (False, True))
        self.assertEqual(visibility_payload["J1"], (True, True))
        self.assertFalse(any(reference.startswith("#FLG") for reference in visibility_payload))
        self.assertEqual(client.calls[8][0], "get_schematic_pin_locations")
        self.assertEqual(client.calls[9], ("batch_add_no_connect", {"schematic": "/tmp/lh60-debug.kicad_sch", "positions": [{"x": 302.26, "y": 101.6}]}))

        grouped_connections = {}
        for name, arguments in client.calls[10:]:
            self.assertEqual(name, "batch_connect_to_net")
            self.assertEqual(arguments["schematic"], "/tmp/lh60-debug.kicad_sch")
            grouped_connections[arguments["net_name"]] = arguments["pins"]
        self.assertEqual(len(grouped_connections), 88)
        self.assertEqual(
            grouped_connections["GND"],
            [
                {"reference": "J1", "pin_number": "1"},
                {"reference": "J1", "pin_number": "5"},
                {"reference": "J1", "pin_number": "9"},
                {"reference": "J1", "pin_number": "16"},
                {"reference": "J1", "pin_number": "20"},
                {"reference": "J1", "pin_number": "24"},
            ],
        )
        self.assertEqual(
            grouped_connections["COL0"],
            [
                {"reference": "D1", "pin_number": "2"},
                {"reference": "D11", "pin_number": "2"},
                {"reference": "D21", "pin_number": "2"},
                {"reference": "D31", "pin_number": "2"},
                {"reference": "D41", "pin_number": "2"},
                {"reference": "D51", "pin_number": "2"},
                {"reference": "D61", "pin_number": "2"},
                {"reference": "J1", "pin_number": "2"},
            ],
        )
        self.assertEqual(
            grouped_connections["ROW6"],
            [
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
                {"reference": "J1", "pin_number": "22"},
            ],
        )

        visibility = {
            edit.reference: (edit.reference_visible, edit.value_visible)
            for edit in plan.field_visibility
        }
        self.assertEqual(visibility["D1"], (False, False))
        self.assertEqual(visibility["SW1"], (False, True))
        self.assertEqual(visibility["J1"], (True, True))
        self.assertFalse(any(reference.startswith("#FLG") for reference in visibility))

    def test_apply_aborts_before_no_connects_when_field_visibility_accounting_is_incomplete(self):
        from tools.lh60_design.schematic import apply_schematic

        class FakeClient:
            def __init__(self, visibility_payload):
                self.calls = []
                self.visibility_payload = visibility_payload

            def tool_schemas(self, toolset):
                self.calls.append(("load", toolset))
                return deepcopy(complete_schematic_schemas()[toolset])

            def call_tool(self, name, arguments):
                self.calls.append((name, arguments))
                if name == "update_symbols_from_library":
                    return tool_text_result(
                        {
                            "errors": [],
                            "pins_moved": [],
                            "updated": [],
                            "unchanged": [
                                "Device:D",
                                "Switch:SW_Push",
                                "lh60-interconnect:FPC-05F-24PH20",
                            ],
                        }
                    )
                if name == "batch_set_schematic_field_visibility":
                    return tool_text_result(self.visibility_payload)
                return tool_text_result({"ok": True})

        bad_payloads = (
            {"updated_count": 0, "unchanged_count": 0, "results": []},
            {"updated_count": 0, "unchanged_count": 1, "results": [{"reference": "D1"}]},
            {
                "updated_count": 0,
                "unchanged_count": 1,
                "results": [
                    {
                        "reference": "D1",
                        "reference_visible": {"old": False, "new": True},
                        "value_visible": {"old": False, "new": False},
                    }
                ],
            },
            {
                "updated_count": 0,
                "unchanged_count": 1,
                "results": [
                    {
                        "reference": "UNKNOWN",
                        "reference_visible": {"old": False, "new": False},
                        "value_visible": {"old": False, "new": False},
                    }
                ],
            },
        )
        for payload in bad_payloads:
            client = FakeClient(payload)
            with self.subTest(payload=payload):
                with self.assertRaisesRegex(RuntimeError, "batch_set_schematic_field_visibility"):
                    apply_schematic(client, "/tmp/lh60-debug.kicad_sch")
                self.assertFalse(any(name == "batch_add_no_connect" for name, _ in client.calls))
                self.assertFalse(any(name == "batch_connect_to_net" for name, _ in client.calls))

    def test_apply_adds_one_pin_level_no_connect_after_symbol_refresh(self):
        from tools.lh60_design.schematic import apply_schematic

        class FakeClient:
            def __init__(self):
                self.calls = []

            def tool_schemas(self, toolset):
                schemas = deepcopy(complete_schematic_schemas()[toolset])
                if toolset == "sch_batch":
                    schemas["batch_edit_schematic_components"]["properties"]["edits"] = {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                name: {"type": kind}
                                for name, kind in (
                                    ("reference", "string"),
                                    ("value", "string"),
                                    ("footprint", "string"),
                                    ("fields", "object"),
                                    ("in_bom", "boolean"),
                                    ("on_board", "boolean"),
                                    ("dnp", "boolean"),
                                )
                            },
                        },
                    }
                return schemas

            def call_tool(self, name, arguments):
                self.calls.append((name, arguments))
                if name == "update_symbols_from_library":
                    return tool_text_result(
                        {
                            "errors": [],
                            "pins_moved": [],
                            "updated": [],
                            "unchanged": [
                                "Device:D",
                                "Switch:SW_Push",
                                "lh60-interconnect:FPC-05F-24PH20",
                            ],
                        }
                    )
                if name == "get_schematic_pin_locations":
                    return tool_text_result({"pins": [{"pin_number": "23", "x": 302.26, "y": 101.6}]})
                if name == "batch_add_no_connect":
                    return tool_text_result({"added_count": 1})
                if name == "batch_set_schematic_field_visibility":
                    return tool_text_result(
                        {
                            "updated_count": 0,
                            "unchanged_count": len(arguments["edits"]),
                            "results": [
                                {
                                    "reference": edit["reference"],
                                    "reference_visible": {
                                        "old": edit["reference_visible"],
                                        "new": edit["reference_visible"],
                                    },
                                    "value_visible": {
                                        "old": edit["value_visible"],
                                        "new": edit["value_visible"],
                                    },
                                }
                                for edit in arguments["edits"]
                            ],
                        }
                    )
                return tool_text_result({"ok": True})

        client = FakeClient()
        apply_schematic(client, "/tmp/lh60-debug.kicad_sch")

        no_connect_batches = [
            (index, arguments)
            for index, (name, arguments) in enumerate(client.calls)
            if name == "batch_add_no_connect"
        ]
        self.assertEqual(len(no_connect_batches), 1)
        batch_index, batch_arguments = no_connect_batches[0]
        self.assertEqual(
            batch_arguments,
            {
                "schematic": "/tmp/lh60-debug.kicad_sch",
                "positions": [{"x": 302.26, "y": 101.6}],
            },
        )
        final_refresh_index = next(
            index for index, (name, arguments) in enumerate(client.calls)
            if name == "update_symbols_from_library" and arguments.get("allow_pin_moves") is False
        )
        self.assertGreater(batch_index, final_refresh_index)

    def test_power_flag_instance_apply_helper_is_retired_noop(self):
        from tools.lh60_design.schematic import apply_power_flag_instance_flags

        class FakeClient:
            def __init__(self):
                self.calls = []

            def call_tool(self, name, arguments):
                self.calls.append((name, arguments))
                return tool_text_result(
                    {
                        "atomic": True,
                        "updated_count": 3,
                        "updated": [
                            {
                                "reference": f"#FLG0{index}",
                                "flags": {"in_bom": True, "on_board": False, "dnp": False},
                                "changed_flags": ["in_bom", "on_board", "dnp"],
                            }
                            for index in range(1, 4)
                        ],
                        "unchanged": [],
                    }
                )

        client = FakeClient()
        result = apply_power_flag_instance_flags(client, "/tmp/lh60-debug.kicad_sch")

        self.assertEqual(client.calls, [])
        self.assertTrue(result["atomic"])
        self.assertEqual(result["updated_count"], 0)

    def test_apply_aborts_before_wiring_on_symbol_refresh_diagnostics(self):
        from tools.lh60_design.schematic import apply_schematic

        class FakeClient:
            def __init__(self, refresh_payload):
                self.calls = []
                self.refresh_payload = refresh_payload

            def tool_schemas(self, toolset):
                self.calls.append(("load", toolset))
                return deepcopy(complete_schematic_schemas()[toolset])

            def call_tool(self, name, arguments):
                self.calls.append((name, arguments))
                if name == "update_symbols_from_library":
                    return tool_text_result(self.refresh_payload)
                return {"content": [{"type": "text", "text": json.dumps({"ok": True})}]}

        bad_payloads = (
            {"errors": ["stale"], "pins_moved": [], "updated": [], "unchanged": []},
            {"errors": [], "pins_moved": ["J1.1"], "updated": [], "unchanged": []},
        )
        for payload in bad_payloads:
            client = FakeClient(payload)
            with self.subTest(payload=payload):
                with self.assertRaisesRegex(RuntimeError, "pins_moved|errors"):
                    apply_schematic(client, "/tmp/lh60-debug.kicad_sch")
                self.assertFalse(any(name == "batch_add_no_connect" for name, _ in client.calls))
                self.assertFalse(any(name == "batch_connect_to_net" for name, _ in client.calls))

    def test_apply_aborts_before_wiring_on_missing_duplicate_or_nonfinite_no_connect_pin(self):
        from tools.lh60_design.schematic import apply_schematic

        class FakeClient:
            def __init__(self, pins):
                self.calls = []
                self.pins = pins

            def tool_schemas(self, toolset):
                self.calls.append(("load", toolset))
                return deepcopy(complete_schematic_schemas()[toolset])

            def call_tool(self, name, arguments):
                self.calls.append((name, arguments))
                if name == "update_symbols_from_library":
                    return tool_text_result(
                        {
                            "errors": [],
                            "pins_moved": [],
                            "updated": [],
                            "unchanged": ["lh60-interconnect:FPC-05F-24PH20"],
                        }
                    )
                if name == "get_schematic_pin_locations":
                    return tool_text_result({"pins": self.pins})
                if name == "batch_set_schematic_field_visibility":
                    return tool_text_result(
                        {
                            "updated_count": 0,
                            "unchanged_count": len(arguments["edits"]),
                            "results": [
                                {
                                    "reference": edit["reference"],
                                    "reference_visible": {
                                        "old": edit["reference_visible"],
                                        "new": edit["reference_visible"],
                                    },
                                    "value_visible": {
                                        "old": edit["value_visible"],
                                        "new": edit["value_visible"],
                                    },
                                }
                                for edit in arguments["edits"]
                            ],
                        }
                    )
                return {"content": [{"type": "text", "text": json.dumps({"ok": True})}]}

        cases = (
            ([], "expected exactly one J1.23"),
            ([{"pin_number": "23", "x": 1, "y": 2}, {"pin_number": "23", "x": 3, "y": 4}], "expected exactly one J1.23"),
            ([{"pin_number": "23", "x": float("nan"), "y": 2}], "non-finite"),
            ([{"pin_number": "23", "x": 1, "y": float("inf")}], "non-finite"),
        )
        for pins, message in cases:
            client = FakeClient(pins)
            with self.subTest(pins=pins):
                with self.assertRaisesRegex(RuntimeError, message):
                    apply_schematic(client, "/tmp/lh60-debug.kicad_sch")
                self.assertFalse(any(name == "batch_add_no_connect" for name, _ in client.calls))
                self.assertFalse(any(name == "batch_connect_to_net" for name, _ in client.calls))

    def test_apply_aborts_on_final_conservative_refresh_diagnostics(self):
        from tools.lh60_design.schematic import apply_schematic

        class FakeClient:
            def __init__(self, final_payload):
                self.calls = []
                self.final_payload = final_payload

            def tool_schemas(self, toolset):
                self.calls.append(("load", toolset))
                return deepcopy(complete_schematic_schemas()[toolset])

            def call_tool(self, name, arguments):
                self.calls.append((name, arguments))
                if name == "update_symbols_from_library" and arguments.get("references") == ["U1"]:
                    return tool_text_result(
                        {
                            "errors": [],
                            "pins_moved": [],
                            "updated": ["lh60-mcu:RP2040-Tiny"],
                            "unchanged": [],
                        }
                    )
                if name == "reset_schematic_field_positions":
                    return tool_text_result(
                        {
                            "no_library_anchor": [],
                            "no_property": [],
                            "not_found": [],
                            "moved": ["U1.Reference", "U1.Value"],
                            "unchanged": [],
                        }
                    )
                if name == "update_symbols_from_library":
                    return tool_text_result(self.final_payload)
                return {"content": [{"type": "text", "text": json.dumps({"ok": True})}]}

        for payload in (
            {"errors": ["stale"], "pins_moved": [], "updated": [], "unchanged": ["lh60-mcu:RP2040-Tiny"]},
            {"errors": [], "pins_moved": ["U1.1"], "updated": [], "unchanged": ["lh60-mcu:RP2040-Tiny"]},
        ):
            client = FakeClient(payload)
            with self.subTest(payload=payload):
                with self.assertRaisesRegex(RuntimeError, "pins_moved|errors"):
                    apply_schematic(client, "/tmp/lh60-debug.kicad_sch")

    def test_apply_aborts_before_wiring_on_empty_or_malformed_early_refresh_results(self):
        from tools.lh60_design.schematic import apply_schematic

        class FakeClient:
            def __init__(self, refresh_result):
                self.calls = []
                self.refresh_result = refresh_result

            def tool_schemas(self, toolset):
                self.calls.append(("load", toolset))
                return deepcopy(complete_schematic_schemas()[toolset])

            def call_tool(self, name, arguments):
                self.calls.append((name, arguments))
                if name == "update_symbols_from_library":
                    return self.refresh_result
                return {"content": [{"type": "text", "text": json.dumps({"ok": True})}]}

        for refresh_result in (
            empty_tool_result(),
            non_json_text_result(),
            json_scalar_result(["not-an-object"]),
        ):
            client = FakeClient(refresh_result)
            with self.subTest(refresh_result=refresh_result):
                with self.assertRaisesRegex(RuntimeError, "no JSON object text block|not valid JSON|not a JSON object"):
                    apply_schematic(client, "/tmp/lh60-debug.kicad_sch")
                self.assertFalse(any(name == "batch_connect_to_net" for name, _ in client.calls))

if __name__ == "__main__":
    unittest.main()
