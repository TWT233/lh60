import unittest


class InterboardContractTest(unittest.TestCase):
    EXPECTED_PIN_MAP = (
        (1, "GND"),
        (2, "COL0"),
        (3, "COL1"),
        (4, "COL2"),
        (5, "GND"),
        (6, "COL3"),
        (7, "COL4"),
        (8, "COL5"),
        (9, "GND"),
        (10, "COL6"),
        (11, "COL7"),
        (12, "COL8"),
        (13, "COL9"),
        (14, "ROW0"),
        (15, "ROW1"),
        (16, "GND"),
        (17, "ROW2"),
        (18, "ROW3"),
        (19, "ROW4"),
        (20, "GND"),
        (21, "ROW5"),
        (22, "ROW6"),
        (23, None),
        (24, "GND"),
    )
    EXPECTED_GPIO_MAP = (
        ("COL0", "GP0"),
        ("COL1", "GP1"),
        ("COL2", "GP2"),
        ("COL3", "GP3"),
        ("COL4", "GP4"),
        ("COL5", "GP5"),
        ("COL6", "GP6"),
        ("COL7", "GP7"),
        ("COL8", "GP8"),
        ("COL9", "GP9"),
        ("ROW0", "GP10"),
        ("ROW1", "GP11"),
        ("ROW2", "GP12"),
        ("ROW3", "GP13"),
        ("ROW4", "GP14"),
        ("ROW5", "GP15"),
        ("ROW6", "GP26"),
    )
    EXPECTED_PROHIBITED_NETS = frozenset(
        {
            "VSYS",
            "3V3",
            "D+",
            "D-",
            "VBUS",
            "RUN",
            "BOOTSEL",
            "SWDIO",
            "SWCLK",
            "GP27",
            "GP28",
            "GP29",
        }
    )

    def contract_module(self):
        from tools.lh60_design import interconnect

        return interconnect

    def test_exact_pin_map_and_connector_identity(self):
        from tools.lh60_design.interconnect import interboard_contract

        contract = interboard_contract()
        self.assertEqual(
            (
                contract.connector.manufacturer,
                contract.connector.mpn,
                contract.connector.lcsc_part,
            ),
            ("XUNPU", "FPC-05F-24PH20", "C2856805"),
        )
        self.assertEqual(
            contract.connector.datasheet_url,
            "https://datasheet.lcsc.com/datasheet/pdf/0ee18373cdadd5e6c8c1fa51e58ba102.pdf?productCode=C2856805",
        )
        self.assertEqual(
            tuple((pin.number, pin.net_name) for pin in contract.pins),
            self.EXPECTED_PIN_MAP,
        )

    def test_passive_reversal_invariant_is_not_a_powered_safety_api(self):
        from tools.lh60_design.interconnect import (
            interboard_contract,
            reversed_pin_number,
        )

        contract = interboard_contract()
        self.assertEqual(contract.ground_pins, frozenset({1, 5, 9, 16, 20, 24}))
        for pin in contract.pins:
            reversed_pin = contract.pin(reversed_pin_number(pin.number))
            self.assertEqual(
                pin.net_name == "GND",
                reversed_pin.net_name == "GND",
            )
        self.assertFalse(hasattr(contract, "powered_reversal_is_safe"))

    def test_mif_state_starts_unapproved(self):
        from tools.lh60_design.interconnect import interboard_contract

        cable = interboard_contract().cable
        self.assertIsNone(cable.approved_mif_revision)
        self.assertIsNone(cable.cable_mpn)
        self.assertIsNone(cable.contact_orientation)

    def test_strict_pin_numbering_and_pin_lookup(self):
        from tools.lh60_design.interconnect import interboard_contract

        contract = interboard_contract()
        self.assertEqual(tuple(pin.number for pin in contract.pins), tuple(range(1, 25)))
        self.assertEqual(contract.pin(1).net_name, "GND")
        self.assertTrue(contract.pin(23).is_no_connect)
        self.assertEqual(contract.pin(24).net_name, "GND")

    def test_exact_signal_ground_and_nc_sets(self):
        from tools.lh60_design.interconnect import interboard_contract

        contract = interboard_contract()
        self.assertEqual(
            contract.signal_nets,
            frozenset(
                {
                    "COL0",
                    "COL1",
                    "COL2",
                    "COL3",
                    "COL4",
                    "COL5",
                    "COL6",
                    "COL7",
                    "COL8",
                    "COL9",
                    "ROW0",
                    "ROW1",
                    "ROW2",
                    "ROW3",
                    "ROW4",
                    "ROW5",
                    "ROW6",
                }
            ),
        )
        self.assertEqual(contract.ground_pins, frozenset({1, 5, 9, 16, 20, 24}))
        self.assertEqual(contract.no_connect_pins, frozenset({23}))
        self.assertNotIn("NC", contract.signal_nets)
        self.assertFalse(any(pin.net_name == "NC" for pin in contract.pins))

    def test_exact_prohibited_nets_and_gpio_map(self):
        from tools.lh60_design.interconnect import interboard_contract

        contract = interboard_contract()
        self.assertEqual(contract.prohibited_nets, self.EXPECTED_PROHIBITED_NETS)
        self.assertEqual(contract.matrix_gpio_map, self.EXPECTED_GPIO_MAP)

    def test_cable_geometry_is_frozen(self):
        from tools.lh60_design.interconnect import interboard_contract

        cable = interboard_contract().cable
        self.assertEqual(cable.pitch_mm, 0.5)
        self.assertEqual(cable.mating_width_mm, 12.50)
        self.assertEqual(cable.mating_width_tolerance_mm, 0.03)
        self.assertEqual(cable.mating_thickness_mm, 0.30)
        self.assertEqual(cable.mating_thickness_tolerance_mm, 0.03)
        self.assertEqual(cable.exposed_conductor_min_mm, 3.00)
        self.assertEqual(cable.stiffener_length_mm, 6.00)
        self.assertEqual(cable.target_max_length_mm, 100.0)
        self.assertEqual(cable.design_max_length_mm, 150.0)

    def test_reversed_pin_number_rejects_out_of_range_inputs(self):
        from tools.lh60_design.interconnect import reversed_pin_number

        with self.assertRaisesRegex(ValueError, "1..24"):
            reversed_pin_number(0)
        with self.assertRaisesRegex(ValueError, "1..24"):
            reversed_pin_number(25)

    def test_constructor_rejects_pin_23_as_electrical_nc_net(self):
        interconnect = self.contract_module()
        pins = tuple(
            interconnect.InterconnectPin(number=number, net_name=net_name)
            for number, net_name in self.EXPECTED_PIN_MAP
        )
        pins = pins[:22] + (
            interconnect.InterconnectPin(number=23, net_name="NC"),
        ) + pins[23:]

        with self.assertRaisesRegex(ValueError, "pin 23"):
            interconnect.InterboardContract(
                connector=interconnect.ConnectorIdentity(
                    manufacturer="XUNPU",
                    mpn="FPC-05F-24PH20",
                    lcsc_part="C2856805",
                    datasheet_url=interconnect.DATASHEET_URL,
                ),
                pins=pins,
                matrix_gpio_map=self.EXPECTED_GPIO_MAP,
                prohibited_nets=self.EXPECTED_PROHIBITED_NETS,
                cable=interconnect.CableContract(
                    pitch_mm=0.5,
                    mating_width_mm=12.50,
                    mating_width_tolerance_mm=0.03,
                    mating_thickness_mm=0.30,
                    mating_thickness_tolerance_mm=0.03,
                    exposed_conductor_min_mm=3.00,
                    stiffener_length_mm=6.00,
                    target_max_length_mm=100.0,
                    design_max_length_mm=150.0,
                ),
            )

    def test_constructor_rejects_wrong_connector_identity(self):
        interconnect = self.contract_module()

        with self.assertRaisesRegex(ValueError, "connector"):
            interconnect.InterboardContract(
                connector=interconnect.ConnectorIdentity(
                    manufacturer="XUNPU",
                    mpn="WRONG-MPN",
                    lcsc_part="C2856805",
                    datasheet_url=interconnect.DATASHEET_URL,
                ),
                pins=tuple(
                    interconnect.InterconnectPin(number=number, net_name=net_name)
                    for number, net_name in self.EXPECTED_PIN_MAP
                ),
                matrix_gpio_map=self.EXPECTED_GPIO_MAP,
                prohibited_nets=self.EXPECTED_PROHIBITED_NETS,
                cable=interconnect.CableContract(
                    pitch_mm=0.5,
                    mating_width_mm=12.50,
                    mating_width_tolerance_mm=0.03,
                    mating_thickness_mm=0.30,
                    mating_thickness_tolerance_mm=0.03,
                    exposed_conductor_min_mm=3.00,
                    stiffener_length_mm=6.00,
                    target_max_length_mm=100.0,
                    design_max_length_mm=150.0,
                ),
            )

    def test_constructor_rejects_wrong_cable_geometry(self):
        interconnect = self.contract_module()

        with self.assertRaisesRegex(ValueError, "cable"):
            interconnect.InterboardContract(
                connector=interconnect.ConnectorIdentity(
                    manufacturer="XUNPU",
                    mpn="FPC-05F-24PH20",
                    lcsc_part="C2856805",
                    datasheet_url=interconnect.DATASHEET_URL,
                ),
                pins=tuple(
                    interconnect.InterconnectPin(number=number, net_name=net_name)
                    for number, net_name in self.EXPECTED_PIN_MAP
                ),
                matrix_gpio_map=self.EXPECTED_GPIO_MAP,
                prohibited_nets=self.EXPECTED_PROHIBITED_NETS,
                cable=interconnect.CableContract(
                    pitch_mm=0.5,
                    mating_width_mm=12.60,
                    mating_width_tolerance_mm=0.03,
                    mating_thickness_mm=0.30,
                    mating_thickness_tolerance_mm=0.03,
                    exposed_conductor_min_mm=3.00,
                    stiffener_length_mm=6.00,
                    target_max_length_mm=100.0,
                    design_max_length_mm=150.0,
                ),
            )

    def test_constructor_rejects_wrong_matrix_gpio_map(self):
        interconnect = self.contract_module()
        wrong_gpio_map = self.EXPECTED_GPIO_MAP[:-1] + (("ROW6", "GP27"),)

        with self.assertRaisesRegex(ValueError, "matrix_gpio_map"):
            interconnect.InterboardContract(
                connector=interconnect.ConnectorIdentity(
                    manufacturer="XUNPU",
                    mpn="FPC-05F-24PH20",
                    lcsc_part="C2856805",
                    datasheet_url=interconnect.DATASHEET_URL,
                ),
                pins=tuple(
                    interconnect.InterconnectPin(number=number, net_name=net_name)
                    for number, net_name in self.EXPECTED_PIN_MAP
                ),
                matrix_gpio_map=wrong_gpio_map,
                prohibited_nets=self.EXPECTED_PROHIBITED_NETS,
                cable=interconnect.CableContract(
                    pitch_mm=0.5,
                    mating_width_mm=12.50,
                    mating_width_tolerance_mm=0.03,
                    mating_thickness_mm=0.30,
                    mating_thickness_tolerance_mm=0.03,
                    exposed_conductor_min_mm=3.00,
                    stiffener_length_mm=6.00,
                    target_max_length_mm=100.0,
                    design_max_length_mm=150.0,
                ),
            )


if __name__ == "__main__":
    unittest.main()
