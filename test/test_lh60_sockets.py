from __future__ import annotations

import collections
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LIBRARY = ROOT / "lib" / "lh60-sockets"
DUAL_NAME = "Gateron-LP-or-ChocV1-Hotswap-Socket-1U"
GATERON_NAMES = (
    "Gateron-LP-Hotswap-Socket-1U",
    "Gateron-LP-Hotswap-Socket-1.25U",
    "Gateron-LP-Hotswap-Socket-1.5U",
    "Gateron-LP-Hotswap-Socket-1.75U",
    "Gateron-LP-Hotswap-Socket-2U",
    "Gateron-LP-Hotswap-Socket-2.25U",
    "Gateron-LP-Hotswap-Socket-2.75U",
)
ALL_NAMES = (*GATERON_NAMES, DUAL_NAME)
GRAPHIC_TAGS = ("fp_line", "fp_arc", "fp_rect", "fp_circle", "fp_poly")
KICAD_CLI = os.environ.get("KICAD_CLI") or shutil.which("kicad-cli")


def footprint_path(name: str) -> Path:
    return LIBRARY / f"{name}.kicad_mod"


def footprints() -> tuple[Path, ...]:
    return tuple(footprint_path(name) for name in ALL_NAMES)


def extract_blocks(source: str, tag: str) -> list[str]:
    blocks: list[str] = []
    start = 0
    marker = f"({tag}"
    while True:
        block_start = source.find(marker, start)
        if block_start < 0:
            return blocks

        depth = 0
        in_string = False
        escaped = False
        for index in range(block_start, len(source)):
            char = source[index]
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
                continue
            if char == '"':
                in_string = True
            elif char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                if depth == 0:
                    blocks.append(source[block_start : index + 1])
                    start = index + 1
                    break
        else:
            raise AssertionError(f"unbalanced ({tag} block")


def pad_number(block: str) -> str:
    match = re.match(r'\(pad\s+(?:"([^"]*)"|([^\s)]+))', block)
    if not match:
        raise AssertionError(f"cannot parse pad number from {block[:80]!r}")
    return match.group(1) if match.group(1) is not None else match.group(2)


def named_pad_numbers(source: str) -> list[str]:
    return [
        number
        for block in extract_blocks(source, "pad")
        if (number := pad_number(block))
    ]


def pad_signature(source: str) -> tuple[str, ...]:
    return tuple(
        re.sub(r"\s+", " ", block).strip() for block in extract_blocks(source, "pad")
    )


def graphic_blocks(source: str, layer: str) -> list[str]:
    blocks: list[str] = []
    for tag in GRAPHIC_TAGS:
        for block in extract_blocks(source, tag):
            if re.search(rf'\(layer\s+"?{re.escape(layer)}"?\)', block):
                blocks.append(block)
    return blocks


def points_from_graphic(block: str) -> list[tuple[float, float]]:
    points: list[tuple[float, float]] = []
    for match in re.finditer(
        r"\((?:start|mid|end|center|xy)\s+"
        r"(-?\d+(?:\.\d+)?)\s+(-?\d+(?:\.\d+)?)\)",
        block,
    ):
        points.append((float(match.group(1)), float(match.group(2))))
    return points


def graphics_bbox(blocks: list[str]) -> tuple[float, float, float, float]:
    points = [point for block in blocks for point in points_from_graphic(block)]
    if not points:
        raise AssertionError("no graphic points found")
    xs, ys = zip(*points, strict=True)
    return min(xs), min(ys), max(xs), max(ys)


def model_paths(source: str) -> list[str]:
    paths: list[str] = []
    for block in extract_blocks(source, "model"):
        match = re.match(r'\(model\s+"([^"]+)"', block)
        if match:
            paths.append(match.group(1))
    return paths


def attr_tokens(source: str) -> set[str]:
    blocks = extract_blocks(source, "attr")
    if not blocks:
        return set()
    return set(blocks[0][len("(attr") : -1].split())


def run_kicad_cli(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    if not KICAD_CLI:
        raise unittest.SkipTest("kicad-cli is not available")
    result = subprocess.run(
        [KICAD_CLI, *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if check and result.returncode:
        raise AssertionError(
            f"kicad-cli {' '.join(args)} failed ({result.returncode})\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    return result


class SocketLibraryInventoryTest(unittest.TestCase):
    def test_contains_exactly_the_eight_canonical_footprints(self) -> None:
        self.assertEqual(
            sorted(path.stem for path in LIBRARY.glob("*.kicad_mod")),
            sorted(ALL_NAMES),
        )

    def test_all_footprints_parse_and_export_with_kicad_10(self) -> None:
        with tempfile.TemporaryDirectory() as output:
            run_kicad_cli("fp", "export", "svg", "--output", output, str(LIBRARY))
            self.assertEqual(len(list(Path(output).glob("*.svg"))), len(ALL_NAMES))


class SocketElectricalContractTest(unittest.TestCase):
    def test_dual_socket_uses_only_logical_pad_numbers_one_and_two(self) -> None:
        source = footprint_path(DUAL_NAME).read_text(encoding="utf-8")
        numbers = named_pad_numbers(source)
        self.assertEqual(set(numbers), {"1", "2"})
        self.assertEqual(collections.Counter(numbers), {"1": 6, "2": 6})

    def test_gateron_variants_have_identical_pad_stacks(self) -> None:
        signatures = {
            name: pad_signature(footprint_path(name).read_text(encoding="utf-8"))
            for name in GATERON_NAMES
        }
        baseline = signatures[GATERON_NAMES[0]]
        for name, signature in signatures.items():
            with self.subTest(name=name):
                self.assertEqual(signature, baseline)


class SocketMechanicalContractTest(unittest.TestCase):
    def test_keycap_envelopes_are_user_drawings_not_production_silkscreen(self) -> None:
        for path in footprints():
            source = path.read_text(encoding="utf-8")
            with self.subTest(footprint=path.stem):
                self.assertEqual(graphic_blocks(source, "F.SilkS"), [])
                drawings = graphic_blocks(source, "Dwgs.User")
                self.assertEqual(len(drawings), 1)
                self.assertTrue(drawings[0].startswith("(fp_rect"))

    def test_each_footprint_has_bottom_fabrication_geometry(self) -> None:
        for path in footprints():
            with self.subTest(footprint=path.stem):
                source = path.read_text(encoding="utf-8")
                self.assertGreaterEqual(len(graphic_blocks(source, "B.Fab")), 1)

    def test_courtyards_cover_socket_bodies_and_complete_land_patterns(self) -> None:
        for name in GATERON_NAMES:
            source = footprint_path(name).read_text(encoding="utf-8")
            blocks = graphic_blocks(source, "B.CrtYd")
            with self.subTest(footprint=name):
                self.assertEqual(len(blocks), 1)
                self.assertEqual(
                    graphics_bbox(blocks),
                    (-9.575, 2.275, 7.775, 8.175),
                )

        source = footprint_path(DUAL_NAME).read_text(encoding="utf-8")
        blocks = graphic_blocks(source, "B.CrtYd")
        self.assertEqual(len(blocks), 2)
        self.assertEqual(
            graphics_bbox(blocks),
            (-9.575, -8.5, 10.25, 8.175),
        )

    def test_courtyard_graphics_use_standard_stroke_and_no_fill(self) -> None:
        for path in footprints():
            for block in graphic_blocks(
                path.read_text(encoding="utf-8"), "B.CrtYd"
            ):
                with self.subTest(footprint=path.stem):
                    self.assertRegex(block, r"\(stroke\s+\(width\s+0\.05\)")
                    self.assertIn("(fill none)", block)

    def test_socket_footprints_are_excluded_from_position_files(self) -> None:
        for path in footprints():
            with self.subTest(footprint=path.stem):
                source = path.read_text(encoding="utf-8")
                self.assertIn("exclude_from_pos_files", attr_tokens(source))
                self.assertNotIn("exclude_from_bom", attr_tokens(source))

    def test_3d_model_paths_exist(self) -> None:
        for path in footprints():
            source = path.read_text(encoding="utf-8")
            paths = model_paths(source)
            expected_count = 2 if path.stem == DUAL_NAME else 1
            with self.subTest(footprint=path.stem):
                self.assertEqual(len(paths), expected_count)
                for model_path in paths:
                    self.assertTrue(
                        (path.parent / model_path).resolve().is_file(),
                        model_path,
                    )


class SocketProjectIntegrationTest(unittest.TestCase):
    def test_project_footprint_libraries_are_portable(self) -> None:
        table = (ROOT / "test" / "fp-lib-table").read_text(encoding="utf-8")
        self.assertNotRegex(table, r"[A-Za-z]:[/\\]")
        self.assertNotIn(".worktrees", table)
        for relative_path in (
            "../lib/keysw-siderakb",
            "../lib/mxv2/Gateron_KS33_Hotswap.pretty",
            "../lib/lh60-sockets",
            "../lib/mxv2/Kailh_PG1353_Hotswap.pretty",
        ):
            self.assertIn(f"${{KIPRJMOD}}/{relative_path}", table)

    def test_clean_coupon_has_no_drc_violations(self) -> None:
        board = ROOT / "test" / "socket-clean.kicad_pcb"
        self.assertTrue(board.is_file())
        with tempfile.NamedTemporaryFile(suffix=".json") as report:
            run_kicad_cli(
                "pcb",
                "drc",
                "--format",
                "json",
                "--output",
                report.name,
                str(board),
            )
            result = json.loads(Path(report.name).read_text(encoding="utf-8"))
        self.assertEqual(result["violations"], [])
        self.assertEqual(result["unconnected_items"], [])

    def test_conflict_fixture_has_only_documented_violation_types(self) -> None:
        board = ROOT / "test" / "socket-conflicts.kicad_pcb"
        self.assertTrue(board.is_file())
        with tempfile.NamedTemporaryFile(suffix=".json") as report:
            run_kicad_cli(
                "pcb",
                "drc",
                "--format",
                "json",
                "--output",
                report.name,
                str(board),
            )
            result = json.loads(Path(report.name).read_text(encoding="utf-8"))
        actual_types = {violation["type"] for violation in result["violations"]}
        self.assertTrue(actual_types)
        self.assertLessEqual(
            actual_types,
            {
                "courtyards_overlap",
                "hole_clearance",
                "hole_to_hole",
                "shorting_items",
                "solder_mask_bridge",
            },
        )


if __name__ == "__main__":
    unittest.main()
