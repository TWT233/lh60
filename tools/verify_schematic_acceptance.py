import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


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
                return {}

            def call_tool_json(self, name, arguments):
                self.calls.append((name, arguments))
                return {}

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

            def new_candidate(client, directory):
                calls.append(("second-candidate", str(directory)))
                return Path(directory) / "candidate.kicad_sch"

            def candidate_acceptance(client, schematic, output):
                calls.append(("candidate-acceptance", str(schematic)))
                return {"semantic": {"NET": [("U1", "1")]}, "svg_sha256": "candidate-svg"}

            result = run_production_transaction(
                FakeClient(), Path("/tmp/lh60.kicad_sch"), evidence_path, output_path,
                expected_plan_hash="plan", expected_git_sha="head", expected_references=expected_refs,
                preflight_fn=preflight, converge_fn=converge, acceptance_fn=acceptance, candidate_fn=new_candidate, candidate_acceptance_fn=candidate_acceptance, capabilities_fn=lambda client: None,
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


if __name__ == "__main__":
    unittest.main()
