from __future__ import annotations

from dataclasses import dataclass


U_SIZES = ("1U", "1.25U", "1.5U", "1.75U", "2U", "2.25U", "2.75U")
SERIES = ("Gateron-LP", "Kailh-Choc-V1V2", "Gateron-LP-or-ChocV1")
PITCH_MM = 19.05
COURTYARD_CLEARANCE_MM = 0.5

GATERON_MODEL = "../mxv2/Gateron_KS33_Hotswap.pretty/Gateron-KS33-Socket.step"
CHOC_MODEL = "../mxv2/Kailh_PG1353_Hotswap.pretty/Kailh-Choc-Socket-CPG135001S30.step"


@dataclass(frozen=True)
class PadSpec:
    number: str
    pad_type: str
    shape: str
    x: float
    y: float
    width: float
    height: float
    layers: tuple[str, ...]
    drill: float | None = None
    rotation: float = 0.0
    roundrect_rratio: float | None = None
    expands_courtyard: bool = True

    def signature(self) -> tuple[object, ...]:
        return (
            self.number,
            self.pad_type,
            self.shape,
            self.x,
            self.y,
            self.width,
            self.height,
            self.layers,
            self.drill,
            self.rotation,
            self.roundrect_rratio,
            self.expands_courtyard,
        )


@dataclass(frozen=True)
class ModelSpec:
    path: str
    offset: tuple[float, float, float]
    scale: tuple[float, float, float]
    rotate: tuple[float, float, float]


@dataclass(frozen=True)
class FootprintSpec:
    name: str
    series: str
    size: str
    pads: tuple[PadSpec, ...]
    models: tuple[ModelSpec, ...]
    keycap_width_mm: float
    keycap_height_mm: float = PITCH_MM
    courtyard_clearance_mm: float = COURTYARD_CLEARANCE_MM
    exclude_from_position_files: bool = True

    def series_signature(self) -> tuple[object, ...]:
        return (
            self.series,
            tuple(pad.signature() for pad in self.pads),
            self.models,
            self.keycap_height_mm,
            self.courtyard_clearance_mm,
            self.exclude_from_position_files,
        )


def _npth(
    x: float,
    y: float,
    diameter: float,
    *,
    layers: tuple[str, ...] = ("*.Cu", "*.Mask"),
    expands_courtyard: bool = True,
) -> PadSpec:
    return PadSpec(
        number="",
        pad_type="np_thru_hole",
        shape="circle",
        x=x,
        y=y,
        width=diameter,
        height=diameter,
        drill=diameter,
        layers=layers,
        expands_courtyard=expands_courtyard,
    )


def _pth(
    number: str,
    x: float,
    y: float,
    width: float,
    drill: float,
    *,
    layers: tuple[str, ...] = ("*.Cu", "B.Mask"),
) -> PadSpec:
    return PadSpec(
        number=number,
        pad_type="thru_hole",
        shape="circle",
        x=x,
        y=y,
        width=width,
        height=width,
        drill=drill,
        layers=layers,
    )


def _smd(
    number: str,
    shape: str,
    x: float,
    y: float,
    width: float,
    height: float,
    *,
    paste_and_mask: bool,
    rotation: float = 0.0,
) -> PadSpec:
    return PadSpec(
        number=number,
        pad_type="smd",
        shape=shape,
        x=x,
        y=y,
        width=width,
        height=height,
        layers=(
            ("B.Cu", "B.Paste", "B.Mask") if paste_and_mask else ("B.Cu",)
        ),
        rotation=rotation,
        roundrect_rratio=0.2 if shape == "roundrect" else None,
    )


def gateron_pads() -> tuple[PadSpec, ...]:
    return (
        _npth(
            0.0,
            0.0,
            5.25,
            layers=("*.Mask",),
            expands_courtyard=False,
        ),
        _smd("1", "roundrect", -8.075, 4.7, 2.5, 2.55, paste_and_mask=True),
        _smd("1", "rect", -6.35, 4.7, 3.9, 1.0, paste_and_mask=False),
        _pth("1", -4.4, 4.7, 4.0, 3.0),
        _pth("2", 2.6, 5.75, 4.0, 3.0),
        _smd("2", "rect", 4.475, 5.75, 3.75, 1.0, paste_and_mask=False),
        _smd("2", "roundrect", 6.275, 5.75, 2.5, 2.55, paste_and_mask=True),
    )


def choc_v1_pads_rotated_180() -> tuple[PadSpec, ...]:
    return (
        _npth(-5.5, 0.0, 1.7018),
        _npth(5.5, 0.0, 1.7018),
        _pth("1", 0.0, -5.9, 4.0, 3.0),
        _smd("1", "rect", -2.0, -5.9, 3.9, 1.0, paste_and_mask=False),
        _smd("1", "roundrect", -3.7, -5.9, 2.6, 2.6, paste_and_mask=True),
        _smd("2", "roundrect", 8.7, -3.8, 2.6, 2.6, paste_and_mask=True),
        _smd("2", "rect", 7.0, -3.8, 3.9, 1.0, paste_and_mask=False),
        _pth("2", 5.0, -3.8, 4.0, 3.0),
    )


def choc_v1_v2_pads() -> tuple[PadSpec, ...]:
    return (
        _npth(-5.5, 0.0, 1.7018),
        _npth(-5.0, 3.8, 3.0, layers=("*.Cu", "*.Mask")),
        _npth(
            0.0,
            0.0,
            5.0,
            layers=("*.Cu", "*.Mask"),
            expands_courtyard=False,
        ),
        _npth(0.0, 5.9, 3.0, layers=("*.Cu", "*.Mask")),
        _pth("", 5.0, -5.15, 1.65, 1.0),
        _npth(5.5, 0.0, 1.7018),
        _smd("1", "roundrect", 3.7, 5.9, 2.6, 2.6, paste_and_mask=True),
        _smd("2", "roundrect", -8.7, 3.8, 2.6, 2.6, paste_and_mask=True),
    )


def _gateron_model() -> ModelSpec:
    return ModelSpec(
        path=GATERON_MODEL,
        offset=(5.025, -7.925, -1.838),
        scale=(-1.0, 1.0, 1.0),
        rotate=(-90.0, 0.0, 0.0),
    )


def _choc_model() -> ModelSpec:
    return ModelSpec(
        path=CHOC_MODEL,
        offset=(0.0, 0.0, 0.0),
        scale=(-1.0, 1.0, 1.0),
        rotate=(90.0, 0.0, 0.0),
    )


def _series_contract(
    series: str,
) -> tuple[tuple[PadSpec, ...], tuple[ModelSpec, ...]]:
    if series == "Gateron-LP":
        return gateron_pads(), (_gateron_model(),)
    if series == "Kailh-Choc-V1V2":
        return choc_v1_v2_pads(), (_choc_model(),)
    if series == "Gateron-LP-or-ChocV1":
        return (
            (*gateron_pads(), *choc_v1_pads_rotated_180()),
            (_gateron_model(), _choc_model()),
        )
    raise ValueError(f"unknown socket series: {series}")


def _u_value(size: str) -> float:
    return float(size.removesuffix("U"))


def build_footprint_specs() -> tuple[FootprintSpec, ...]:
    specs: list[FootprintSpec] = []
    for series in SERIES:
        pads, models = _series_contract(series)
        for size in U_SIZES:
            specs.append(
                FootprintSpec(
                    name=f"{series}-Hotswap-Socket-{size}",
                    series=series,
                    size=size,
                    pads=pads,
                    models=models,
                    keycap_width_mm=_u_value(size) * PITCH_MM,
                )
            )
    return tuple(specs)
