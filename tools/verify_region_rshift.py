from dataclasses import replace
from itertools import combinations, product
import json
from pathlib import Path
import unittest


class RShiftRegionReportTest(unittest.TestCase):
    ROOT = Path(__file__).resolve().parents[1]
    REPORT_PATH = ROOT / "docs" / "regions" / "rshift.json"

    @classmethod
    def setUpClass(cls):
        cls.payload = json.loads(cls.REPORT_PATH.read_text())

    def rshift_keys(self):
        from tools.lh60_design.layout import physical_keys

        return tuple(key for key in physical_keys() if key.region == "rshift")

    def single_g_region(self):
        from tools.lh60_design.layout import REGION_ROTATIONS_DEG
        from tools.lh60_design.regions import RegionPlacement, RegionSpec

        placements = tuple(
            RegionPlacement(
                socket_ref=key.physical_key_id,
                footprint=(
                    f"Gateron-LP-Hotswap-Socket-{key.footprint_size}"
                ),
                center_x_mm=key.center_x_mm,
                center_y_mm=key.center_y_mm,
                logical_node_id=key.logical_node_id,
                allowed_rotations_deg=REGION_ROTATIONS_DEG["rshift"],
            )
            for key in self.rshift_keys()
        )
        return RegionSpec(region="rshift", placements=placements)

    def test_report_has_the_complete_blocked_region_schema(self):
        self.assertEqual(
            set(self.payload),
            {
                "schema_version",
                "region",
                "status",
                "solved",
                "search_contract",
                "hard_limits_mm",
                "placements",
                "minimum_copper_clearance_mm",
                "minimum_hole_edge_clearance_mm",
                "minimum_courtyard_clearance_mm",
                "hole_edge_target_met",
                "drc_status",
                "blocking_conflicts",
                "single_g_search",
                "dual_upgrade_attempts",
                "retained_dual_upgrades",
                "smallest_alternatives",
                "coupon_evidence",
                "production_pcb_modified",
                "decision_required",
            },
        )
        self.assertEqual(self.payload["schema_version"], 1)
        self.assertEqual(self.payload["region"], "rshift")
        self.assertEqual(self.payload["status"], "blocked")
        self.assertFalse(self.payload["solved"])
        self.assertFalse(self.payload["production_pcb_modified"])
        self.assertTrue(self.payload["decision_required"])

    def test_report_recomputes_all_five_approved_single_g_sockets(self):
        from tools.lh60_design.regions import solve_region

        expected = solve_region(self.single_g_region())

        self.assertEqual(
            self.payload["placements"],
            expected.to_dict()["placements"],
        )
        self.assertEqual(
            self.payload["blocking_conflicts"],
            expected.to_dict()["blocking_conflicts"],
        )
        self.assertEqual(
            self.payload["minimum_copper_clearance_mm"],
            expected.minimum_copper_clearance_mm,
        )
        self.assertEqual(
            self.payload["minimum_hole_edge_clearance_mm"],
            expected.minimum_hole_edge_clearance_mm,
        )
        self.assertEqual(
            self.payload["minimum_courtyard_clearance_mm"],
            expected.minimum_courtyard_clearance_mm,
        )
        self.assertEqual(
            self.payload["hole_edge_target_met"],
            expected.hole_edge_target_met,
        )
        self.assertEqual(self.payload["drc_status"], expected.drc_status)
        self.assertEqual(
            [placement["socket_ref"] for placement in self.payload["placements"]],
            [key.physical_key_id for key in self.rshift_keys()],
        )
        self.assertEqual(
            [placement["center_x_mm"] for placement in self.payload["placements"]],
            [key.center_x_mm for key in self.rshift_keys()],
        )
        self.assertEqual(
            [placement["center_y_mm"] for placement in self.payload["placements"]],
            [key.center_y_mm for key in self.rshift_keys()],
        )
        self.assertEqual(
            [
                placement["logical_node_id"]
                for placement in self.payload["placements"]
            ],
            [key.logical_node_id for key in self.rshift_keys()],
        )

    def test_single_g_search_is_exhaustive_and_reproducible(self):
        from tools.lh60_design.regions import (
            MIN_COPPER_CLEARANCE_MM,
            MIN_COURTYARD_CLEARANCE_MM,
            MIN_HOLE_EDGE_CLEARANCE_MM,
            measure_clearances,
            solve_region,
        )

        region = self.single_g_region()
        solved_candidate_count = 0
        for rotations in product(
            region.placements[0].allowed_rotations_deg,
            repeat=len(region.placements),
        ):
            placements = tuple(
                replace(placement, rotation_deg=rotation)
                for placement, rotation in zip(
                    region.placements,
                    rotations,
                    strict=True,
                )
            )
            clearance = measure_clearances(placements)
            solved_candidate_count += (
                clearance.minimum_copper_clearance_mm
                >= MIN_COPPER_CLEARANCE_MM
                and clearance.minimum_hole_edge_clearance_mm
                >= MIN_HOLE_EDGE_CLEARANCE_MM
                and clearance.minimum_courtyard_clearance_mm
                >= MIN_COURTYARD_CLEARANCE_MM
            )

        expected = solve_region(region).to_dict()
        search = self.payload["single_g_search"]
        self.assertEqual(search["candidate_count"], 4**5)
        self.assertEqual(search["solved_candidate_count"], solved_candidate_count)
        self.assertEqual(solved_candidate_count, 0)
        self.assertEqual(search["selected_report"], expected)
        self.assertFalse(
            self.payload["search_contract"]["old_test_board_assumptions_reused"]
        )

    def test_dual_upgrades_are_attempted_in_layout_order_and_recomputed(self):
        from tools.lh60_design.regions import RegionSpec, solve_region

        current = solve_region(self.single_g_region())
        expected_attempts = []
        for order, placement in enumerate(current.placements, start=1):
            candidate_footprint = placement.footprint.replace(
                "Gateron-LP-",
                "Gateron-LP-or-ChocV1-",
            )
            candidate = tuple(
                replace(item, footprint=candidate_footprint)
                if item.socket_ref == placement.socket_ref
                else item
                for item in current.placements
            )
            report = solve_region(RegionSpec(region="rshift", placements=candidate))
            expected_attempts.append(
                {
                    "order": order,
                    "socket_ref": placement.socket_ref,
                    "from_footprint": placement.footprint,
                    "candidate_footprint": candidate_footprint,
                    "accepted": report.solved,
                    "report": report.to_dict(),
                }
            )
            if report.solved:
                current = report

        self.assertEqual(
            self.payload["dual_upgrade_attempts"],
            expected_attempts,
        )
        self.assertEqual(self.payload["retained_dual_upgrades"], [])

    def test_every_blocker_preserves_actual_required_and_shortfall(self):
        conflict_groups = [self.payload["blocking_conflicts"]]
        conflict_groups.extend(
            attempt["report"]["blocking_conflicts"]
            for attempt in self.payload["dual_upgrade_attempts"]
        )

        for conflicts in conflict_groups:
            self.assertGreater(len(conflicts), 0)
            for conflict in conflicts:
                with self.subTest(
                    domain=conflict["domain"],
                    items=conflict["items"],
                ):
                    self.assertEqual(
                        set(conflict),
                        {
                            "domain",
                            "items",
                            "actual_mm",
                            "required_mm",
                            "shortfall_mm",
                        },
                    )
                    self.assertLess(
                        conflict["actual_mm"],
                        conflict["required_mm"],
                    )
                    self.assertAlmostEqual(
                        conflict["shortfall_mm"],
                        conflict["required_mm"] - conflict["actual_mm"],
                    )

    def test_smallest_center_preserving_alternatives_are_recomputed(self):
        from tools.lh60_design.regions import RegionSpec, solve_region

        region = self.single_g_region()
        expected_solutions = []
        minimum_removed_count = None
        for removed_count in range(1, len(region.placements)):
            for removed_indexes in combinations(
                range(len(region.placements)),
                removed_count,
            ):
                kept = tuple(
                    placement
                    for index, placement in enumerate(region.placements)
                    if index not in removed_indexes
                )
                report = solve_region(
                    RegionSpec(region="rshift", placements=kept)
                )
                if report.solved:
                    expected_solutions.append(
                        {
                            "removed_socket_refs": [
                                region.placements[index].socket_ref
                                for index in removed_indexes
                            ],
                            "report": report.to_dict(),
                        }
                    )
            if expected_solutions:
                minimum_removed_count = removed_count
                break

        alternatives = self.payload["smallest_alternatives"]
        self.assertEqual(
            alternatives["search_kind"],
            "center-preserving-socket-exclusion",
        )
        self.assertEqual(
            alternatives["minimum_removed_socket_count"],
            minimum_removed_count,
        )
        self.assertEqual(
            alternatives["solutions"],
            expected_solutions,
        )
        self.assertEqual(minimum_removed_count, 1)
        self.assertEqual(
            [
                solution["removed_socket_refs"]
                for solution in expected_solutions
            ],
            [["r3_rshift_2.75u"]],
        )
        self.assertTrue(alternatives["requires_user_approval"])

    def test_coupon_evidence_covers_the_selected_assignment_and_drc(self):
        coupon = self.payload["coupon_evidence"]
        self.assertTrue(coupon["temporary"])
        self.assertFalse(coupon["committed"])
        self.assertEqual(coupon["created_via"], "Konnect MCP")
        self.assertEqual(
            coupon["project_directory"],
            "/tmp/lh60-region-rshift",
        )
        self.assertEqual(
            coupon["library"]["nickname"],
            "lh60-sockets",
        )
        self.assertTrue(coupon["library"]["registered"])
        self.assertEqual(
            coupon["library"]["path"],
            "lib/lh60-sockets",
        )
        self.assertEqual(
            coupon["rules_mm"],
            {
                "minimum_copper_clearance": 0.25,
                "minimum_trace_width": 0.25,
                "minimum_hole_to_hole": 0.45,
                "minimum_via_drill": 0.3,
                "minimum_via_size": 0.7,
            },
        )

        expected_placements = [
            {
                "reference": f"SW_RSHIFT_{index}",
                "socket_ref": placement["socket_ref"],
                "footprint": f"lh60-sockets:{placement['footprint']}",
                "x_mm": placement["center_x_mm"],
                "y_mm": placement["center_y_mm"],
                "rotation_deg": placement["rotation_deg"],
            }
            for index, placement in enumerate(
                self.payload["placements"],
                start=1,
            )
        ]
        self.assertEqual(coupon["placements"], expected_placements)

        drc = coupon["drc"]
        self.assertTrue(drc["executed"])
        self.assertEqual(drc["tool"], "run_drc")
        self.assertEqual(drc["status"], "blocked")
        self.assertEqual(drc["error_count"], 3)
        self.assertEqual(drc["warning_count"], 4)
        self.assertEqual(drc["violation_count"], 7)
        self.assertEqual(drc["violation_count"], len(drc["violations"]))
        self.assertEqual(
            [
                violation["description"]
                for violation in drc["violations"]
                if violation["severity"] == "error"
            ],
            [
                "Courtyards overlap",
                "Courtyards overlap",
                "NPTH inside courtyard",
            ],
        )


if __name__ == "__main__":
    unittest.main()
