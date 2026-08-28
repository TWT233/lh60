import json
import unittest
from dataclasses import replace
from pathlib import Path


REPORT_PATH = (
    Path(__file__).resolve().parents[1] / "docs" / "regions" / "enter.json"
)
APPROVED_KEY_IDS = (
    "r2_enter_ansi_2.25u",
    "r2_enter_split_left_fn_1u",
    "r2_enter_split_right_1.25u",
)
SINGLE_G_PREFIX = "Gateron-LP-Hotswap-Socket-"
DUAL_PREFIX = "Gateron-LP-or-ChocV1-Hotswap-Socket-"


def _load_report(test_case: unittest.TestCase) -> dict[str, object]:
    test_case.assertTrue(
        REPORT_PATH.is_file(),
        f"missing Enter region report: {REPORT_PATH}",
    )
    return json.loads(REPORT_PATH.read_text())


def _approved_layout_keys():
    from tools.lh60_design.layout import physical_keys

    keys_by_id = {key.physical_key_id: key for key in physical_keys()}
    return tuple(keys_by_id[key_id] for key_id in APPROVED_KEY_IDS)


def _single_g_region():
    from tools.lh60_design.layout import REGION_ROTATIONS_DEG
    from tools.lh60_design.regions import RegionPlacement, RegionSpec

    return RegionSpec(
        region="enter",
        placements=tuple(
            RegionPlacement(
                socket_ref=key.physical_key_id,
                footprint=f"{SINGLE_G_PREFIX}{key.footprint_size}",
                center_x_mm=key.center_x_mm,
                center_y_mm=key.center_y_mm,
                logical_node_id=key.logical_node_id,
                allowed_rotations_deg=REGION_ROTATIONS_DEG["enter"],
            )
            for key in _approved_layout_keys()
        ),
    )


def _clearance_payload(placements) -> dict[str, object]:
    from tools.lh60_design.regions import measure_clearances

    clearance = measure_clearances(placements)
    return {
        "minimum_copper_clearance_mm": (
            clearance.minimum_copper_clearance_mm
        ),
        "closest_copper_pair": list(clearance.closest_copper_pair),
        "minimum_hole_edge_clearance_mm": (
            clearance.minimum_hole_edge_clearance_mm
        ),
        "closest_hole_pair": list(clearance.closest_hole_pair),
        "minimum_courtyard_clearance_mm": (
            clearance.minimum_courtyard_clearance_mm
        ),
        "closest_courtyard_pair": list(
            clearance.closest_courtyard_pair
        ),
    }


def _attempt_payload(report, socket_ref: str) -> dict[str, object]:
    return {
        "socket_ref": socket_ref,
        "candidate_footprint": next(
            placement.footprint
            for placement in report.placements
            if placement.socket_ref == socket_ref
        ),
        "retained": report.solved,
        "solved": report.solved,
        "placements": [
            placement.to_dict() for placement in report.placements
        ],
        "clearances": _clearance_payload(report.placements),
        "hole_edge_target_met": report.hole_edge_target_met,
        "blocking_conflicts": [
            conflict.to_dict() for conflict in report.blocking_conflicts
        ],
    }


class EnterRegionReportTest(unittest.TestCase):
    def test_report_declares_the_frozen_enter_contract(self):
        from tools.lh60_design.layout import REGION_ROTATIONS_DEG
        from tools.lh60_design.regions import (
            MIN_COPPER_CLEARANCE_MM,
            MIN_COURTYARD_CLEARANCE_MM,
            MIN_HOLE_EDGE_CLEARANCE_MM,
            TARGET_HOLE_EDGE_CLEARANCE_MM,
        )
        from tools.lh60_design.socket_geometry import build_footprint_specs

        report = _load_report(self)
        expected_keys = [
            {
                "physical_key_id": key.physical_key_id,
                "logical_node_id": key.logical_node_id,
                "center_x_mm": key.center_x_mm,
                "center_y_mm": key.center_y_mm,
                "width_u": key.width_u,
                "single_g_footprint": (
                    f"{SINGLE_G_PREFIX}{key.footprint_size}"
                ),
                "approved_rotations_deg": list(
                    REGION_ROTATIONS_DEG["enter"]
                ),
            }
            for key in _approved_layout_keys()
        ]
        courtyard_buffers = {
            spec.courtyard_clearance_mm
            for spec in build_footprint_specs()
        }

        self.assertEqual(
            set(report),
            {
                "schema_version",
                "region",
                "status",
                "solved",
                "approved_keys",
                "solver",
                "requirements_mm",
                "single_g_search",
                "placements",
                "clearances",
                "hole_edge_target_met",
                "geometry_status",
                "blocking_conflicts",
                "dual_upgrade_attempts",
                "retained_dual_upgrades",
                "drc_evidence",
                "sources",
                "notes",
            },
        )
        self.assertEqual(report["schema_version"], 1)
        self.assertEqual(report["region"], "enter")
        self.assertEqual(report["status"], "solved")
        self.assertTrue(report["solved"])
        self.assertEqual(report["approved_keys"], expected_keys)
        self.assertEqual(
            report["solver"],
            {
                "implementation": (
                    "tools.lh60_design.regions.solve_region"
                ),
                "search_order": "approved-key-order-product",
                "allowed_rotations_deg": [0, 90, 180, 270],
                "single_g_first": True,
                "dual_upgrade_policy": (
                    "one-placement-at-a-time-retain-only-hard-check-pass"
                ),
            },
        )
        self.assertEqual(courtyard_buffers, {0.5})
        self.assertEqual(
            report["requirements_mm"],
            {
                "minimum_copper_clearance": (
                    MIN_COPPER_CLEARANCE_MM
                ),
                "minimum_independent_hole_edge_clearance": (
                    MIN_HOLE_EDGE_CLEARANCE_MM
                ),
                "target_hole_edge_clearance": (
                    TARGET_HOLE_EDGE_CLEARANCE_MM
                ),
                "minimum_courtyard_clearance": (
                    MIN_COURTYARD_CLEARANCE_MM
                ),
                "courtyard_buffer_per_footprint": 0.5,
            },
        )

    def test_selected_single_g_solution_recomputes_exactly(self):
        from tools.lh60_design.regions import solve_region

        report = _load_report(self)
        solved = solve_region(_single_g_region())
        expected_rotations = {
            placement.socket_ref: placement.rotation_deg
            for placement in solved.placements
        }

        self.assertTrue(solved.solved)
        self.assertEqual(solved.drc_status, "geometry-pass")
        self.assertEqual(
            report["single_g_search"],
            {
                "rotation_combinations_evaluated": 64,
                "solved": True,
                "selected_rotations_deg": expected_rotations,
            },
        )
        self.assertEqual(
            report["placements"],
            [placement.to_dict() for placement in solved.placements],
        )
        self.assertEqual(
            report["clearances"],
            _clearance_payload(solved.placements),
        )
        self.assertEqual(
            report["hole_edge_target_met"],
            solved.hole_edge_target_met,
        )
        self.assertEqual(report["geometry_status"], solved.drc_status)
        self.assertEqual(
            report["blocking_conflicts"],
            [
                conflict.to_dict()
                for conflict in solved.blocking_conflicts
            ],
        )

    def test_dual_upgrades_are_attempted_one_at_a_time(self):
        from tools.lh60_design.regions import RegionSpec, solve_region

        report = _load_report(self)
        current = solve_region(_single_g_region()).placements
        expected_attempts = []
        retained = []

        for index, placement in enumerate(tuple(current)):
            candidate = tuple(
                replace(
                    item,
                    footprint=item.footprint.replace(
                        SINGLE_G_PREFIX,
                        DUAL_PREFIX,
                    ),
                )
                if offset == index
                else item
                for offset, item in enumerate(current)
            )
            attempt = solve_region(
                RegionSpec(region="enter", placements=candidate)
            )
            expected_attempts.append(
                _attempt_payload(attempt, placement.socket_ref)
            )
            if attempt.solved:
                current = attempt.placements
                retained.append(placement.socket_ref)

        self.assertEqual(
            report["dual_upgrade_attempts"],
            expected_attempts,
        )
        self.assertEqual(report["retained_dual_upgrades"], retained)
        self.assertEqual(
            report["placements"],
            [placement.to_dict() for placement in current],
        )
        for attempt in report["dual_upgrade_attempts"]:
            if attempt["solved"]:
                continue
            self.assertFalse(attempt["retained"])
            self.assertGreater(len(attempt["blocking_conflicts"]), 0)
            for conflict in attempt["blocking_conflicts"]:
                self.assertLess(
                    conflict["actual_mm"],
                    conflict["required_mm"],
                )
                self.assertAlmostEqual(
                    conflict["shortfall_mm"],
                    conflict["required_mm"]
                    - conflict["actual_mm"],
                )

    def test_coupon_drc_evidence_matches_the_selected_solution(self):
        report = _load_report(self)
        evidence = report["drc_evidence"]
        expected_references = [
            {
                "reference": f"SW{index}",
                "socket_ref": placement["socket_ref"],
                "footprint_id": (
                    f"lh60-sockets:{placement['footprint']}"
                ),
                "center_x_mm": placement["center_x_mm"],
                "center_y_mm": placement["center_y_mm"],
                "rotation_deg": placement["rotation_deg"],
            }
            for index, placement in enumerate(
                report["placements"],
                start=1,
            )
        ]

        self.assertEqual(
            evidence["tool"],
            "Konnect MCP verification.run_drc",
        )
        self.assertEqual(
            evidence["coupon_project"],
            "/tmp/lh60-region-enter/lh60.kicad_pro",
        )
        self.assertEqual(
            evidence["coupon_board"],
            "/tmp/lh60-region-enter/lh60.kicad_pcb",
        )
        self.assertEqual(
            evidence["library"],
            {
                "nickname": "lh60-sockets",
                "repo_relative_path": "lib/lh60-sockets",
                "scope": "project",
            },
        )
        self.assertEqual(
            evidence["placed_footprints"],
            expected_references,
        )
        self.assertEqual(
            evidence["design_rules"],
            {
                "min_clearance_mm": 0.25,
                "min_hole_to_hole_mm": 0.45,
                "min_trace_width_mm": 0.25,
                "min_via_drill_mm": 0.3,
                "min_via_size_mm": 0.7,
            },
        )
        self.assertEqual(
            evidence["board_extents_mm"],
            {
                "x_min": 0.0,
                "y_min": 0.0,
                "x_max": 285.75,
                "y_max": 95.25,
                "width": 285.75,
                "height": 95.25,
            },
        )
        self.assertEqual(
            evidence["placement_method"],
            (
                "Konnect MCP pcb_components.place_component "
                "closed-board fallback"
            ),
        )
        self.assertEqual(
            evidence["placement_call_status"],
            ["SW1:ok", "SW2:ok", "SW3:ok"],
        )
        self.assertEqual(evidence["status"], "pass")
        self.assertEqual(
            evidence["summary"],
            {
                "error_count": 0,
                "warning_count": 0,
                "violation_count": 0,
            },
        )
        self.assertEqual(evidence["violations"], [])
        self.assertFalse(evidence["production_board_modified"])
        self.assertFalse(evidence["coupon_artifacts_committed"])


if __name__ == "__main__":
    unittest.main()
