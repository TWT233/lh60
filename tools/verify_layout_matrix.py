import unittest
from pathlib import Path


EXPECTED_SHARED_GROUPS = {
    frozenset({"r0_top_2u", "r0_top_split_right_1u"}),
    frozenset({"r2_enter_ansi_2.25u", "r2_enter_split_right_1.25u"}),
    frozenset({"r3_lshift_2.25u", "r3_lshift_split_1.25u"}),
    frozenset(
        {
            "r3_rshift_left_1.75u",
            "r3_rshift_right_1.75u",
        }
    ),
    frozenset({"r3_rshift_left_fn_1u", "r3_rshift_right_fn_1u"}),
}


class LayoutMatrixContractTest(unittest.TestCase):
    ROOT = Path(__file__).resolve().parents[1]

    def test_physical_layout_has_approved_counts_extents_and_centers(self):
        from tools.lh60_design.layout import KEY_PITCH_MM, physical_keys

        keys = physical_keys()
        self.assertEqual(len(keys), 75)
        self.assertEqual(len({key.physical_key_id for key in keys}), 75)
        self.assertEqual(
            tuple(sum(key.row == row for key in keys) for row in range(5)),
            (16, 14, 15, 17, 13),
        )
        self.assertNotIn(
            "r3_rshift_2.75u",
            {key.physical_key_id for key in keys},
        )

        for row in range(5):
            row_keys = [key for key in keys if key.row == row]
            self.assertEqual(min(key.x_u for key in row_keys), 0.0)
            self.assertEqual(max(key.x_u + key.width_u for key in row_keys), 15.0)

        for key in keys:
            with self.subTest(physical_key_id=key.physical_key_id):
                self.assertAlmostEqual(
                    key.center_x_u,
                    key.x_u + key.width_u / 2,
                )
                self.assertAlmostEqual(key.center_y_u, key.row + 0.5)
                self.assertAlmostEqual(
                    key.center_x_mm,
                    key.center_x_u * KEY_PITCH_MM,
                )
                self.assertAlmostEqual(
                    key.center_y_mm,
                    key.center_y_u * KEY_PITCH_MM,
                )

    def test_logical_nodes_cover_every_socket_with_five_shared_groups(self):
        from tools.lh60_design.layout import physical_keys
        from tools.lh60_design.matrix import logical_nodes

        keys = physical_keys()
        nodes = logical_nodes()
        physical_ids = {key.physical_key_id for key in keys}
        grouped_ids = [
            physical_key_id
            for node in nodes
            for physical_key_id in node.physical_key_ids
        ]
        shared_groups = {
            frozenset(node.physical_key_ids)
            for node in nodes
            if len(node.physical_key_ids) > 1
        }

        self.assertEqual(len(nodes), 70)
        self.assertEqual(len({node.logical_node_id for node in nodes}), 70)
        self.assertEqual(set(grouped_ids), physical_ids)
        self.assertEqual(len(grouped_ids), len(set(grouped_ids)))
        self.assertEqual(shared_groups, EXPECTED_SHARED_GROUPS)
        rshift = next(
            node
            for node in nodes
            if "r3_rshift_left_1.75u" in node.physical_key_ids
        )
        self.assertEqual(
            rshift.logical_node_id,
            "r3_rshift_1.75u",
        )

    def test_split_left_function_keys_remain_independent_nodes(self):
        from tools.lh60_design.matrix import node_for_physical_key

        for physical_key_id in (
            "r0_top_split_left_fn_1u",
            "r2_enter_split_left_fn_1u",
            "r3_lshift_split_left_fn_1u",
        ):
            with self.subTest(physical_key_id=physical_key_id):
                node = node_for_physical_key(physical_key_id)
                self.assertEqual(node.physical_key_ids, (physical_key_id,))

    def test_matrix_allocation_is_ten_by_seven_row_major(self):
        from tools.lh60_design.matrix import logical_nodes

        nodes = logical_nodes()
        for logical_index, node in enumerate(nodes):
            with self.subTest(logical_node_id=node.logical_node_id):
                expected_row, expected_column = divmod(logical_index, 10)
                self.assertEqual(node.logical_index, logical_index)
                self.assertEqual((node.row, node.column), (expected_row, expected_column))
                self.assertEqual(node.row_net, f"ROW{expected_row}")
                self.assertEqual(node.column_net, f"COL{expected_column}")
                self.assertEqual(node.diode_ref, f"D{logical_index + 1}")

        self.assertEqual({node.row for node in nodes}, set(range(7)))
        self.assertEqual({node.column for node in nodes}, set(range(10)))

    def test_gpio_map_matches_the_frozen_carrier_contract(self):
        from tools.lh60_design.matrix import gpio_map

        mapping = gpio_map()
        self.assertEqual(mapping.columns, tuple(f"GP{index}" for index in range(10)))
        self.assertEqual(
            mapping.rows,
            ("GP10", "GP11", "GP12", "GP13", "GP14", "GP15", "GP26"),
        )
        self.assertEqual(mapping.spares, ("GP27", "GP28", "GP29"))

    def test_four_region_rotation_sets_remain_explicitly_unresolved(self):
        from tools.lh60_design.layout import REGION_ROTATIONS_DEG, physical_keys

        self.assertEqual(
            REGION_ROTATIONS_DEG,
            {
                "top-right": (0, 90, 180, 270),
                "enter": (0, 90, 180, 270),
                "lshift": (0, 90, 180, 270),
                "rshift": (0, 90, 180, 270),
            },
        )
        self.assertEqual(
            {key.region for key in physical_keys() if key.region},
            set(REGION_ROTATIONS_DEG),
        )

    def test_current_layout_document_covers_every_key_and_node(self):
        from tools.lh60_design.layout import physical_keys
        from tools.lh60_design.matrix import logical_nodes

        text = (self.ROOT / "docs" / "layout-current.md").read_text()
        for key in physical_keys():
            self.assertIn(f"`{key.physical_key_id}`", text)
        for node in logical_nodes():
            self.assertIn(f"`{node.logical_node_id}`", text)
        self.assertIn("10 × 7", text)
        self.assertIn("GP27`, `GP28`, `GP29", text)
        self.assertIn("旋转待区域求解", text)


if __name__ == "__main__":
    unittest.main()
