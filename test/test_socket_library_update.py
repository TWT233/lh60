from __future__ import annotations

import unittest

from tools.update_socket_library import (
    ALL_NAMES,
    DUAL_NAME,
    GATERON_NAMES,
    REQUIRED_TOOL_FIELDS,
    build_operation_plan,
    choc_courtyard_polygons,
    gateron_courtyard_polygons,
)


class SocketGeometryPlanTest(unittest.TestCase):
    def test_gateron_courtyard_encloses_body_and_land_pattern(self) -> None:
        polygons = gateron_courtyard_polygons()
        self.assertEqual(len(polygons), 1)
        self.assertEqual(
            tuple(round(value, 3) for value in polygons[0].bounds),
            (-9.575, 2.275, 7.775, 8.175),
        )

    def test_choc_courtyard_encloses_body_and_land_pattern(self) -> None:
        polygons = choc_courtyard_polygons()
        self.assertEqual(len(polygons), 1)
        self.assertEqual(
            tuple(round(value, 3) for value in polygons[0].bounds),
            (-5.25, -8.5, 10.25, -1.2),
        )

    def test_operation_plan_covers_every_footprint_and_required_change(self) -> None:
        operations = build_operation_plan()
        targets = {operation["footprint"] for operation in operations}
        self.assertEqual(targets, set(ALL_NAMES))

        dual_pad_edits = [
            operation
            for operation in operations
            if operation["footprint"] == DUAL_NAME
            and operation["tool"] == "edit_footprint_pad"
        ]
        self.assertEqual(
            [(item["arguments"]["pad_number"], item["arguments"]["new_number"])
             for item in dual_pad_edits],
            [("3", "1"), ("4", "2")],
        )

        for name in ALL_NAMES:
            footprint_operations = [
                operation for operation in operations if operation["footprint"] == name
            ]
            graphics_layers = {
                operation["arguments"]["selector"]["layer"]
                for operation in footprint_operations
                if operation["tool"] == "set_footprint_graphics"
            }
            self.assertEqual(
                graphics_layers,
                {"F.SilkS", "Dwgs.User", "B.Fab", "B.CrtYd"},
            )
            self.assertTrue(
                any(
                    operation["tool"] == "set_footprint_metadata"
                    for operation in footprint_operations
                )
            )
            model_operation = next(
                operation
                for operation in footprint_operations
                if operation["tool"] == "set_footprint_models"
            )
            expected_models = 2 if name == DUAL_NAME else 1
            self.assertEqual(
                len(model_operation["arguments"]["models"]),
                expected_models,
            )

        self.assertEqual(len(GATERON_NAMES), 7)


class SocketMcpContractTest(unittest.TestCase):
    def test_required_tool_fields_cover_every_mutation(self) -> None:
        self.assertEqual(
            set(REQUIRED_TOOL_FIELDS),
            {
                "edit_footprint_pad",
                "set_footprint_graphics",
                "set_footprint_metadata",
                "set_footprint_models",
            },
        )
        self.assertGreaterEqual(
            REQUIRED_TOOL_FIELDS["edit_footprint_pad"],
            {"footprint_path", "pad_number", "new_number", "match_all"},
        )


if __name__ == "__main__":
    unittest.main()
