from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache


PIN_COUNT = 24
DATASHEET_URL = (
    "https://datasheet.lcsc.com/datasheet/pdf/"
    "0ee18373cdadd5e6c8c1fa51e58ba102.pdf?productCode=C2856805"
)
PIN_NETS = (
    "GND",
    "COL0",
    "COL1",
    "COL2",
    "GND",
    "COL3",
    "COL4",
    "COL5",
    "GND",
    "COL6",
    "COL7",
    "COL8",
    "COL9",
    "ROW0",
    "ROW1",
    "GND",
    "ROW2",
    "ROW3",
    "ROW4",
    "GND",
    "ROW5",
    "ROW6",
    None,
    "GND",
)
PROHIBITED_NETS = frozenset(
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
EXPECTED_CONNECTOR_IDENTITY = (
    "XUNPU",
    "FPC-05F-24PH20",
    "C2856805",
    DATASHEET_URL,
)
EXPECTED_CABLE_GEOMETRY = (
    0.5,
    12.50,
    0.03,
    0.30,
    0.03,
    3.00,
    6.00,
    100.0,
    150.0,
)


@dataclass(frozen=True)
class InterconnectPin:
    number: int
    net_name: str | None

    @property
    def is_no_connect(self) -> bool:
        return self.net_name is None


@dataclass(frozen=True)
class ConnectorIdentity:
    manufacturer: str
    mpn: str
    lcsc_part: str
    datasheet_url: str


@dataclass(frozen=True)
class CableContract:
    pitch_mm: float
    mating_width_mm: float
    mating_width_tolerance_mm: float
    mating_thickness_mm: float
    mating_thickness_tolerance_mm: float
    exposed_conductor_min_mm: float
    stiffener_length_mm: float
    target_max_length_mm: float
    design_max_length_mm: float


@dataclass(frozen=True)
class InterboardContract:
    connector: ConnectorIdentity
    pins: tuple[InterconnectPin, ...]
    prohibited_nets: frozenset[str]
    cable: CableContract

    def __post_init__(self) -> None:
        if tuple(pin.number for pin in self.pins) != tuple(range(1, PIN_COUNT + 1)):
            raise ValueError("interconnect pins must be exactly 1..24")
        if tuple(pin.net_name for pin in self.pins) != PIN_NETS:
            raise ValueError("interconnect pins must match the frozen 24-pin contract, including pin 23 = None")
        if self.connector != ConnectorIdentity(*EXPECTED_CONNECTOR_IDENTITY):
            raise ValueError("connector must match the frozen XUNPU FPC-05F-24PH20 identity")
        if self.cable != CableContract(*EXPECTED_CABLE_GEOMETRY):
            raise ValueError("cable must match the frozen keyboard-side FFC geometry")
        if self.prohibited_nets != PROHIBITED_NETS:
            raise ValueError("prohibited_nets must match the frozen FFC prohibited-net set")
        if self.signal_nets & self.prohibited_nets:
            raise ValueError("FFC signal set includes a prohibited net")

    def pin(self, number: int) -> InterconnectPin:
        if not 1 <= number <= PIN_COUNT:
            raise ValueError(f"pin number outside 1..24: {number}")
        return self.pins[number - 1]

    @property
    def signal_nets(self) -> frozenset[str]:
        return frozenset(
            pin.net_name
            for pin in self.pins
            if pin.net_name not in {None, "GND"}
        )

    @property
    def ground_pins(self) -> frozenset[int]:
        return frozenset(pin.number for pin in self.pins if pin.net_name == "GND")

    @property
    def no_connect_pins(self) -> frozenset[int]:
        return frozenset(pin.number for pin in self.pins if pin.is_no_connect)


def reversed_pin_number(pin: int) -> int:
    if not 1 <= pin <= PIN_COUNT:
        raise ValueError(f"pin number outside 1..24: {pin}")
    return PIN_COUNT + 1 - pin


@lru_cache(maxsize=1)
def interboard_contract() -> InterboardContract:
    return InterboardContract(
        connector=ConnectorIdentity(
            manufacturer="XUNPU",
            mpn="FPC-05F-24PH20",
            lcsc_part="C2856805",
            datasheet_url=DATASHEET_URL,
        ),
        pins=tuple(
            InterconnectPin(number=index, net_name=net_name)
            for index, net_name in enumerate(PIN_NETS, start=1)
        ),
        prohibited_nets=PROHIBITED_NETS,
        cable=CableContract(
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
