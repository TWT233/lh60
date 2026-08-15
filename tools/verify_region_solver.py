import unittest


class RegionSolverContractTest(unittest.TestCase):
    def fixture(self, spacing_mm: float):
        from tools.lh60_design.regions import RegionPlacement, RegionSpec

        return RegionSpec(
            region="fixture",
            placements=(
                RegionPlacement(
                    socket_ref="SW1",
                    footprint="Gateron-LP-Hotswap-Socket-1U",
                    center_x_mm=0.0,
                    center_y_mm=0.0,
                    logical_node_id="node-a",
                ),
                RegionPlacement(
                    socket_ref="SW2",
                    footprint="Gateron-LP-Hotswap-Socket-1U",
                    center_x_mm=spacing_mm,
                    center_y_mm=0.0,
                    logical_node_id="node-b",
                ),
            ),
        )

    def test_rotation_enumeration_is_complete_and_deterministic(self):
        from tools.lh60_design.regions import enumerate_rotations

        combinations = enumerate_rotations(("SW1", "SW2"))

        self.assertEqual(len(combinations), 16)
        self.assertEqual(
            combinations[0],
            (("SW1", 0), ("SW2", 0)),
        )
        self.assertEqual(
            combinations[-1],
            (("SW1", 270), ("SW2", 270)),
        )
        self.assertEqual(
            set(combinations),
            {
                (("SW1", left), ("SW2", right))
                for left in (0, 90, 180, 270)
                for right in (0, 90, 180, 270)
            },
        )

    def test_clearance_measurement_reports_all_three_domains(self):
        from tools.lh60_design.regions import measure_clearances

        report = measure_clearances(self.fixture(19.05).placements)

        self.assertGreater(report.minimum_copper_clearance_mm, 0.25)
        self.assertGreater(report.minimum_hole_edge_clearance_mm, 0.50)
        self.assertGreaterEqual(report.minimum_courtyard_clearance_mm, 0.0)
        self.assertIsNotNone(report.closest_copper_pair)
        self.assertIsNotNone(report.closest_hole_pair)
        self.assertIsNotNone(report.closest_courtyard_pair)

    def test_hard_limit_failure_records_measured_conflicts(self):
        from tools.lh60_design.regions import solve_region

        report = solve_region(self.fixture(0.0))

        self.assertEqual(report.region, "fixture")
        self.assertFalse(report.solved)
        self.assertEqual(report.drc_status, "blocked")
        self.assertGreater(len(report.blocking_conflicts), 0)
        for conflict in report.blocking_conflicts:
            self.assertIn(
                conflict.domain,
                {"copper", "hole_edge", "courtyard"},
            )
            self.assertLess(conflict.actual_mm, conflict.required_mm)
            self.assertAlmostEqual(
                conflict.shortfall_mm,
                conflict.required_mm - conflict.actual_mm,
            )
            self.assertEqual(len(conflict.items), 2)

    def test_solver_prefers_target_compliance_then_clearance(self):
        from tools.lh60_design.regions import RegionPlacement, RegionSpec, solve_region

        region = RegionSpec(
            region="rotation-choice",
            placements=(
                RegionPlacement(
                    socket_ref="SW1",
                    footprint="Gateron-LP-Hotswap-Socket-1U",
                    center_x_mm=0.0,
                    center_y_mm=0.0,
                    logical_node_id="node-a",
                    allowed_rotations_deg=(0,),
                ),
                RegionPlacement(
                    socket_ref="SW2",
                    footprint="Gateron-LP-Hotswap-Socket-1U",
                    center_x_mm=17.0,
                    center_y_mm=0.0,
                    logical_node_id="node-b",
                    allowed_rotations_deg=(0, 180),
                ),
            ),
        )

        report = solve_region(region)

        self.assertTrue(report.solved)
        self.assertEqual(report.drc_status, "geometry-pass")
        self.assertEqual(
            tuple(placement.rotation_deg for placement in report.placements),
            (0, 180),
        )
        self.assertGreaterEqual(report.minimum_copper_clearance_mm, 0.25)
        self.assertGreaterEqual(report.minimum_hole_edge_clearance_mm, 0.45)
        self.assertGreaterEqual(report.minimum_courtyard_clearance_mm, 0.0)

    def test_report_serialization_matches_wave_two_schema(self):
        from tools.lh60_design.regions import solve_region

        payload = solve_region(self.fixture(19.05)).to_dict()

        self.assertEqual(
            set(payload),
            {
                "region",
                "solved",
                "placements",
                "minimum_copper_clearance_mm",
                "minimum_hole_edge_clearance_mm",
                "minimum_courtyard_clearance_mm",
                "hole_edge_target_met",
                "drc_status",
                "blocking_conflicts",
            },
        )
        self.assertEqual(
            set(payload["placements"][0]),
            {
                "socket_ref",
                "footprint",
                "center_x_mm",
                "center_y_mm",
                "rotation_deg",
                "logical_node_id",
            },
        )
        self.assertEqual(payload["drc_status"], "geometry-pass")

    def test_invalid_region_inputs_fail_before_search(self):
        from tools.lh60_design.regions import RegionPlacement, RegionSpec, solve_region

        empty_region = RegionSpec(region="empty", placements=())
        duplicate_refs = RegionSpec(
            region="bad",
            placements=(
                RegionPlacement("SW1", "Gateron-LP-Hotswap-Socket-1U", 0, 0, "a"),
                RegionPlacement("SW1", "Gateron-LP-Hotswap-Socket-1U", 19.05, 0, "b"),
            ),
        )
        unknown_footprint = RegionSpec(
            region="bad-footprint",
            placements=(
                RegionPlacement("SW1", "missing", 0, 0, "a"),
            ),
        )

        with self.assertRaisesRegex(ValueError, "at least one placement"):
            solve_region(empty_region)
        with self.assertRaisesRegex(ValueError, "duplicate socket_ref"):
            solve_region(duplicate_refs)
        with self.assertRaisesRegex(ValueError, "unknown footprint"):
            solve_region(unknown_footprint)


if __name__ == "__main__":
    unittest.main()
