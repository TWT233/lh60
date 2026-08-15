from __future__ import annotations

from dataclasses import dataclass, replace
from functools import lru_cache
from itertools import product
from math import hypot, sqrt
from typing import Iterable, Sequence

from shapely import affinity
from shapely.geometry import Point, box
from shapely.ops import unary_union

from tools.lh60_design.socket_geometry import (
    FootprintSpec,
    PadSpec,
    build_footprint_specs,
    choc_v1_pads_rotated_180,
    choc_v1_v2_pads,
    gateron_pads,
)
from tools.lh60_design.socket_library import (
    choc_physical_geometry,
    gateron_physical_geometry,
)


ROTATIONS_DEG = (0, 90, 180, 270)
MIN_COPPER_CLEARANCE_MM = 0.25
MIN_HOLE_EDGE_CLEARANCE_MM = 0.45
TARGET_HOLE_EDGE_CLEARANCE_MM = 0.50
MIN_COURTYARD_CLEARANCE_MM = 0.0
NO_PAIR_CLEARANCE_MM = 1_000_000.0


@dataclass(frozen=True)
class RegionPlacement:
    socket_ref: str
    footprint: str
    center_x_mm: float
    center_y_mm: float
    logical_node_id: str
    rotation_deg: int = 0
    allowed_rotations_deg: tuple[int, ...] = ROTATIONS_DEG

    def to_dict(self) -> dict[str, object]:
        return {
            "socket_ref": self.socket_ref,
            "footprint": self.footprint,
            "center_x_mm": self.center_x_mm,
            "center_y_mm": self.center_y_mm,
            "rotation_deg": self.rotation_deg,
            "logical_node_id": self.logical_node_id,
        }


@dataclass(frozen=True)
class RegionSpec:
    region: str
    placements: tuple[RegionPlacement, ...]


@dataclass(frozen=True)
class PairMeasurement:
    domain: str
    items: tuple[str, str]
    actual_mm: float


@dataclass(frozen=True)
class ClearanceReport:
    minimum_copper_clearance_mm: float
    minimum_hole_edge_clearance_mm: float
    minimum_courtyard_clearance_mm: float
    closest_copper_pair: tuple[str, str] | None
    closest_hole_pair: tuple[str, str] | None
    closest_courtyard_pair: tuple[str, str] | None
    measurements: tuple[PairMeasurement, ...]


@dataclass(frozen=True)
class BlockingConflict:
    domain: str
    items: tuple[str, str]
    actual_mm: float
    required_mm: float
    shortfall_mm: float

    def to_dict(self) -> dict[str, object]:
        return {
            "domain": self.domain,
            "items": list(self.items),
            "actual_mm": self.actual_mm,
            "required_mm": self.required_mm,
            "shortfall_mm": self.shortfall_mm,
        }


@dataclass(frozen=True)
class RegionReport:
    region: str
    solved: bool
    placements: tuple[RegionPlacement, ...]
    minimum_copper_clearance_mm: float
    minimum_hole_edge_clearance_mm: float
    minimum_courtyard_clearance_mm: float
    hole_edge_target_met: bool
    drc_status: str
    blocking_conflicts: tuple[BlockingConflict, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "region": self.region,
            "solved": self.solved,
            "placements": [placement.to_dict() for placement in self.placements],
            "minimum_copper_clearance_mm": self.minimum_copper_clearance_mm,
            "minimum_hole_edge_clearance_mm": self.minimum_hole_edge_clearance_mm,
            "minimum_courtyard_clearance_mm": self.minimum_courtyard_clearance_mm,
            "hole_edge_target_met": self.hole_edge_target_met,
            "drc_status": self.drc_status,
            "blocking_conflicts": [
                conflict.to_dict() for conflict in self.blocking_conflicts
            ],
        }


@dataclass(frozen=True)
class _PlacedGeometry:
    placement: RegionPlacement
    copper: object
    holes: tuple[tuple[str, float, float, float], ...]
    courtyard: object


def enumerate_rotations(
    socket_refs: Sequence[str],
    allowed_rotations: dict[str, Sequence[int]] | None = None,
) -> tuple[tuple[tuple[str, int], ...], ...]:
    refs = tuple(socket_refs)
    if len(refs) != len(set(refs)):
        raise ValueError("duplicate socket_ref in rotation enumeration")
    choices = []
    for socket_ref in refs:
        rotations = tuple(
            allowed_rotations.get(socket_ref, ROTATIONS_DEG)
            if allowed_rotations
            else ROTATIONS_DEG
        )
        _validate_rotations(rotations)
        choices.append(rotations)
    return tuple(
        tuple(zip(refs, rotations, strict=True))
        for rotations in product(*choices)
    )


def _validate_rotations(rotations: Sequence[int]) -> None:
    if not rotations:
        raise ValueError("allowed_rotations_deg cannot be empty")
    if len(rotations) != len(set(rotations)):
        raise ValueError("allowed_rotations_deg contains duplicates")
    invalid = set(rotations) - set(ROTATIONS_DEG)
    if invalid:
        raise ValueError(f"unsupported rotations: {sorted(invalid)}")


def _pad_geometry(pad: PadSpec):
    if pad.shape == "circle":
        return Point(pad.x, pad.y).buffer(pad.width / 2, quad_segs=24)
    geometry = box(
        pad.x - pad.width / 2,
        pad.y - pad.height / 2,
        pad.x + pad.width / 2,
        pad.y + pad.height / 2,
    )
    if pad.rotation:
        geometry = affinity.rotate(
            geometry,
            -pad.rotation,
            origin=(pad.x, pad.y),
        )
    return geometry


def _copper_geometry(pads: Iterable[PadSpec]):
    copper = [
        _pad_geometry(pad)
        for pad in pads
        if pad.pad_type != "np_thru_hole"
        and any("Cu" in layer for layer in pad.layers)
    ]
    return unary_union(copper)


def _land_pattern(pads: Iterable[PadSpec]):
    return unary_union([_pad_geometry(pad) for pad in pads])


def _courtyard_geometry(spec: FootprintSpec):
    gateron = unary_union(
        [gateron_physical_geometry(), _land_pattern(gateron_pads())]
    ).buffer(
        spec.courtyard_clearance_mm,
        quad_segs=8,
        join_style="round",
    )
    choc = unary_union(
        [choc_physical_geometry(), _land_pattern(choc_v1_v2_pads())]
    ).buffer(
        spec.courtyard_clearance_mm,
        quad_segs=8,
        join_style="round",
    )
    if spec.series == "Gateron-LP":
        return gateron
    if spec.series == "Kailh-Choc-V1V2":
        return choc
    rotated_choc_body = affinity.rotate(
        choc_physical_geometry(),
        180,
        origin=(0, 0),
    )
    rotated_choc = unary_union(
        [rotated_choc_body, _land_pattern(choc_v1_pads_rotated_180())]
    ).buffer(
        spec.courtyard_clearance_mm,
        quad_segs=8,
        join_style="round",
    )
    return unary_union([gateron, rotated_choc])


def _transform_geometry(geometry, placement: RegionPlacement):
    rotated = affinity.rotate(
        geometry,
        -placement.rotation_deg,
        origin=(0, 0),
    )
    return affinity.translate(
        rotated,
        xoff=placement.center_x_mm,
        yoff=placement.center_y_mm,
    )


def _transform_point(
    x: float,
    y: float,
    placement: RegionPlacement,
) -> tuple[float, float]:
    angle = placement.rotation_deg % 360
    if angle == 0:
        rotated_x, rotated_y = x, y
    elif angle == 90:
        rotated_x, rotated_y = y, -x
    elif angle == 180:
        rotated_x, rotated_y = -x, -y
    elif angle == 270:
        rotated_x, rotated_y = -y, x
    else:
        raise ValueError(f"unsupported rotation: {angle}")
    return (
        rotated_x + placement.center_x_mm,
        rotated_y + placement.center_y_mm,
    )


@lru_cache(maxsize=1)
def _footprint_specs() -> dict[str, FootprintSpec]:
    return {spec.name: spec for spec in build_footprint_specs()}


@lru_cache(maxsize=None)
def _placed_geometry(placement: RegionPlacement) -> _PlacedGeometry:
    spec = _footprint_specs()[placement.footprint]
    holes = []
    for index, pad in enumerate(spec.pads):
        if pad.drill is None:
            continue
        x, y = _transform_point(pad.x, pad.y, placement)
        label = pad.number or f"NPTH{index + 1}"
        holes.append(
            (
                f"{placement.socket_ref}:pad-{label}:hole",
                x,
                y,
                pad.drill / 2,
            )
        )
    return _PlacedGeometry(
        placement=placement,
        copper=_transform_geometry(_copper_geometry(spec.pads), placement),
        holes=tuple(holes),
        courtyard=_transform_geometry(_courtyard_geometry(spec), placement),
    )


def _overlap_aware_distance(left, right) -> float:
    intersection = left.intersection(right)
    if intersection.area > 1e-9:
        return -sqrt(intersection.area)
    return left.distance(right)


def _minimum_measurement(
    measurements: Sequence[PairMeasurement],
    domain: str,
) -> tuple[float, tuple[str, str] | None]:
    candidates = [
        measurement
        for measurement in measurements
        if measurement.domain == domain
    ]
    if not candidates:
        return NO_PAIR_CLEARANCE_MM, None
    closest = min(
        candidates,
        key=lambda measurement: (measurement.actual_mm, measurement.items),
    )
    return closest.actual_mm, closest.items


@lru_cache(maxsize=None)
def _pair_measurements(
    left_placement: RegionPlacement,
    right_placement: RegionPlacement,
) -> tuple[PairMeasurement, ...]:
    left = _placed_geometry(left_placement)
    right = _placed_geometry(right_placement)
    placement_pair = (
        left.placement.socket_ref,
        right.placement.socket_ref,
    )
    measurements = [
        PairMeasurement(
            domain="copper",
            items=placement_pair,
            actual_mm=left.copper.distance(right.copper),
        ),
        PairMeasurement(
            domain="courtyard",
            items=placement_pair,
            actual_mm=_overlap_aware_distance(
                left.courtyard,
                right.courtyard,
            ),
        ),
    ]
    measurements.extend(
        PairMeasurement(
            domain="hole_edge",
            items=(left_hole[0], right_hole[0]),
            actual_mm=(
                hypot(
                    right_hole[1] - left_hole[1],
                    right_hole[2] - left_hole[2],
                )
                - left_hole[3]
                - right_hole[3]
            ),
        )
        for left_hole in left.holes
        for right_hole in right.holes
    )
    return tuple(measurements)


def measure_clearances(
    placements: Sequence[RegionPlacement],
) -> ClearanceReport:
    footprint_specs = _footprint_specs()
    unknown = sorted(
        {
            placement.footprint
            for placement in placements
            if placement.footprint not in footprint_specs
        }
    )
    if unknown:
        raise ValueError(f"unknown footprint: {', '.join(unknown)}")
    measurements = []
    placements = tuple(placements)
    for left_index, left in enumerate(placements):
        for right in placements[left_index + 1 :]:
            measurements.extend(_pair_measurements(left, right))
    copper, copper_pair = _minimum_measurement(measurements, "copper")
    hole, hole_pair = _minimum_measurement(measurements, "hole_edge")
    courtyard, courtyard_pair = _minimum_measurement(
        measurements,
        "courtyard",
    )
    return ClearanceReport(
        minimum_copper_clearance_mm=copper,
        minimum_hole_edge_clearance_mm=hole,
        minimum_courtyard_clearance_mm=courtyard,
        closest_copper_pair=copper_pair,
        closest_hole_pair=hole_pair,
        closest_courtyard_pair=courtyard_pair,
        measurements=tuple(measurements),
    )


def _blocking_conflicts(
    clearance: ClearanceReport,
) -> tuple[BlockingConflict, ...]:
    requirements = {
        "copper": MIN_COPPER_CLEARANCE_MM,
        "hole_edge": MIN_HOLE_EDGE_CLEARANCE_MM,
        "courtyard": MIN_COURTYARD_CLEARANCE_MM,
    }
    conflicts = []
    for measurement in clearance.measurements:
        required = requirements[measurement.domain]
        if measurement.actual_mm + 1e-9 >= required:
            continue
        conflicts.append(
            BlockingConflict(
                domain=measurement.domain,
                items=measurement.items,
                actual_mm=measurement.actual_mm,
                required_mm=required,
                shortfall_mm=required - measurement.actual_mm,
            )
        )
    return tuple(
        sorted(
            conflicts,
            key=lambda conflict: (
                conflict.domain,
                conflict.actual_mm,
                conflict.items,
            ),
        )
    )


def _candidate_score(
    clearance: ClearanceReport,
    conflicts: Sequence[BlockingConflict],
    rotations: tuple[int, ...],
) -> tuple[object, ...]:
    solved = not conflicts
    target_met = (
        clearance.minimum_hole_edge_clearance_mm
        >= TARGET_HOLE_EDGE_CLEARANCE_MM
    )
    return (
        solved,
        target_met,
        -len(conflicts),
        clearance.minimum_hole_edge_clearance_mm,
        clearance.minimum_copper_clearance_mm,
        clearance.minimum_courtyard_clearance_mm,
        tuple(-rotation for rotation in rotations),
    )


def _validate_region(region: RegionSpec) -> None:
    if not region.region:
        raise ValueError("region name cannot be empty")
    if not region.placements:
        raise ValueError("region must contain at least one placement")
    refs = [placement.socket_ref for placement in region.placements]
    if len(refs) != len(set(refs)):
        raise ValueError("duplicate socket_ref in region")
    footprint_specs = _footprint_specs()
    for placement in region.placements:
        if placement.footprint not in footprint_specs:
            raise ValueError(f"unknown footprint: {placement.footprint}")
        _validate_rotations(placement.allowed_rotations_deg)


def solve_region(region: RegionSpec) -> RegionReport:
    _validate_region(region)
    refs = tuple(placement.socket_ref for placement in region.placements)
    allowed = {
        placement.socket_ref: placement.allowed_rotations_deg
        for placement in region.placements
    }
    rotation_candidates = enumerate_rotations(refs, allowed)

    best = None
    for candidate in rotation_candidates:
        rotations_by_ref = dict(candidate)
        placements = tuple(
            replace(
                placement,
                rotation_deg=rotations_by_ref[placement.socket_ref],
            )
            for placement in region.placements
        )
        clearance = measure_clearances(placements)
        conflicts = _blocking_conflicts(clearance)
        rotations = tuple(placement.rotation_deg for placement in placements)
        score = _candidate_score(clearance, conflicts, rotations)
        if best is None or score > best[0]:
            best = (score, placements, clearance, conflicts)

    if best is None:
        raise ValueError("region must contain at least one placement")
    _, placements, clearance, conflicts = best
    solved = not conflicts
    return RegionReport(
        region=region.region,
        solved=solved,
        placements=placements,
        minimum_copper_clearance_mm=clearance.minimum_copper_clearance_mm,
        minimum_hole_edge_clearance_mm=(
            clearance.minimum_hole_edge_clearance_mm
        ),
        minimum_courtyard_clearance_mm=(
            clearance.minimum_courtyard_clearance_mm
        ),
        hole_edge_target_met=(
            clearance.minimum_hole_edge_clearance_mm
            >= TARGET_HOLE_EDGE_CLEARANCE_MM
        ),
        drc_status="geometry-pass" if solved else "blocked",
        blocking_conflicts=conflicts,
    )
