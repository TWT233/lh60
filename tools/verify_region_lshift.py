from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
import unittest

from tools.lh60_design.layout import physical_keys
from tools.lh60_design.regions import RegionPlacement, RegionSpec, solve_region


REPORT_PATH = Path(__file__).resolve().parents[1] / "docs" / "regions" / "lshift.json"
APPROVED_KEY_IDS = (
    "r3_lshift_split_left_fn_1u",
    "r3_lshift_2.25u",
    "r3_lshift_split_1.25u",
)
EXPECTED_LAYOUT = (
    (
        "r3_lshift_split_left_fn_1u",
        9.525,
        66.675,
        "1U",
        "r3_lshift_split_left_fn_1u",
    ),
    (
        "r3_lshift_2.25u",
        21.431250000000002,
        66.675,
        "2.25U",
        "r3_lshift_2.25u",
    ),
    (
        "r3_lshift_split_1.25u",
        30.95625,
        66.675,
        "1.25U",
        "r3_lshift_2.25u",
    ),
)


def _approved_layout():
    keys_by_id = {key.physical_key_id: key for key in physical_keys()}
    return tuple(keys_by_id[key_id] for key_id in APPROVED_KEY_IDS)


def _single_g_region() -> RegionSpec:
    return RegionSpec(
        region="lshift",
        placements=tuple(
            RegionPlacement(
                socket_ref=key.physical_key_id,
                footprint=(
                    f"Gateron-LP-Hotswap-Socket-{key.footprint_size}"
                ),
                center_x_mm=key.center_x_mm,
                center_y_mm=key.center_y_mm,
                logical_node_id=key.logical_node_id,
            )
            for key in _approved_layout()
        ),
    )


def _dual_footprint(footprint: str) -> str:
    return footprint.replace(
        "Gateron-LP-Hotswap",
        "Gateron-LP-or-ChocV1-Hotswap",
    )


def recompute_lshift_report():
    retained = solve_region(_single_g_region())
    attempts = []
    for socket_ref in APPROVED_KEY_IDS:
        candidate = tuple(
            replace(
                placement,
                footprint=_dual_footprint(placement.footprint),
            )
            if placement.socket_ref == socket_ref
            else placement
            for placement in retained.placements
        )
        attempt = solve_region(
            RegionSpec(region="lshift", placements=candidate)
        )
        attempts.append(attempt)
        if attempt.solved:
            retained = attempt
    return retained, tuple(attempts)


class LShiftRegionContractTest(unittest.TestCase):
    def test_approved_keys_have_exact_centers_sizes_and_logical_nodes(self):
        actual = tuple(
            (
                key.physical_key_id,
                key.center_x_mm,
                key.center_y_mm,
                key.footprint_size,
                key.logical_node_id,
            )
            for key in _approved_layout()
        )

        self.assertEqual(actual, EXPECTED_LAYOUT)

    def test_single_g_solution_passes_and_no_dual_upgrade_is_retained(self):
        report, attempts = recompute_lshift_report()

        self.assertTrue(report.solved)
        self.assertEqual(report.drc_status, "geometry-pass")
        self.assertEqual(
            tuple(
                (placement.socket_ref, placement.rotation_deg)
                for placement in report.placements
            ),
            (
                ("r3_lshift_split_left_fn_1u", 270),
                ("r3_lshift_2.25u", 0),
                ("r3_lshift_split_1.25u", 180),
            ),
        )
        self.assertTrue(
            all(
                placement.footprint.startswith(
                    "Gateron-LP-Hotswap-Socket-"
                )
                for placement in report.placements
            )
        )
        self.assertEqual(len(attempts), len(APPROVED_KEY_IDS))
        self.assertTrue(all(not attempt.solved for attempt in attempts))
        self.assertTrue(
            all(attempt.blocking_conflicts for attempt in attempts)
        )

    def test_report_matches_recomputed_solver_result(self):
        report, _ = recompute_lshift_report()

        with REPORT_PATH.open(encoding="utf-8") as report_file:
            payload = json.load(report_file)

        self.assertEqual(payload, report.to_dict())
        self.assertGreaterEqual(payload["minimum_copper_clearance_mm"], 0.25)
        self.assertGreaterEqual(
            payload["minimum_hole_edge_clearance_mm"],
            0.45,
        )
        self.assertGreaterEqual(
            payload["minimum_courtyard_clearance_mm"],
            0.0,
        )
        self.assertTrue(payload["hole_edge_target_met"])
        self.assertEqual(payload["blocking_conflicts"], [])


if __name__ == "__main__":
    unittest.main()
