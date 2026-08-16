from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import unittest

from tools.lh60_design.layout import physical_keys
from tools.lh60_design.regions import RegionPlacement, RegionSpec, solve_region


REPORT_PATH = Path("docs/regions/top-right.json")
REGION = "top-right"
PHYSICAL_KEY_IDS = (
    "r0_top_2u",
    "r0_top_split_left_fn_1u",
    "r0_top_split_right_1u",
)
DUAL_PREFIX = "Gateron-LP-or-ChocV1-"
REPORT_FIELDS = {
    "region",
    "solved",
    "placements",
    "minimum_copper_clearance_mm",
    "minimum_hole_edge_clearance_mm",
    "minimum_courtyard_clearance_mm",
    "hole_edge_target_met",
    "drc_status",
    "blocking_conflicts",
    "coupon_drc",
    "source_series",
    "upgrade_attempts",
    "minimum_change_alternatives",
}
PLACEMENT_FIELDS = {
    "socket_ref",
    "footprint",
    "center_x_mm",
    "center_y_mm",
    "rotation_deg",
    "logical_node_id",
}
COUPON_DRC_FIELDS = {
    "project",
    "tool",
    "status",
    "violations",
    "errors",
    "warnings",
    "unconnected_items",
    "source_series",
    "library_nickname",
    "library_path",
    "findings",
}
ALTERNATIVE_FIELDS = {
    "type",
    "socket_ref",
    "axis",
    "offset_mm",
    "requires_layout_approval",
    "change",
    "effect",
    "minimum_clearances_mm",
}


def top_right_keys():
    keys_by_id = {
        key.physical_key_id: key
        for key in physical_keys()
        if key.region == REGION
    }
    return tuple(keys_by_id[key_id] for key_id in PHYSICAL_KEY_IDS)


def single_g_spec() -> RegionSpec:
    return RegionSpec(
        region=REGION,
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
            for key in top_right_keys()
        ),
    )


def dual_attempts(single_g_report):
    attempts = []
    for selected in single_g_report.placements:
        candidate = solve_region(
            RegionSpec(
                region=REGION,
                placements=tuple(
                    replace(
                        placement,
                        footprint=placement.footprint.replace(
                            "Gateron-LP-Hotswap",
                            "Gateron-LP-or-ChocV1-Hotswap",
                        ),
                    )
                    if placement.socket_ref == selected.socket_ref
                    else placement
                    for placement in single_g_report.placements
                ),
            )
        )
        attempts.append(
            {
                "socket_ref": selected.socket_ref,
                "retained": candidate.solved,
                "result": candidate.to_dict(),
            }
        )
    return attempts


class TopRightRegionReportTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.payload = json.loads(REPORT_PATH.read_text())
        cls.single_g_report = solve_region(single_g_spec())

    def test_report_contract_and_layout_source(self):
        self.assertEqual(set(self.payload), REPORT_FIELDS)
        self.assertEqual(self.payload["region"], REGION)
        self.assertEqual(
            tuple(
                placement["socket_ref"]
                for placement in self.payload["placements"]
            ),
            PHYSICAL_KEY_IDS,
        )
        for key, placement in zip(
            top_right_keys(),
            self.payload["placements"],
            strict=True,
        ):
            self.assertEqual(set(placement), PLACEMENT_FIELDS)
            self.assertEqual(placement["socket_ref"], key.physical_key_id)
            self.assertEqual(placement["center_x_mm"], key.center_x_mm)
            self.assertEqual(placement["center_y_mm"], key.center_y_mm)
            self.assertEqual(
                placement["logical_node_id"],
                key.logical_node_id,
            )

    def test_blocked_single_g_result_is_recomputed_exactly(self):
        expected = self.single_g_report.to_dict()
        for field in expected:
            self.assertEqual(self.payload[field], expected[field])
        self.assertFalse(self.payload["solved"])
        self.assertEqual(self.payload["drc_status"], "blocked")
        self.assertGreaterEqual(
            self.payload["minimum_copper_clearance_mm"],
            0.25,
        )
        self.assertGreaterEqual(
            self.payload["minimum_hole_edge_clearance_mm"],
            0.45,
        )
        self.assertLess(
            self.payload["minimum_courtyard_clearance_mm"],
            0.0,
        )
        self.assertTrue(self.payload["hole_edge_target_met"])
        self.assertGreater(len(self.payload["blocking_conflicts"]), 0)

    def test_dual_upgrades_are_attempted_and_none_are_retained(self):
        expected_attempts = dual_attempts(self.single_g_report)
        self.assertEqual(self.payload["upgrade_attempts"], expected_attempts)
        self.assertTrue(
            all(
                not attempt["retained"]
                for attempt in self.payload["upgrade_attempts"]
            )
        )
        self.assertTrue(
            all(
                not placement["footprint"].startswith(DUAL_PREFIX)
                for placement in self.payload["placements"]
            )
        )
        self.assertNotIn("Choc V2", json.dumps(self.payload))

    def test_coupon_drc_records_konnect_evidence(self):
        coupon = self.payload["coupon_drc"]
        self.assertEqual(set(coupon), COUPON_DRC_FIELDS)
        self.assertEqual(
            coupon["project"],
            (
                "/tmp/lh60-region-top-right-clean/"
                "lh60-region-top-right.kicad_pcb"
            ),
        )
        self.assertEqual(coupon["tool"], "Konnect run_drc")
        self.assertEqual(coupon["status"], "blocked")
        self.assertEqual(coupon["violations"], coupon["errors"] + coupon["warnings"])
        self.assertGreater(coupon["violations"], 0)
        self.assertEqual(
            coupon["source_series"],
            self.payload["source_series"],
        )
        self.assertEqual(
            self.payload["source_series"],
            {
                "r0_top_2u": "Gateron-LP",
                "r0_top_split_left_fn_1u": "Gateron-LP",
                "r0_top_split_right_1u": "Gateron-LP",
            },
        )
        self.assertEqual(coupon["library_nickname"], "lh60-sockets")
        self.assertEqual(coupon["library_path"], "lib/lh60-sockets")
        self.assertEqual(
            coupon["findings"],
            [{"severity": "error", "description": "Courtyards overlap"}],
        )

    def test_blocked_report_has_actionable_alternatives(self):
        alternatives = self.payload["minimum_change_alternatives"]
        self.assertGreater(len(alternatives), 0)
        for alternative in alternatives:
            self.assertEqual(set(alternative), ALTERNATIVE_FIELDS)
            self.assertTrue(alternative["change"])
            self.assertTrue(alternative["effect"])
            self.assertEqual(alternative["type"], "center-offset")
            self.assertEqual(alternative["axis"], "center_y_mm")
            self.assertTrue(alternative["requires_layout_approval"])
            self.assertNotEqual(alternative["offset_mm"], 0.0)
            moved_spec = RegionSpec(
                region=REGION,
                placements=tuple(
                    replace(
                        placement,
                        center_y_mm=(
                            placement.center_y_mm
                            + alternative["offset_mm"]
                        ),
                    )
                    if placement.socket_ref == alternative["socket_ref"]
                    else placement
                    for placement in single_g_spec().placements
                ),
            )
            result = solve_region(moved_spec)
            self.assertTrue(result.solved)
            self.assertEqual(
                alternative["minimum_clearances_mm"],
                {
                    "copper": result.minimum_copper_clearance_mm,
                    "hole_edge": result.minimum_hole_edge_clearance_mm,
                    "courtyard": result.minimum_courtyard_clearance_mm,
                },
            )


if __name__ == "__main__":
    unittest.main()
