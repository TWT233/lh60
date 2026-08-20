import unittest
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory


def disjoint_acceptance_schemas():
    def schema(required, *properties):
        return {"required": list(required), "properties": {item: {} for item in properties}}

    return {
        "sch_components": {
            "get_schematic_component": schema(("schematic", "reference"), "schematic", "reference"),
            "list_schematic_components": schema(("schematic",), "schematic"),
        },
        "sch_batch": {
            "get_schematic_layout": schema(("schematic",), "schematic"),
            "validate_wire_connections": schema(("schematic",), "schematic"),
            "validate_component_connections": schema(("schematic",), "schematic"),
        },
        "sch_wiring": {
            "batch_delete_schematic_wire": schema(("schematic", "uuids"), "schematic", "uuids"),
        },
        "sch_analysis": {
            name: schema(("schematic",), "schematic")
            for name in (
                "list_schematic_wires", "list_schematic_labels",
                "check_schematic_overlaps", "find_orphan_items",
                "find_shorted_nets", "find_single_pin_nets",
            )
        } | {
            "get_pin_net_name": schema(("schematic", "reference", "pin_number"), "schematic", "reference", "pin_number"),
        },
        "sch_export": {
            "export_netlist_summary": schema(("schematic",), "schematic"),
            "run_erc": schema(("schematic",), "schematic", "severity"),
            "export_schematic_svg": schema(("schematic", "output"), "schematic", "output"),
        },
        "library": {
            "get_symbol_info": schema(("lib_id",), "lib_id", "project_dir"),
            "get_footprint_info": schema(("footprint_path",), "footprint_path", "include_graphics", "project"),
        },
    }


def old_production_references():
    return (
        {"U1", *{f"#FLG{index:02d}" for index in range(1, 4)}}
        | {f"D{index}" for index in range(1, 71)}
        | {f"SW{index}" for index in range(1, 77) if index != 59}
        | {f"TP{index}" for index in range(1, 24)}
    )


def tool_text_result(payload):
    return {"content": [{"type": "text", "text": json.dumps(payload)}]}


def migration_references():
    from tools.lh60_design.schematic import build_schematic_plan

    return sorted({component.reference for component in build_schematic_plan().components})


def migration_component_payload(*, flags_on_board):
    from tools.lh60_design.schematic import POWER_FLAG_INSTANCE_FLAGS, build_schematic_plan

    normalized = []
    for component in build_schematic_plan().components:
        on_board = component.on_board
        if component.reference in POWER_FLAG_INSTANCE_FLAGS:
            on_board = flags_on_board
        normalized.append(
            {
                "reference": component.reference,
                "lib_id": component.lib_id,
                "value": component.value,
                "footprint": component.footprint,
                "in_bom": component.in_bom,
                "on_board": on_board,
                "dnp": component.dnp,
            }
        )
    return {"components": sorted(normalized, key=lambda item: item["reference"])}


def migration_component_details():
    return {
        reference: {"reference": reference, "uuid": f"uuid-{reference}"}
        for reference in migration_references()
    }


class SchematicAcceptanceContractTest(unittest.TestCase):
    def test_candidate_registers_every_footprint_library_needed_by_plan(self):
        from tools.check_schematic_acceptance import candidate_library_registrations

        registrations = candidate_library_registrations(self.id())
        self.assertEqual(
            {item["nickname"] for item in registrations["footprints"]},
            {"lh60-core", "lh60-mcu", "lh60-sockets"},
        )
        self.assertEqual(
            {item["nickname"] for item in registrations["symbols"]},
            {"lh60-core", "lh60-mcu"},
        )

    def test_accepts_expected_zero_wire_orphan_diagnostic(self):
        from tools.check_schematic_acceptance import classify_known_diagnostics

        self.assertEqual(
            classify_known_diagnostics(
                {"wire_count": 0, "label_count": 339},
                {"orphan_count": 339},
            ),
            {"orphan_labels": 339, "classification": "pin_end_labels"},
        )

    def test_rejects_unexpected_orphan_count(self):
        from tools.check_schematic_acceptance import classify_known_diagnostics

        with self.assertRaisesRegex(AssertionError, "orphan"):
            classify_known_diagnostics(
                {"wire_count": 0, "label_count": 339},
                {"orphan_count": 338},
            )

    def test_preflight_rejects_missing_or_duplicate_uuids(self):
        from tools.check_schematic_acceptance import assert_unique_nonempty_uuids

        with self.assertRaisesRegex(AssertionError, "unique"):
            assert_unique_nonempty_uuids([{"uuid": "same"}, {"uuid": "same"}], "wire")
        with self.assertRaisesRegex(AssertionError, "nonempty"):
            assert_unique_nonempty_uuids([{"uuid": ""}], "label")

    def test_candidate_evidence_requires_current_plan_head_gates_and_visual_approval(self):
        from tools.check_schematic_acceptance import assert_candidate_evidence

        evidence = {
            "plan_hash": "current-plan",
            "git_sha": "current-head",
            "acceptance": {"inventory": {"mcu": 1}},
            "gates": {"wire_validation": True, "component_validation": True, "erc_errors": 0, "erc_warnings": 0},
            "svg_sha256": "svg-sha",
            "render_sha256": "render-sha",
            "visual_approval": {"approved": True, "plan_hash": "current-plan", "git_sha": "current-head", "svg_sha256": "svg-sha", "render_sha256": "render-sha"},
        }
        assert_candidate_evidence(evidence, "current-plan", "current-head")

        for field, value in (("git_sha", "old-head"), ("svg_sha256", "other-svg")):
            rejected = dict(evidence)
            rejected[field] = value
            with self.subTest(field=field):
                with self.assertRaisesRegex(AssertionError, field):
                    assert_candidate_evidence(rejected, "current-plan", "current-head")

        rejected = dict(evidence)
        rejected["visual_approval"] = {"approved": True}
        with self.assertRaisesRegex(AssertionError, "visual approval"):
            assert_candidate_evidence(rejected, "current-plan", "current-head")

    def test_preflight_requires_exact_frozen_production_refs_and_uuid_counts(self):
        from tools.check_schematic_acceptance import assert_production_preflight

        expected_refs = (
            {"U1", *{f"J{index}" for index in range(1, 7)}, *{f"#FLG{index:02d}" for index in range(1, 4)}}
            | {f"D{index}" for index in range(1, 71)}
            | {f"SW{index}" for index in range(1, 77) if index != 59}
            | {f"TP{index}" for index in range(1, 24)}
        )
        state = {
            "layout": {"component_count": 172, "wire_count": 290, "label_count": 339},
            "wire_uuids": [f"wire-{index}" for index in range(290)],
            "label_uuids": [f"label-{index}" for index in range(339)],
            "references": sorted(expected_refs),
        }
        assert_production_preflight(state, expected_refs)

        state["label_uuids"].pop()
        with self.assertRaisesRegex(AssertionError, "label UUID count"):
            assert_production_preflight(state, expected_refs)

        state["label_uuids"].append("label-338")
        state["references"].remove("TP23")
        with self.assertRaisesRegex(AssertionError, "references"):
            assert_production_preflight(state, expected_refs)

    def test_production_transaction_refuses_before_delete_without_evidence(self):
        from tools.check_schematic_acceptance import run_production_transaction

        class FakeClient:
            def __init__(self):
                self.calls = []

            def call_tool(self, name, arguments):
                self.calls.append((name, arguments))
                return tool_text_result({"ok": True})

            def call_tool_json(self, name, arguments):
                self.calls.append((name, arguments))
                return {"ok": True}

            def tool_schemas(self, toolset):
                return {}

        client = FakeClient()
        with self.assertRaisesRegex(AssertionError, "candidate evidence"):
            run_production_transaction(client, Path("/tmp/lh60.kicad_sch"), None, Path("/tmp/evidence.json"))
        self.assertEqual(client.calls, [])

    def test_production_transaction_orders_once_and_persists_bound_evidence(self):
        from tools.check_schematic_acceptance import run_production_transaction

        with TemporaryDirectory() as directory:
            evidence_path = Path(directory) / "candidate.json"
            output_path = Path(directory) / "production.json"
            evidence = {
                "plan_hash": "plan", "git_sha": "head",
                "acceptance": {"inventory": {"mcu": 1}},
                "gates": {"wire_validation": True, "component_validation": True, "erc_errors": 0, "erc_warnings": 0},
                "svg_sha256": "svg", "render_sha256": "render",
                "visual_approval": {"approved": True, "plan_hash": "plan", "git_sha": "head", "svg_sha256": "svg", "render_sha256": "render"},
            }
            evidence_path.write_text(__import__("json").dumps(evidence))

            expected_refs = (
                {"U1", *{f"J{index}" for index in range(1, 7)}, *{f"#FLG{index:02d}" for index in range(1, 4)}}
                | {f"D{index}" for index in range(1, 71)}
                | {f"SW{index}" for index in range(1, 77) if index != 59}
                | {f"TP{index}" for index in range(1, 24)}
            )
            state = {
                "layout": {"component_count": 172, "wire_count": 290, "label_count": 339},
                "wire_uuids": [f"w{index}" for index in range(290)],
                "label_uuids": [f"l{index}" for index in range(339)],
                "references": sorted(expected_refs),
            }
            calls = []

            class FakeClient:
                def tool_schemas(self, toolset):
                    calls.append(("schema", toolset))
                    return {}

            def preflight(client, schematic):
                calls.append(("preflight", str(schematic)))
                return state

            def converge(client, schematic, current_state):
                calls.extend([("delete-wires", None), ("delete-labels", None), ("delete-components", None), ("empty", None), ("apply", None)])

            def acceptance(client, schematic, output):
                calls.append(("post-acceptance", str(schematic)))
                return {"semantic": {"NET": [("U1", "1")]}, "svg_sha256": "prod-svg"}

            def new_candidate(client, directory, *, regenerate_libraries):
                calls.append(("second-candidate", str(directory)))
                self.assertFalse(regenerate_libraries)
                return Path(directory) / "candidate.kicad_sch"

            def candidate_acceptance(client, schematic, output):
                calls.append(("candidate-acceptance", str(schematic)))
                return {"semantic": {"NET": [("U1", "1")]}, "svg_sha256": "candidate-svg"}

            result = run_production_transaction(
                FakeClient(), Path("/tmp/lh60.kicad_sch"), evidence_path, output_path,
                expected_plan_hash="plan", expected_git_sha="head", expected_references=expected_refs,
                preflight_fn=preflight, converge_fn=converge, acceptance_fn=acceptance, candidate_fn=new_candidate, candidate_acceptance_fn=candidate_acceptance, capabilities_fn=lambda client: None, safety_fn=lambda schematic, board: {"pcb_sha256": "pcb"},
            )
            self.assertEqual([name for name, _ in calls], ["preflight", "delete-wires", "delete-labels", "delete-components", "empty", "apply", "post-acceptance", "second-candidate", "candidate-acceptance"])
            self.assertTrue(output_path.is_file())
            self.assertEqual(result["candidate_evidence"]["svg_sha256"], "svg")

    def test_production_transaction_refuses_before_delete_when_global_capability_is_missing(self):
        from tools.check_schematic_acceptance import run_production_transaction

        calls = []
        class FakeClient:
            pass

        with TemporaryDirectory() as directory:
            evidence_path = Path(directory) / "candidate.json"
            evidence_path.write_text(__import__("json").dumps({
                "plan_hash": "plan", "git_sha": "head", "acceptance": {"ok": True},
                "gates": {"wire_validation": True, "component_validation": True, "erc_errors": 0, "erc_warnings": 0},
                "svg_sha256": "svg", "render_sha256": "render",
                "visual_approval": {"approved": True, "plan_hash": "plan", "git_sha": "head", "svg_sha256": "svg", "render_sha256": "render"},
            }))
            with self.assertRaisesRegex(RuntimeError, "flip_component"):
                run_production_transaction(
                    FakeClient(), Path("/tmp/lh60.kicad_sch"), evidence_path, Path(directory) / "production.json",
                    expected_plan_hash="plan", expected_git_sha="head",
                    capabilities_fn=lambda client: (_ for _ in ()).throw(RuntimeError("flip_component missing")),
                    preflight_fn=lambda client, schematic: calls.append("preflight"),
                )
        self.assertEqual(calls, [])

    def test_global_production_capability_gate_requires_pcb_flip_contract(self):
        from tools.check_schematic_acceptance import require_production_capabilities
        from tools.verify_schematic_apply import complete_schematic_schemas

        class FakeClient:
            def tool_schemas(self, toolset):
                schemas = complete_schematic_schemas()
                if toolset in schemas:
                    return schemas[toolset]
                if toolset == "sch_export":
                    return {
                        "update_pcb_from_schematic": {
                            "required": ["schematic", "board"],
                            "properties": {name: {} for name in ("schematic", "board", "dry_run", "expected_plan_revision")},
                        }
                    }
                if toolset == "pcb_components":
                    return {}
                raise AssertionError(toolset)

        with self.assertRaisesRegex(RuntimeError, "flip_component"):
            require_production_capabilities(FakeClient())

    def test_narrow_migration_capability_gate_requires_read_tools_before_write(self):
        from tools.check_schematic_acceptance import require_power_flag_instance_migration_capabilities
        from tools.verify_schematic_apply import complete_schematic_schemas

        class FakeClient:
            def tool_schemas(self, toolset):
                schemas = complete_schematic_schemas()
                if toolset in schemas:
                    data = deepcopy(schemas[toolset])
                elif toolset == "sch_analysis":
                    data = {
                        "list_schematic_wires": {"required": ["schematic"], "properties": {"schematic": {}}},
                        "list_schematic_labels": {"required": ["schematic"], "properties": {"schematic": {}}},
                    }
                elif toolset == "sch_export":
                    data = {
                        "export_netlist_summary": {"required": ["schematic"], "properties": {"schematic": {}}},
                    }
                else:
                    raise AssertionError(toolset)
                if toolset == "sch_batch":
                    data["batch_edit_schematic_components"]["properties"]["edits"] = {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                name: {"type": kind}
                                for name, kind in (
                                    ("reference", "string"),
                                    ("in_bom", "boolean"),
                                    ("on_board", "boolean"),
                                    ("dnp", "boolean"),
                                )
                            },
                        },
                    }
                return data

        require_power_flag_instance_migration_capabilities(FakeClient())

        class MissingAnalysis(FakeClient):
            def tool_schemas(self, toolset):
                data = super().tool_schemas(toolset)
                if toolset == "sch_analysis":
                    data.pop("list_schematic_labels")
                return data

        with self.assertRaisesRegex(RuntimeError, "list_schematic_labels"):
            require_power_flag_instance_migration_capabilities(MissingAnalysis())

        class MissingNetlist(FakeClient):
            def tool_schemas(self, toolset):
                data = super().tool_schemas(toolset)
                if toolset == "sch_export":
                    data.pop("export_netlist_summary")
                return data

        with self.assertRaisesRegex(RuntimeError, "export_netlist_summary"):
            require_power_flag_instance_migration_capabilities(MissingNetlist())

    def test_narrow_migration_applies_one_flag_batch_and_preserves_identities(self):
        from tools.check_schematic_acceptance import migrate_power_flag_instance_flags

        component_payload = migration_component_payload(flags_on_board=True)
        wires = {"wires": [{"uuid": "wire-1"}, {"uuid": "wire-2"}]}
        labels = {"labels": [{"uuid": "label-1"}, {"uuid": "label-2"}]}
        netlist_before = {
            "components": [
                {"reference": "U1", "pins": [{"number": "23", "net": "VSYS"}]},
                {"reference": "J1", "pins": [{"number": "1", "net": "VSYS"}]},
                {"reference": "J1", "pins": [{"number": "2", "net": "3V3"}]},
                {"reference": "J1", "pins": [{"number": "3", "net": "GND"}]},
                {"reference": "#FLG01", "pins": [{"number": "1", "net": "VSYS"}]},
                {"reference": "#FLG02", "pins": [{"number": "1", "net": "3V3"}]},
                {"reference": "#FLG03", "pins": [{"number": "1", "net": "GND"}]},
            ]
        }
        netlist_after = deepcopy(netlist_before)
        batch_result = {
            "atomic": True,
            "updated_count": 3,
            "updated": [
                {
                    "reference": f"#FLG0{index}",
                    "flags": {"in_bom": True, "on_board": False, "dnp": False},
                    "changed_flags": ["on_board"],
                }
                for index in range(1, 4)
            ],
            "unchanged": [],
        }
        calls = []

        class FakeClient:
            def __init__(self):
                self.component_calls = 0
                self.component_details = migration_component_details()

            def tool_schemas(self, toolset):
                from tools.verify_schematic_apply import complete_schematic_schemas

                schemas = complete_schematic_schemas()
                if toolset in schemas:
                    data = deepcopy(schemas[toolset])
                elif toolset == "sch_analysis":
                    data = {
                        "list_schematic_wires": {"required": ["schematic"], "properties": {"schematic": {}}},
                        "list_schematic_labels": {"required": ["schematic"], "properties": {"schematic": {}}},
                    }
                elif toolset == "sch_export":
                    data = {
                        "export_netlist_summary": {"required": ["schematic"], "properties": {"schematic": {}}},
                    }
                else:
                    raise AssertionError(toolset)
                if toolset == "sch_batch":
                    data["batch_edit_schematic_components"]["properties"]["edits"] = {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                name: {"type": kind}
                                for name, kind in (
                                    ("reference", "string"),
                                    ("in_bom", "boolean"),
                                    ("on_board", "boolean"),
                                    ("dnp", "boolean"),
                                )
                            },
                        },
                    }
                return data

            def call_tool(self, name, arguments):
                calls.append((name, arguments))
                if name == "batch_edit_schematic_components":
                    return tool_text_result(batch_result)
                raise AssertionError(name)

            def call_tool_json(self, name, arguments):
                calls.append((name, arguments))
                if name == "list_schematic_components":
                    self.component_calls += 1
                    return migration_component_payload(flags_on_board=self.component_calls == 1)
                if name == "get_schematic_component":
                    return deepcopy(self.component_details[arguments["reference"]])
                if name == "list_schematic_wires":
                    return deepcopy(wires)
                if name == "list_schematic_labels":
                    return deepcopy(labels)
                if name == "export_netlist_summary":
                    return deepcopy(netlist_after if self.component_calls > 1 else netlist_before)
                raise AssertionError(name)

        result = migrate_power_flag_instance_flags(
            FakeClient(),
            Path("/tmp/lh60.kicad_sch"),
            Path("/tmp/evidence.json"),
            safety_fn=lambda schematic, board: {
                "schematic_sha256": "7ae8a38afc453579f8f24de23e57772eff73056d12acd4fd9fcc6f0bf57533f9",
                "pcb_sha256": "0a5722685ee378e9c9b240aa01a1f151f382cab83216edfa14a0663a1ac80664",
            },
            component_hash_fn=lambda components: "028d14843b05b9483765e68bb59fc9e5bd8e0d8b9a2e60b539314c6578c79d18",
            pin_hash_fn=lambda client, schematic: calls.append(("export_netlist_summary", {"schematic": str(schematic)})) or "85f400c94abdb1e70a6da80177fbba76b774a3105d0b15081b54f318a06d7f58",
            write_json_fn=lambda path, payload: calls.append(("write_json", {"path": str(path), "payload": payload})),
        )
        batch_calls = [call for call in calls if call[0] == "batch_edit_schematic_components"]
        self.assertEqual(len(batch_calls), 1)
        self.assertEqual(
            batch_calls[0][1],
            {
                "schematic": "/tmp/lh60.kicad_sch",
                "edits": [
                    {"reference": "#FLG01", "in_bom": True, "on_board": False, "dnp": False},
                    {"reference": "#FLG02", "in_bom": True, "on_board": False, "dnp": False},
                    {"reference": "#FLG03", "in_bom": True, "on_board": False, "dnp": False},
                ],
            },
        )
        self.assertEqual(
            [name for name, _ in calls].count("get_schematic_component"),
            len(migration_references()) * 2,
        )
        getter_coverages = []
        current = []
        for name, arguments in calls:
            if name == "list_schematic_components":
                if current:
                    getter_coverages.append(sorted(current))
                    current = []
                continue
            if name == "get_schematic_component":
                current.append(arguments["reference"])
        getter_coverages.append(sorted(current))
        self.assertEqual(
            getter_coverages,
            [migration_references(), migration_references()],
        )
        self.assertEqual(result["batch"]["updated_count"], 3)
        self.assertEqual(len(result["before"]["component_identities"]), len(migration_references()))
        self.assertEqual(result["before"]["component_identities"], result["after"]["component_identities"])

    def test_power_flag_state_query_requires_exact_getter_identities(self):
        from tools.check_schematic_acceptance import _query_power_flag_instance_state

        class FakeClient:
            def __init__(self, details, components=None):
                self.details = details
                self.components = deepcopy(components or migration_component_payload(flags_on_board=True))
                self.calls = []

            def call_tool_json(self, name, arguments):
                self.calls.append((name, arguments))
                if name == "list_schematic_components":
                    return deepcopy(self.components)
                if name == "get_schematic_component":
                    return deepcopy(self.details.get(arguments["reference"], {}))
                if name == "list_schematic_wires":
                    return {"wires": [{"uuid": "wire-1"}]}
                if name == "list_schematic_labels":
                    return {"labels": [{"uuid": "label-1"}]}
                raise AssertionError(name)

        ok_client = FakeClient(
            migration_component_details()
        )
        result = _query_power_flag_instance_state(ok_client, Path("/tmp/lh60.kicad_sch"))
        self.assertEqual(
            len(result["component_identities"]),
            len(migration_references()),
        )
        self.assertEqual(result["flag_states"]["#FLG01"]["uuid"], "uuid-#FLG01")
        self.assertEqual(
            sorted(arguments["reference"] for name, arguments in ok_client.calls if name == "get_schematic_component"),
            migration_references(),
        )
        self.assertEqual(
            result["component_identities"][0],
            ("#FLG01", "uuid-#FLG01"),
        )

        error_cases = (
            (
                "extra-flag-ref",
                migration_component_details(),
                {
                    "components": migration_component_payload(flags_on_board=True)["components"]
                    + [{
                        "reference": "#FLG04",
                        "lib_id": "lh60-core:PowerFlag",
                        "value": "PWR_FLAG",
                        "footprint": "",
                        "in_bom": True,
                        "on_board": True,
                        "dnp": False,
                    }]
                },
                AssertionError,
                "power flag reference set mismatch",
            ),
            (
                "missing-list-ref",
                migration_component_details(),
                {
                    "components": [
                        component
                        for component in migration_component_payload(flags_on_board=True)["components"]
                        if component["reference"] != "U1"
                    ]
                },
                AssertionError,
                "reference inventory mismatch",
            ),
            (
                "duplicate-list-ref",
                migration_component_details(),
                {
                    "components": migration_component_payload(flags_on_board=True)["components"][:-1]
                    + [deepcopy(migration_component_payload(flags_on_board=True)["components"][0])]
                },
                AssertionError,
                "unique",
            ),
            (
                "empty-list-ref",
                migration_component_details(),
                {
                    "components": migration_component_payload(flags_on_board=True)["components"][:-1]
                    + [{**migration_component_payload(flags_on_board=True)["components"][-1], "reference": ""}]
                },
                AssertionError,
                "nonempty",
            ),
            (
                "missing-getter-detail",
                {
                    reference: detail
                    for reference, detail in migration_component_details().items()
                    if reference != "U1"
                },
                None,
                AssertionError,
                "identity mismatch",
            ),
            (
                "mismatched-getter-reference",
                {**migration_component_details(), "U1": {"reference": "WRONG", "uuid": "uuid-U1"}},
                None,
                AssertionError,
                "identity mismatch",
            ),
            (
                "duplicate-uuid",
                {**migration_component_details(), "U1": {"reference": "U1", "uuid": "uuid-#FLG01"}},
                None,
                AssertionError,
                "unique",
            ),
            (
                "empty-getter-uuid",
                {**migration_component_details(), "U1": {"reference": "U1", "uuid": ""}},
                None,
                AssertionError,
                "nonempty",
            ),
        )
        for case in error_cases:
            if len(case) == 5:
                label, details, components, error_type, message = case
            else:
                label, details, error_type, message = case
                components = None
            with self.subTest(label=label):
                client = FakeClient(details, components=components)
                with self.assertRaisesRegex(error_type, message):
                    _query_power_flag_instance_state(client, Path("/tmp/lh60.kicad_sch"))

    def test_narrow_migration_rejects_non_flag_component_identity_drift(self):
        from tools.check_schematic_acceptance import assert_power_flag_migration_post_state

        before = {
            "component_identities": tuple(
                (reference, f"uuid-{reference}")
                for reference in migration_references()
            ),
            "wire_uuids": ["wire-1"],
            "label_uuids": ["label-1"],
            "flag_states": {
                "#FLG01": {"uuid": "uuid-#FLG01", "in_bom": True, "on_board": True, "dnp": False},
                "#FLG02": {"uuid": "uuid-#FLG02", "in_bom": True, "on_board": True, "dnp": False},
                "#FLG03": {"uuid": "uuid-#FLG03", "in_bom": True, "on_board": True, "dnp": False},
            },
            "all_flags": {
                "#FLG01": {"uuid": "", "in_bom": True, "on_board": True, "dnp": False},
                "#FLG02": {"uuid": "", "in_bom": True, "on_board": True, "dnp": False},
                "#FLG03": {"uuid": "", "in_bom": True, "on_board": True, "dnp": False},
            },
        }
        after = {
            **before,
            "component_identities": tuple(
                (reference, f"uuid-{reference}")
                for reference in migration_references()
            ),
            "flag_states": {
                "#FLG01": {"uuid": "uuid-#FLG01", "in_bom": True, "on_board": False, "dnp": False},
                "#FLG02": {"uuid": "uuid-#FLG02", "in_bom": True, "on_board": False, "dnp": False},
                "#FLG03": {"uuid": "uuid-#FLG03", "in_bom": True, "on_board": False, "dnp": False},
            },
            "all_flags": {
                "#FLG01": {"uuid": "", "in_bom": True, "on_board": False, "dnp": False},
                "#FLG02": {"uuid": "", "in_bom": True, "on_board": False, "dnp": False},
                "#FLG03": {"uuid": "", "in_bom": True, "on_board": False, "dnp": False},
            },
        }

        drifted = {
            **after,
            "component_identities": tuple(
                ("U1", "uuid-drifted-U1") if reference == "U1" else (reference, uuid)
                for reference, uuid in after["component_identities"]
            ),
        }
        with self.assertRaisesRegex(AssertionError, "component identity drift"):
            assert_power_flag_migration_post_state(before, drifted)

    def test_narrow_migration_rejects_pin_hash_drift_from_runtime_netlist(self):
        from tools.check_schematic_acceptance import migrate_power_flag_instance_flags

        component_payload = migration_component_payload(flags_on_board=False)

        class FakeClient:
            def tool_schemas(self, toolset):
                from tools.verify_schematic_apply import complete_schematic_schemas

                schemas = complete_schematic_schemas()
                if toolset in schemas:
                    data = deepcopy(schemas[toolset])
                elif toolset == "sch_analysis":
                    data = {
                        "list_schematic_wires": {"required": ["schematic"], "properties": {"schematic": {}}},
                        "list_schematic_labels": {"required": ["schematic"], "properties": {"schematic": {}}},
                    }
                elif toolset == "sch_export":
                    data = {
                        "export_netlist_summary": {"required": ["schematic"], "properties": {"schematic": {}}},
                    }
                else:
                    raise AssertionError(toolset)
                return data

            def call_tool(self, name, arguments):
                if name == "batch_edit_schematic_components":
                    return tool_text_result(
                        {
                            "atomic": True,
                            "updated_count": 3,
                            "updated": [
                                {"reference": "#FLG01", "flags": {"in_bom": True, "on_board": False, "dnp": False}, "changed_flags": []},
                                {"reference": "#FLG02", "flags": {"in_bom": True, "on_board": False, "dnp": False}, "changed_flags": []},
                                {"reference": "#FLG03", "flags": {"in_bom": True, "on_board": False, "dnp": False}, "changed_flags": []},
                            ],
                            "unchanged": [],
                        }
                    )
                raise AssertionError(name)

            def call_tool_json(self, name, arguments):
                if name == "list_schematic_components":
                    return deepcopy(component_payload)
                if name == "get_schematic_component":
                    return migration_component_details()[arguments["reference"]]
                if name == "list_schematic_wires":
                    return {"wires": [{"uuid": "wire-1"}]}
                if name == "list_schematic_labels":
                    return {"labels": [{"uuid": "label-1"}]}
                if name == "export_netlist_summary":
                    return {"components": [{"reference": "U1", "pins": [{"number": "99", "net": "WRONG"}]}]}
                raise AssertionError(name)

        with self.assertRaisesRegex(AssertionError, "pin contract hash drift"):
            migrate_power_flag_instance_flags(
                FakeClient(),
                Path("/tmp/lh60.kicad_sch"),
                Path("/tmp/evidence.json"),
                safety_fn=lambda schematic, board: {
                    "schematic_sha256": "7ae8a38afc453579f8f24de23e57772eff73056d12acd4fd9fcc6f0bf57533f9",
                    "pcb_sha256": "0a5722685ee378e9c9b240aa01a1f151f382cab83216edfa14a0663a1ac80664",
                },
                component_hash_fn=lambda components: "028d14843b05b9483765e68bb59fc9e5bd8e0d8b9a2e60b539314c6578c79d18",
                write_json_fn=lambda *unused: None,
            )

    def test_narrow_migration_rejects_identity_or_non_flag_drift(self):
        from tools.check_schematic_acceptance import assert_power_flag_migration_post_state

        before = {
            "components": [
                {"reference": "#FLG01", "uuid": "flag-1", "in_bom": True, "on_board": True, "dnp": False},
                {"reference": "#FLG02", "uuid": "flag-2", "in_bom": True, "on_board": True, "dnp": False},
                {"reference": "#FLG03", "uuid": "flag-3", "in_bom": True, "on_board": True, "dnp": False},
                {"reference": "U1", "uuid": "u1", "in_bom": None, "on_board": None, "dnp": None},
            ],
            "wire_uuids": ["wire-1"],
            "label_uuids": ["label-1"],
        }
        after = {
            "components": [
                {"reference": "#FLG01", "uuid": "flag-1", "in_bom": True, "on_board": False, "dnp": False},
                {"reference": "#FLG02", "uuid": "flag-2", "in_bom": True, "on_board": False, "dnp": False},
                {"reference": "#FLG03", "uuid": "flag-3", "in_bom": True, "on_board": False, "dnp": False},
                {"reference": "U1", "uuid": "u1", "in_bom": None, "on_board": None, "dnp": None},
            ],
            "wire_uuids": ["wire-1"],
            "label_uuids": ["label-1"],
        }
        assert_power_flag_migration_post_state(before, after)

        drifted = deepcopy(after)
        drifted["components"][3]["dnp"] = True
        with self.assertRaisesRegex(AssertionError, "unrelated flag drift"):
            assert_power_flag_migration_post_state(before, drifted)

        rewired = deepcopy(after)
        rewired["wire_uuids"] = ["wire-2"]
        with self.assertRaisesRegex(AssertionError, "wire identity"):
            assert_power_flag_migration_post_state(before, rewired)

    def test_semantic_comparison_normalizes_net_and_pin_order(self):
        from tools.check_schematic_acceptance import assert_semantically_equal

        assert_semantically_equal(
            {"nets": [{"name": "ROW0", "pins": [{"reference": "D1", "pin_number": "2"}, {"reference": "U1", "pin_number": "11"}]}]},
            {"nets": [{"net_name": "ROW0", "pins": [{"pin_number": 11, "reference": "U1"}, {"pin_number": 2, "reference": "D1"}]}]},
        )
        with self.assertRaisesRegex(AssertionError, "semantic mismatch"):
            assert_semantically_equal(
                {"nets": [{"name": "ROW0", "pins": [{"reference": "D1", "pin_number": "2"}]}]},
                {"nets": [{"name": "ROW0", "pins": [{"reference": "D1", "pin_number": "1"}]}]},
            )

    def test_frozen_production_reference_set_is_exactly_172_without_headers(self):
        from tools.check_schematic_acceptance import EXPECTED_PRODUCTION_REFERENCES

        self.assertEqual(EXPECTED_PRODUCTION_REFERENCES, old_production_references())
        self.assertEqual(len(EXPECTED_PRODUCTION_REFERENCES), 172)
        self.assertFalse(any(reference.startswith("J") for reference in EXPECTED_PRODUCTION_REFERENCES))

    def test_acceptance_schema_gate_rejects_wrong_toolset_ownership(self):
        from tools.check_schematic_acceptance import _load_acceptance_toolsets

        class FakeClient:
            def tool_schemas(self, toolset):
                schemas = deepcopy(disjoint_acceptance_schemas()[toolset])
                if toolset == "sch_analysis":
                    schemas.pop("list_schematic_wires")
                return schemas

        with self.assertRaisesRegex(RuntimeError, "list_schematic_wires"):
            _load_acceptance_toolsets(FakeClient())

    def test_acceptance_schema_gate_allows_property_only_erc_severity_and_rejects_missing_property(self):
        from tools.check_schematic_acceptance import _load_acceptance_toolsets

        class FakeClient:
            def tool_schemas(self, toolset):
                return deepcopy(disjoint_acceptance_schemas()[toolset])

        _load_acceptance_toolsets(FakeClient())

        class MissingSeverity(FakeClient):
            def tool_schemas(self, toolset):
                schemas = super().tool_schemas(toolset)
                if toolset == "sch_export":
                    schemas["run_erc"]["properties"].pop("severity")
                return schemas

        with self.assertRaisesRegex(RuntimeError, "run_erc.*severity"):
            _load_acceptance_toolsets(MissingSeverity())

    def test_acceptance_rejects_component_contract_or_layout_drift(self):
        from tools import check_schematic_acceptance as checker

        with TemporaryDirectory() as directory:
            svg_path = Path(directory) / "candidate.svg"
            svg_path.write_text('<svg width="420mm" height="297mm"/>')
            plan_components = [
                {"reference": "U1", "lib_id": "lh60-mcu:RP2040-Tiny", "value": "RP2040-Tiny", "footprint": "lh60-mcu:MCU_RP2040-Tiny_SMD"},
                {"reference": "J1", "lib_id": "lh60-core:Conn_01x03", "value": "PWR", "footprint": "lh60-core:PinHeader_1x03_P2.54mm_Vertical"},
            ]
            data = {
                "components": {"components": deepcopy(plan_components)},
                "netlist": {"components": [
                    {**plan_components[0], "pins": [{"number": "23", "net": "VSYS"}]},
                    {**plan_components[1], "pins": [{"number": "1", "net": "VSYS"}]},
                ]},
                "layout": {"component_count": 2, "wire_count": 0, "label_count": 339},
                "overlaps": {"overlap_count": 0},
                "single_pin_nets": {"single_pin_net_count": 0, "nets": []},
                "svg_path": str(svg_path),
            }
            component_hash = checker.FROZEN_COMPONENT_SHA256
            pin_hash = checker.FROZEN_PIN_SHA256
            connector_map = checker.FROZEN_CONNECTOR_MAP
            checker.FROZEN_COMPONENT_SHA256 = checker._stable_hash(checker.normalize_actual_components(plan_components))
            checker.FROZEN_PIN_SHA256 = checker._stable_hash(checker.normalize_exported_pins(data["netlist"]))
            checker.FROZEN_CONNECTOR_MAP = {"J1": (("1", "VSYS"),)}
            try:
                checker.assert_frozen_acceptance(data)
                data["components"]["components"][1]["footprint"] = "wrong"
                with self.assertRaisesRegex(AssertionError, "component contract"):
                    checker.assert_frozen_acceptance(data)
            finally:
                checker.FROZEN_COMPONENT_SHA256 = component_hash
                checker.FROZEN_PIN_SHA256 = pin_hash
                checker.FROZEN_CONNECTOR_MAP = connector_map

    def test_complete_acceptance_invokes_frozen_plan_gate(self):
        from tools.check_schematic_acceptance import _assert_acceptance

        data = {
            "components": {"components": []},
            "layout": {"wire_count": 0, "label_count": 339},
            "shorts": {"short_count": 0},
            "wire_validation": {"valid": True}, "component_validation": {"valid": True},
            "erc": {"errors": 0, "warnings": 0}, "orphans": {"orphan_count": 339},
        }
        with self.assertRaisesRegex(AssertionError, "inventory mismatch"):
            _assert_acceptance(data)

    def test_cli_exposes_narrow_migration_mode_and_requires_output(self):
        import sys
        from unittest import mock

        from tools import check_schematic_acceptance as checker

        with mock.patch.object(sys, "argv", ["check_schematic_acceptance.py", "--migrate-power-flag-instance-flags"]):
            with self.assertRaisesRegex(SystemExit, "2"):
                checker.main()

    def test_cli_rejects_migration_mode_with_other_modes(self):
        import sys
        from unittest import mock

        from tools import check_schematic_acceptance as checker

        for argv in (
            ["check_schematic_acceptance.py", "--migrate-power-flag-instance-flags", "--production", "--output", "/tmp/out.json", "--candidate-evidence", "/tmp/evidence.json"],
            ["check_schematic_acceptance.py", "--migrate-power-flag-instance-flags", "--preflight", "--output", "/tmp/out.json"],
            ["check_schematic_acceptance.py", "--migrate-power-flag-instance-flags", "--record-visual-approval", "--output", "/tmp/out.json"],
        ):
            with self.subTest(argv=argv):
                with mock.patch.object(sys, "argv", argv):
                    with self.assertRaisesRegex(SystemExit, "2"):
                        checker.main()

    def test_cli_dispatches_only_narrow_migration_mode(self):
        import sys
        from unittest import mock

        from tools import check_schematic_acceptance as checker

        calls = []

        class FakeClient:
            def __enter__(self):
                calls.append(("client-enter", None))
                return self

            def __exit__(self, *unused):
                calls.append(("client-exit", None))
                return None

        with mock.patch.object(sys, "argv", ["check_schematic_acceptance.py", "--migrate-power-flag-instance-flags", "--output", "/tmp/out.json"]):
            with mock.patch.object(checker, "McpClient", return_value=FakeClient()):
                with mock.patch.object(checker, "migrate_power_flag_instance_flags", side_effect=lambda client, schematic, output: calls.append(("migrate", (str(schematic), str(output)))) or {"mode": "power-flag-instance-migration"}):
                    with mock.patch.object(checker, "run_production_transaction", side_effect=AssertionError("production-called")):
                        with mock.patch.object(checker, "preflight", side_effect=AssertionError("preflight-called")):
                            with mock.patch.object(checker, "candidate", side_effect=AssertionError("candidate-called")):
                                checker.main()

        self.assertEqual(calls[0][0], "client-enter")
        self.assertEqual(calls[1], ("migrate", (str(checker.SCHEMATIC), "/tmp/out.json")))
        self.assertEqual(calls[-1][0], "client-exit")

    def test_approval_recording_requires_human_identity_and_complete_checklist(self):
        from tools.check_schematic_acceptance import record_visual_approval

        with TemporaryDirectory() as directory:
            evidence_path = Path(directory) / "candidate.json"
            output_path = Path(directory) / "approved.json"
            evidence = {"plan_hash": "plan", "git_sha": "head", "svg_sha256": "svg", "render_sha256": "render"}
            evidence_path.write_text(json.dumps(evidence))
            with self.assertRaisesRegex(AssertionError, "checklist"):
                record_visual_approval(evidence_path, output_path, "reviewer", {"u1": True})
            approval = record_visual_approval(
                evidence_path, output_path, "reviewer",
                {"u1": True, "matrix": True, "connectors": True, "title_block": True},
            )
            self.assertEqual(approval["visual_approval"]["approved_by"], "reviewer")
            self.assertTrue(approval["visual_approval"]["approved"])
            self.assertTrue(output_path.is_file())

    def test_approval_output_preserves_complete_evidence_for_production(self):
        from tools.check_schematic_acceptance import assert_candidate_evidence, record_visual_approval

        with TemporaryDirectory() as directory:
            evidence_path = Path(directory) / "candidate.json"
            approved_path = Path(directory) / "approved.json"
            evidence = {
                "plan_hash": "plan", "git_sha": "head",
                "acceptance": {"inventory": {"mcu": 1}},
                "gates": {"wire_validation": True, "component_validation": True, "erc_errors": 0, "erc_warnings": 0},
                "svg_sha256": "svg", "render_sha256": "render",
            }
            evidence_path.write_text(json.dumps(evidence))
            approved = record_visual_approval(
                evidence_path, approved_path, "reviewer",
                {"u1": True, "matrix": True, "connectors": True, "title_block": True},
            )
            self.assertEqual(approved["acceptance"], evidence["acceptance"])
            self.assertEqual(approved["visual_approval"]["approved_by"], "reviewer")
            assert_candidate_evidence(approved, "plan", "head")

    def test_writer_detection_fails_closed_when_lsof_is_unavailable(self):
        from tools.check_schematic_acceptance import _writer_pids

        with self.assertRaisesRegex(RuntimeError, "writer detection unavailable"):
            _writer_pids(Path("/tmp/lh60.kicad_sch"), run_fn=lambda *args, **kwargs: (_ for _ in ()).throw(FileNotFoundError()))

    def test_frozen_acceptance_hashes_actual_exported_components_and_pins_without_plan_builder(self):
        from tools import check_schematic_acceptance as checker

        components = [{"reference": "U1", "lib_id": "lib", "value": "value", "footprint": "fp"}]
        netlist = {"components": [{**components[0], "pins": [{"number": "1", "net": "NET"}]}]}
        original_component_hash = checker.FROZEN_COMPONENT_SHA256
        original_pin_hash = checker.FROZEN_PIN_SHA256
        original_map = checker.FROZEN_CONNECTOR_MAP
        original_builder = checker.build_schematic_plan
        checker.FROZEN_COMPONENT_SHA256 = checker._stable_hash(checker.normalize_actual_components(components))
        checker.FROZEN_PIN_SHA256 = checker._stable_hash(checker.normalize_exported_pins(netlist))
        checker.FROZEN_CONNECTOR_MAP = {}
        checker.build_schematic_plan = lambda: (_ for _ in ()).throw(AssertionError("plan builder called"))
        try:
            with TemporaryDirectory() as directory:
                svg_path = Path(directory) / "candidate.svg"
                svg_path.write_text('<svg width="420mm" height="297mm"/>')
                data = {
                    "components": {"components": components}, "netlist": netlist, "svg_path": str(svg_path),
                    "overlaps": {"overlap_count": 0}, "single_pin_nets": {"single_pin_net_count": 0, "nets": []},
                }
                checker.assert_frozen_acceptance(data)
                data["netlist"]["components"][0]["pins"].append({"number": "2", "net": "NET"})
                with self.assertRaisesRegex(AssertionError, "pin contract"):
                    checker.assert_frozen_acceptance(data)
        finally:
            checker.FROZEN_COMPONENT_SHA256 = original_component_hash
            checker.FROZEN_PIN_SHA256 = original_pin_hash
            checker.FROZEN_CONNECTOR_MAP = original_map
            checker.build_schematic_plan = original_builder

    def test_candidate_prepares_libraries_once_then_second_candidate_only_registers_and_queries(self):
        from tools.check_schematic_acceptance import candidate

        calls = []
        class FakeClient:
            def call_tool(self, name, arguments):
                calls.append((name, arguments)); return tool_text_result({"ok": True})
            def tool_schemas(self, toolset):
                calls.append(("schemas", toolset)); return {}

        client = FakeClient()
        first = candidate(
            client, Path("/tmp/first"), regenerate_libraries=True,
            regenerate_fn=lambda factory, directory: calls.append(("regenerate", directory)),
            verify_fn=lambda factory, project: calls.append(("verify", project)),
            apply_fn=lambda client, schematic: calls.append(("apply", schematic)),
        )
        second = candidate(
            client, Path("/tmp/second"), regenerate_libraries=False,
            regenerate_fn=lambda factory, directory: calls.append(("regenerate", directory)),
            verify_fn=lambda factory, project: calls.append(("verify", project)),
            apply_fn=lambda client, schematic: calls.append(("apply", schematic)),
        )
        self.assertEqual([name for name, _ in calls].count("regenerate"), 1)
        self.assertEqual([name for name, _ in calls].count("verify"), 2)
        self.assertEqual([name for name, _ in calls].count("create_project"), 2)
        self.assertEqual(first.name, "lh60-candidate.kicad_sch")
        self.assertEqual(second.name, "lh60-candidate.kicad_sch")

    def test_real_preflight_and_converge_use_exact_payloads_and_refuse_nonempty_delete(self):
        from tools.check_schematic_acceptance import converge, preflight
        from tools.verify_schematic_apply import complete_schematic_schemas

        class FakeClient:
            def __init__(self, empty_after_delete=True):
                self.calls = []
                self.empty_after_delete = empty_after_delete

            def tool_schemas(self, toolset):
                schemas = deepcopy(disjoint_acceptance_schemas())
                for name, values in complete_schematic_schemas().items():
                    schemas.setdefault(name, {}).update(values)
                return schemas[toolset]

            def call_tool(self, name, arguments):
                self.calls.append((name, arguments))
                if name == "update_symbols_from_library":
                    if arguments.get("references") == ["U1"]:
                        return tool_text_result(
                            {
                                "errors": [],
                                "pins_moved": [],
                                "updated": ["lh60-mcu:RP2040-Tiny"],
                                "unchanged": [],
                            }
                        )
                    return tool_text_result(
                        {
                            "errors": [],
                            "pins_moved": [],
                            "updated": [],
                            "unchanged": ["lh60-mcu:RP2040-Tiny"],
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
                return tool_text_result({"ok": True})

            def call_tool_json(self, name, arguments):
                self.calls.append((name, arguments))
                if name == "get_schematic_layout":
                    if len([call for call in self.calls if call[0] == name]) > 1:
                        return {"component_count": 0 if self.empty_after_delete else 1, "wire_count": 0, "label_count": 0}
                    return {"component_count": 172, "wire_count": 290, "label_count": 339}
                if name == "list_schematic_wires":
                    return {"wires": [{"uuid": f"w{index}"} for index in range(290)]}
                if name == "list_schematic_labels":
                    return {"labels": [{"uuid": f"l{index}"} for index in range(339)]}
                if name == "list_schematic_components":
                    return {"components": [{"reference": reference} for reference in sorted(old_production_references())]}
                raise AssertionError(name)

        client = FakeClient()
        state = preflight(client, Path("/tmp/production.kicad_sch"))
        converge(client, Path("/tmp/production.kicad_sch"), state)
        deletes = [(name, arguments) for name, arguments in client.calls if name.startswith("batch_delete")]
        self.assertEqual([name for name, _ in deletes], ["batch_delete_schematic_wire", "batch_delete", "batch_delete_schematic_components"])
        self.assertEqual(deletes[0][1]["uuids"], [f"w{index}" for index in range(290)])
        self.assertEqual(deletes[1][1]["uuids"], [f"l{index}" for index in range(339)])
        self.assertEqual(set(deletes[2][1]["references"]), old_production_references())

        with self.assertRaisesRegex(AssertionError, "did not empty"):
            converge(FakeClient(empty_after_delete=False), Path("/tmp/production.kicad_sch"), state)

    def test_predelete_safety_records_pcb_hash_and_refuses_dirty_or_writer_state(self):
        from tools.check_schematic_acceptance import assert_predelete_safety

        with TemporaryDirectory() as directory:
            root = Path(directory)
            schematic = root / "lh60.kicad_sch"
            board = root / "lh60.kicad_pcb"
            schematic.write_text("schematic")
            board.write_text("board")
            result = assert_predelete_safety(
                schematic, board, clean_tree_fn=lambda: True, writer_pids_fn=lambda path: []
            )
            self.assertEqual(result["pcb_sha256"], hashlib.sha256(b"board").hexdigest())
            with self.assertRaisesRegex(AssertionError, "clean"):
                assert_predelete_safety(schematic, board, clean_tree_fn=lambda: False, writer_pids_fn=lambda path: [])
            with self.assertRaisesRegex(AssertionError, "writer"):
                assert_predelete_safety(schematic, board, clean_tree_fn=lambda: True, writer_pids_fn=lambda path: [123])

    def test_prepare_and_verify_candidate_libraries_use_separate_fresh_clients(self):
        from tools.check_schematic_acceptance import prepare_candidate_libraries, verify_candidate_libraries

        clients = []
        class FakeClient:
            def __init__(self, number):
                self.number = number
                self.calls = []
            def __enter__(self):
                return self
            def __exit__(self, *unused):
                return None
            def tool_schemas(self, toolset):
                return deepcopy(disjoint_acceptance_schemas()[toolset])
            def call_tool_json(self, name, arguments):
                self.calls.append((name, arguments))
                if name == "get_symbol_info":
                    return {"name": arguments["lib_id"].split(":")[1]}
                if name == "get_footprint_info":
                    return {"name": Path(arguments["footprint_path"]).stem}
                raise AssertionError(name)

        def factory(*unused):
            client = FakeClient(len(clients))
            clients.append(client)
            return client

        applied = []
        prepare_candidate_libraries(
            factory, Path("/tmp/project"),
            apply_core_fn=lambda client: applied.append(("core", client.number)),
            apply_mcu_fn=lambda client: applied.append(("mcu", client.number)),
            capability_fn=lambda client: None,
        )
        self.assertEqual(applied, [("core", 0), ("mcu", 1)])
        result = verify_candidate_libraries(
            factory, Path("/tmp/project/lh60-candidate.kicad_pro"), capability_fn=lambda client: None,
        )
        self.assertEqual(len(clients), 3)
        for name, arguments in clients[2].calls:
            if name == "get_symbol_info":
                self.assertEqual(arguments["project_dir"], "/tmp/project")
            if name == "get_footprint_info":
                self.assertEqual(arguments["project"], "/tmp/project/lh60-candidate.kicad_pro")
        self.assertEqual(set(result["symbols"]), {"Conn_01x03", "Conn_01x04", "Conn_01x05", "RP2040-Tiny"})
        self.assertEqual(set(result["footprints"]), {"PinHeader_1x03_P2.54mm_Vertical", "PinHeader_1x04_P2.54mm_Vertical", "PinHeader_1x05_P2.54mm_Vertical", "MCU_RP2040-Tiny_SMD"})

    def test_transaction_runs_real_preflight_and_converge_only_after_safety(self):
        from tools.check_schematic_acceptance import run_production_transaction
        from tools.verify_schematic_apply import complete_schematic_schemas

        with TemporaryDirectory() as directory:
            evidence_path = Path(directory) / "candidate.json"
            evidence_path.write_text(json.dumps({
                "plan_hash": "plan", "git_sha": "head", "acceptance": {"ok": True},
                "gates": {"wire_validation": True, "component_validation": True, "erc_errors": 0, "erc_warnings": 0},
                "svg_sha256": "svg", "render_sha256": "render",
                "visual_approval": {"approved": True, "plan_hash": "plan", "git_sha": "head", "svg_sha256": "svg", "render_sha256": "render"},
            }))
            calls = []
            class FakeClient:
                def tool_schemas(self, toolset):
                    schemas = deepcopy(disjoint_acceptance_schemas())
                    for name, values in complete_schematic_schemas().items():
                        schemas.setdefault(name, {}).update(values)
                    return schemas[toolset]
                def call_tool(self, name, arguments):
                    calls.append((name, arguments))
                    if name == "update_symbols_from_library":
                        if arguments.get("references") == ["U1"]:
                            return tool_text_result(
                                {
                                    "errors": [],
                                    "pins_moved": [],
                                    "updated": ["lh60-mcu:RP2040-Tiny"],
                                    "unchanged": [],
                                }
                            )
                        return tool_text_result(
                            {
                                "errors": [],
                                "pins_moved": [],
                                "updated": [],
                                "unchanged": ["lh60-mcu:RP2040-Tiny"],
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
                    return tool_text_result({"ok": True})
                def call_tool_json(self, name, arguments):
                    calls.append((name, arguments))
                    if name == "get_schematic_layout":
                        deleted = any(call[0] == "batch_delete_schematic_components" for call in calls)
                        return {"component_count": 0 if deleted else 172, "wire_count": 0 if deleted else 290, "label_count": 0 if deleted else 339}
                    if name == "list_schematic_wires": return {"wires": [{"uuid": f"w{n}"} for n in range(290)]}
                    if name == "list_schematic_labels": return {"labels": [{"uuid": f"l{n}"} for n in range(339)]}
                    if name == "list_schematic_components": return {"components": [{"reference": ref} for ref in old_production_references()]}
                    raise AssertionError(name)

            result = run_production_transaction(
                FakeClient(), Path("/tmp/production.kicad_sch"), evidence_path, Path(directory) / "out.json",
                expected_plan_hash="plan", expected_git_sha="head",
                capabilities_fn=lambda client: calls.append(("capabilities", {})),
                safety_fn=lambda schematic, board: calls.append(("safety", {})) or {"pcb_sha256": "pcb"},
                acceptance_fn=lambda *unused: {"semantic": {"NET": [("U1", "1")]}, "svg_sha256": "production"},
                candidate_fn=lambda *unused, **kwargs: Path(directory) / "candidate.kicad_sch",
                candidate_acceptance_fn=lambda *unused: {"semantic": {"NET": [("U1", "1")]}, "svg_sha256": "candidate"},
            )
            write_names = [name for name, _ in calls if name.startswith("batch_delete")]
            self.assertEqual(calls[0][0], "capabilities")
            self.assertEqual(calls[1][0], "safety")
            self.assertEqual(write_names, ["batch_delete_schematic_wire", "batch_delete", "batch_delete_schematic_components"])
            self.assertEqual(result["predelete_safety"]["pcb_sha256"], "pcb")


if __name__ == "__main__":
    unittest.main()
