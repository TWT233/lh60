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


if __name__ == "__main__":
    unittest.main()
