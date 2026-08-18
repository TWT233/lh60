import unittest


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


if __name__ == "__main__":
    unittest.main()
