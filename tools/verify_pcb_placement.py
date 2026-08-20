from collections import Counter
import unittest


class SocketPlacementPlanTest(unittest.TestCase):
    def test_plan_maps_every_physical_key_to_its_exact_reference_and_center(self):
        from tools.lh60_design.layout import physical_keys
        from tools.lh60_design.pcb import socket_placement_plan
        from tools.lh60_design.schematic import switch_references

        keys = physical_keys()
        references = switch_references()
        plan = socket_placement_plan()

        self.assertEqual(len(plan), 75)
        self.assertEqual(len({placement.reference for placement in plan}), 75)
        self.assertNotIn("SW59", {placement.reference for placement in plan})
        self.assertEqual(
            next(
                placement.reference
                for placement in plan
                if placement.physical_key_id == "r3_rshift_left_1.75u"
            ),
            "SW60",
        )
        self.assertEqual(plan[-1].reference, "SW76")
        self.assertEqual(
            [placement.physical_key_id for placement in plan],
            [key.physical_key_id for key in keys],
        )
        for key, placement in zip(keys, plan):
            with self.subTest(physical_key_id=key.physical_key_id):
                self.assertEqual(placement.reference, references[key.physical_key_id])
                self.assertAlmostEqual(placement.x_mm, key.center_x_mm)
                self.assertAlmostEqual(placement.y_mm, key.center_y_mm)
                self.assertEqual(placement.layer, "F.Cu")

    def test_reviewed_rotations_override_the_solver_reports(self):
        from tools.lh60_design.pcb import (
            REVIEWED_ROTATION_OVERRIDES_DEG,
            socket_placement_plan,
        )

        rotations = {
            placement.physical_key_id: placement.rotation_deg
            for placement in socket_placement_plan()
        }
        self.assertEqual(
            REVIEWED_ROTATION_OVERRIDES_DEG,
            {
                "r0_top_split_left_fn_1u": 0.0,
                "r2_enter_ansi_2.25u": 180.0,
                "r2_enter_split_left_fn_1u": 0.0,
                "r2_enter_split_right_1.25u": 0.0,
                "r3_lshift_split_left_fn_1u": 0.0,
                "r3_lshift_2.25u": 180.0,
                "r3_lshift_split_1.25u": 0.0,
            },
        )
        self.assertEqual(
            {
                key_id: rotation
                for key_id, rotation in rotations.items()
                if rotation != 0
            },
            {
                "r0_top_2u": 180.0,
                "r2_enter_ansi_2.25u": 180.0,
                "r3_lshift_2.25u": 180.0,
                "r3_rshift_left_1.75u": 180.0,
                "r3_rshift_right_fn_1u": 180.0,
            },
        )

    def test_apply_uses_only_move_then_absolute_rotate_for_each_socket(self):
        from tools.lh60_design.pcb import apply_socket_placements, socket_placement_plan

        class FakeClient:
            def __init__(self):
                self.calls = []

            def tool_schemas(self, toolset):
                self.calls.append(("load", toolset))
                return {"move_component": {}, "rotate_component": {}}

            def call_tool(self, name, arguments):
                self.calls.append((name, arguments))
                return {}

        client = FakeClient()
        apply_socket_placements(client, "/tmp/lh60.kicad_pcb")

        plan = socket_placement_plan()
        self.assertEqual(client.calls[0], ("load", "pcb_components"))
        self.assertEqual(len(client.calls), 1 + 2 * len(plan))
        for index, placement in enumerate(plan):
            move = client.calls[1 + index * 2]
            rotate = client.calls[2 + index * 2]
            self.assertEqual(
                move,
                (
                    "move_component",
                    {
                        "board": "/tmp/lh60.kicad_pcb",
                        "reference": placement.reference,
                        "x": placement.x_mm,
                        "y": placement.y_mm,
                    },
                ),
            )
            self.assertEqual(
                rotate,
                (
                    "rotate_component",
                    {
                        "board": "/tmp/lh60.kicad_pcb",
                        "reference": placement.reference,
                        "rotation": placement.rotation_deg,
                    },
                ),
            )

    def test_production_board_socket_roots_match_the_plan(self):
        from tools.lh60_design.pcb import (
            BOARD,
            read_board_placements,
            socket_placement_plan,
        )

        actual = read_board_placements(BOARD)
        plan = socket_placement_plan()

        self.assertEqual(
            {reference for reference in actual if reference.startswith("SW")},
            {placement.reference for placement in plan},
        )
        for placement in plan:
            with self.subTest(reference=placement.reference):
                x, y, rotation, layer = actual[placement.reference]
                self.assertAlmostEqual(x, placement.x_mm)
                self.assertAlmostEqual(y, placement.y_mm)
                self.assertAlmostEqual(rotation % 360, placement.rotation_deg % 360)
                self.assertEqual(layer, placement.layer)


class ConnectorPlacementPlanTest(unittest.TestCase):
    def test_connector_placement_rejects_ambiguous_rotation_or_layer_at_construction(self):
        from tools.lh60_design.pcb import ConnectorPlacement

        with self.assertRaisesRegex(ValueError, "0 or 180"):
            ConnectorPlacement("J1", 3, 10.0, 10.0, 90.0)
        with self.assertRaisesRegex(ValueError, "B.Cu"):
            ConnectorPlacement("J1", 3, 10.0, 10.0, 0.0, layer="F.Cu")

    def test_legacy_centroid_search_inputs_are_frozen_exactly(self):
        from tools.lh60_design import pcb

        offsets = getattr(pcb, "CANDIDATE_OFFSETS_MM", None)
        self.assertIsNotNone(offsets, "legacy search offsets must be explicit")
        self.assertEqual(
            offsets,
            (
                (0.0, 0.0),
                (-5.0, 0.0),
                (5.0, 0.0),
                (0.0, -5.0),
                (0.0, 5.0),
                (-5.0, -5.0),
                (5.0, -5.0),
                (-5.0, 5.0),
                (5.0, 5.0),
                (-10.0, 0.0),
                (10.0, 0.0),
                (0.0, -10.0),
                (0.0, 10.0),
                (-10.0, -10.0),
                (10.0, -10.0),
                (-10.0, 10.0),
                (10.0, 10.0),
            ),
        )
        self.assertEqual(len(offsets), 17)

        read_centroids = getattr(pcb, "read_legacy_connector_centroids", None)
        self.assertIsNotNone(
            read_centroids,
            "legacy centroids must be read from the committed L5 baseline",
        )
        self.assertEqual(
            tuple(read_centroids().items()),
            (
                ("J1", (172.32625, 116.36500000000001)),
                ("J2", (173.83625, 122.045)),
                ("J3", (176.85625, 122.755)),
                ("J4", (179.87625, 121.69)),
                ("J5", (182.39291666666668, 119.915)),
                ("J6", (183.65125, 123.46499999999999)),
            ),
        )

    def test_legacy_centroid_search_exhausts_all_408_board_bound_candidates(self):
        from tools.lh60_design import pcb

        audit_search = getattr(pcb, "audit_legacy_connector_search", None)
        self.assertIsNotNone(
            audit_search,
            "legacy placement search must expose a deterministic audit",
        )
        rotations = getattr(pcb, "CANDIDATE_ROTATIONS_DEG", None)
        self.assertEqual(rotations, (0.0, 90.0, 180.0, 270.0))

        audit = audit_search(pcb.read_legacy_connector_centroids())
        expected_order = tuple(
            (reference, offset_x, offset_y, rotation)
            for reference in ("J1", "J2", "J3", "J4", "J5", "J6")
            for offset_x, offset_y in pcb.CANDIDATE_OFFSETS_MM
            for rotation in rotations
        )

        self.assertEqual(len(audit), 408)
        self.assertEqual(
            tuple(
                (
                    result.placement.reference,
                    result.offset_x_mm,
                    result.offset_y_mm,
                    result.placement.rotation_deg,
                )
                for result in audit
            ),
            expected_order,
        )
        self.assertEqual(
            Counter(
                reason
                for result in audit
                for reason in result.rejection_reasons
            ),
            {"board_max_y": 408},
        )
        self.assertTrue(
            all(result.rejection_reasons == ("board_max_y",) for result in audit)
        )
        self.assertTrue(all(not result.viable for result in audit))
        self.assertTrue(
            all(result.envelope.max_y > 95.25 - 0.5 for result in audit)
        )

    def test_frozen_positions_are_an_explicit_reviewed_override_not_search_output(self):
        from tools.lh60_design import pcb

        reason = getattr(pcb, "REVIEWED_PLACEMENT_OVERRIDE_REASON", None)
        self.assertEqual(
            reason,
            "The planned 408-candidate legacy-centroid search was exhausted: "
            "all candidates were outside production board access bounds because "
            "the source test points were outside the board outline. "
            "FROZEN_CONNECTOR_PLACEMENTS is a user-reviewed override subsequently "
            "validated by live access, courtyard, and DRC evidence; it was not "
            "generated by that search.",
        )
        self.assertEqual(
            tuple(
                (
                    placement.reference,
                    placement.pin_count,
                    placement.x_mm,
                    placement.y_mm,
                    placement.rotation_deg,
                )
                for placement in pcb.FROZEN_CONNECTOR_PLACEMENTS
            ),
            (
                ("J1", 3, 282.5, 36.0, 0.0),
                ("J2", 5, 77.5, 92.0, 0.0),
                ("J3", 5, 107.5, 92.0, 0.0),
                ("J4", 4, 3.0, 49.5, 0.0),
                ("J5", 3, 3.0, 55.5, 180.0),
                ("J6", 3, 282.5, 42.0, 180.0),
            ),
        )

    def test_frozen_plan_groups_six_headers_on_the_back_with_clear_access(self):
        from tools.lh60_design.pcb import frozen_connector_placements

        plan = frozen_connector_placements()
        self.assertEqual(
            [placement.reference for placement in plan],
            ["J1", "J2", "J3", "J4", "J5", "J6"],
        )
        self.assertEqual(
            [placement.pin_count for placement in plan],
            [3, 5, 5, 4, 3, 3],
        )
        self.assertTrue(all(placement.layer == "B.Cu" for placement in plan))
        self.assertTrue(all(placement.rotation_deg in (0.0, 180.0) for placement in plan))
        self.assertTrue(
            all(
                coordinate * 2 == round(coordinate * 2)
                for placement in plan
                for coordinate in (placement.x_mm, placement.y_mm)
            )
        )
        self.assertEqual(
            [(p.reference, p.x_mm, p.y_mm, p.rotation_deg) for p in plan],
            [
                ("J1", 282.5, 36.0, 0.0),
                ("J2", 77.5, 92.0, 0.0),
                ("J3", 107.5, 92.0, 0.0),
                ("J4", 3.0, 49.5, 0.0),
                ("J5", 3.0, 55.5, 180.0),
                ("J6", 282.5, 42.0, 180.0),
            ],
        )
        self.assertEqual(
            [placement.pin1_direction for placement in plan],
            ["south", "south", "south", "south", "north", "north"],
        )

        for placement in plan:
            with self.subTest(reference=placement.reference):
                envelope = placement.access_envelope()
                self.assertGreaterEqual(envelope.min_x, 0.5)
                self.assertGreaterEqual(envelope.min_y, 0.5)
                self.assertLessEqual(envelope.max_x, 285.25)
                self.assertLessEqual(envelope.max_y, 94.75)
                self.assertEqual(placement.extraction_clearance_mm, 15.0)

        for index, first in enumerate(plan):
            for second in plan[index + 1 :]:
                with self.subTest(first=first.reference, second=second.reference):
                    self.assertGreaterEqual(
                        first.access_envelope().distance_to(second.access_envelope()),
                        1.0,
                    )

    def test_apply_sets_each_header_pose_then_idempotent_back_side(self):
        from tools.lh60_design.pcb import (
            apply_connector_placements,
            frozen_connector_placements,
        )

        class FakeClient:
            def __init__(self):
                self.calls = []
                self.layers = {
                    placement.reference: "F.Cu"
                    for placement in frozen_connector_placements()
                }

            def tool_schemas(self, toolset):
                self.calls.append(("load", toolset))
                return {
                    "move_component": {},
                    "rotate_component": {},
                    "flip_component": {},
                }

            def call_tool_json(self, name, arguments):
                self.calls.append((name, arguments))
                placement = next(
                    item
                    for item in frozen_connector_placements()
                    if item.reference == arguments["reference"]
                )
                if name == "move_component":
                    return {
                        "moved": placement.reference,
                        "x": placement.x_mm,
                        "y": placement.y_mm,
                        "source": "file",
                    }
                if name == "rotate_component":
                    return {
                        "rotated": placement.reference,
                        "rotation": placement.rotation_deg,
                        "source": "file",
                    }
                changed = self.layers[placement.reference] != arguments["layer"]
                self.layers[placement.reference] = arguments["layer"]
                return {
                    "flipped": placement.reference,
                    "layer": self.layers[placement.reference],
                    "changed": changed,
                    "source": "file",
                }

        client = FakeClient()
        first = apply_connector_placements(client, "/tmp/lh60.kicad_pcb")
        second = apply_connector_placements(client, "/tmp/lh60.kicad_pcb")
        plan = frozen_connector_placements()

        self.assertEqual(len(client.calls), 2 * (1 + 3 * len(plan)))
        for pass_index, (applied, expected_changed) in enumerate(
            ((first, True), (second, False))
        ):
            offset = pass_index * (1 + 3 * len(plan))
            self.assertEqual(client.calls[offset], ("load", "pcb_components"))
            self.assertEqual(
                [item["reference"] for item in applied],
                [placement.reference for placement in plan],
            )
            self.assertTrue(all(item["layer"] == "B.Cu" for item in applied))
            self.assertTrue(
                all(item["flip_changed"] is expected_changed for item in applied)
            )
            for index, placement in enumerate(plan):
                move, rotate, flip = client.calls[
                    offset + 1 + index * 3 : offset + 4 + index * 3
                ]
                self.assertEqual(
                    move,
                    (
                        "move_component",
                        {
                            "board": "/tmp/lh60.kicad_pcb",
                            "reference": placement.reference,
                            "x": placement.x_mm,
                            "y": placement.y_mm,
                        },
                    ),
                )
                self.assertEqual(
                    rotate,
                    (
                        "rotate_component",
                        {
                            "board": "/tmp/lh60.kicad_pcb",
                            "reference": placement.reference,
                            "rotation": placement.rotation_deg,
                        },
                    ),
                )
                self.assertEqual(
                    flip,
                    (
                        "flip_component",
                        {
                            "board": "/tmp/lh60.kicad_pcb",
                            "reference": placement.reference,
                            "layer": "B.Cu",
                        },
                    ),
                )

        self.assertEqual(
            client.layers,
            {placement.reference: "B.Cu" for placement in plan},
        )

    def test_apply_rejects_flip_results_that_do_not_prove_the_target_final_state(self):
        from tools.lh60_design.pcb import apply_connector_placements

        class InvalidFlipClient:
            def __init__(self, field, value):
                self.field = field
                self.value = value

            def tool_schemas(self, _toolset):
                return {
                    "move_component": {},
                    "rotate_component": {},
                    "flip_component": {},
                }

            def call_tool_json(self, name, arguments):
                reference = arguments["reference"]
                if name == "move_component":
                    return {
                        "moved": reference,
                        "x": arguments["x"],
                        "y": arguments["y"],
                        "source": "file",
                    }
                if name == "rotate_component":
                    return {
                        "rotated": reference,
                        "rotation": arguments["rotation"],
                        "source": "file",
                    }
                result = {
                    "flipped": reference,
                    "layer": "B.Cu",
                    "changed": True,
                    "source": "file",
                }
                result[self.field] = self.value
                return result

        cases = (
            ("flipped", "J2", "flip readback mismatch"),
            ("layer", "F.Cu", "flip readback mismatch"),
            ("source", "ipc", "closed-board file path"),
        )
        for field, value, error in cases:
            with self.subTest(field=field):
                with self.assertRaisesRegex(RuntimeError, error):
                    apply_connector_placements(
                        InvalidFlipClient(field, value),
                        "/tmp/lh60.kicad_pcb",
                    )

    def test_apply_refuses_missing_schema_or_non_file_response(self):
        from tools.lh60_design.pcb import apply_connector_placements

        class MissingFlipClient:
            def tool_schemas(self, _toolset):
                return {"move_component": {}, "rotate_component": {}}

        with self.assertRaisesRegex(RuntimeError, "flip_component"):
            apply_connector_placements(MissingFlipClient(), "/tmp/lh60.kicad_pcb")

        class LiveMoveClient:
            def tool_schemas(self, _toolset):
                return {
                    "move_component": {},
                    "rotate_component": {},
                    "flip_component": {},
                }

            def call_tool_json(self, name, arguments):
                if name == "move_component":
                    return {"moved": arguments["reference"], "source": "ipc"}
                raise AssertionError("must stop before rotate/flip")

        with self.assertRaisesRegex(RuntimeError, "closed-board"):
            apply_connector_placements(LiveMoveClient(), "/tmp/lh60.kicad_pcb")


if __name__ == "__main__":
    unittest.main()
