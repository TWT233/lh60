# Task 2 Report: U3 Exact C2856805 Project Library

## Scope

- Task branch/worktree: `task/mcu-tail-u3-library` at `.worktree/mcu-tail-ffc-u3/lh60`
- Integration branch/worktree: `integration/mcu-tail-ffc` at `.worktree/mcu-tail-ffc/lh60`
- Goal: create and audit the exact project-local KiCad symbol and footprint for XUNPU `FPC-05F-24PH20`, LCSC `C2856805`.
- Protected KiCad files were generated or modified through Konnect/KiCad-aware operations only.

## Implementation Summary

- Added `tools/lh60_design/interconnect_library.py`:
  - frozen symbol/footprint specs
  - Konnect payload builders
  - `apply_interconnect_library()` for library creation, project registration, and clearance-rule setup
- Added `tools/verify_interconnect_library.py`:
  - exact C2856805 symbol, footprint, graphics, metadata, payload, and rule-condition tests
  - regression for preserving two unnumbered mechanical hold-down pads
  - regression for replacing an already existing library symbol before re-apply
- Added `tools/check_interconnect_library_acceptance.py`:
  - live Konnect readback for symbol, footprint graphics, project registrations, and board rules
  - read-only parser for pad geometry because `get_footprint_info(include_graphics=true)` does not expose pad geometry/layers
  - KiCad SVG export proof for the generated footprint
- Added `lib/lh60-interconnect/README.md` documenting:
  - XUNPU `FPC-05F-24PH20`
  - LCSC `C2856805`
  - exact datasheet/product URLs
  - controlled geometry
  - no exact trusted STEP model
  - why FH12 is not a substitute
- Created through Konnect:
  - `lib/lh60-interconnect/lh60-interconnect.kicad_sym`
  - `lib/lh60-interconnect/lh60-interconnect.pretty/FPC-05F-24PH20.kicad_mod`
- Registered project libraries through Konnect:
  - `sym-lib-table`
  - `fp-lib-table`
- Configured the root board rule floor through Konnect:
  - `lh60.kicad_pro` Board Setup `min_clearance` changed from `0.25` to `0.20`
  - this is intentional and in scope because the 0.30 mm pads at 0.50 mm pitch need a 0.20 mm board-floor clearance
  - the general 0.25 mm clearance is restored by a custom rule in `lh60.kicad_dru`
- Added custom rule through Konnect:
  - name: `lh60-interconnect:C2856805-general-clearance`
  - constraint: `clearance`
  - minimum: `0.25 mm`
  - condition: `!(A.Type == 'Pad' && B.Type == 'Pad' && A.memberOfFootprint('FPC-05F-24PH20') && B.memberOfFootprint('FPC-05F-24PH20') && A.Reference == B.Reference)`

## RED Evidence

Initial test-first run:

```bash
PYTHONDONTWRITEBYTECODE=1 python -m unittest -v tools.verify_interconnect_library
```

Result:

- exit `1`
- expected failures were import errors for the missing implementation modules:
  - `tools.lh60_design.interconnect_library`
  - `tools.check_interconnect_library_acceptance`

## Exact Geometry Frozen

- Symbol:
  - reference prefix `J`
  - value `FPC-05F-24PH20`
  - datasheet set to the exact LCSC PDF
  - 24 passive sequential pins `1..24`
- Footprint:
  - 24 signal pads numbered `1..24`
  - signal centers: `x = -5.75 + index * 0.50`, `y = 0.00`
  - signal size: `0.30 x 1.25 mm`
  - two unnumbered mechanical hold-down lands at `(-7.44, 2.575)` and `(7.44, 2.575)`
  - hold-down size: `2.00 x 2.50 mm`
  - pad layers: `F.Cu`, `F.Paste`, `F.Mask`
  - body: `16.40 x 5.12 x 2.00 mm`
  - `F.Fab` rectangle: `x=-8.20..8.20`, `y=0.68..5.80`
  - `F.CrtYd` rectangle: `(-8.69, -0.875)` to `(8.69, 6.05)`, stroke `0.05`
  - mouth direction `+Y`
  - top-view pin 1 is the leftmost signal pad
  - no STEP model associated

## Live Acceptance Evidence

```bash
PYTHONDONTWRITEBYTECODE=1 python -m tools.lh60_design.interconnect_library --apply
PYTHONDONTWRITEBYTECODE=1 python tools/check_interconnect_library_acceptance.py
```

Result:

- apply completed through Konnect `0.11.0`
- symbol readback confirmed `FPC-05F-24PH20` with 24 passive sequential pins
- footprint readback confirmed:
  - `pad_count=26`
  - `has_3d_model=False`
  - `has_courtyard=True`
  - `graphic_count=8`
- pad parser confirmed 24 electrical pads plus 2 unnumbered mechanical lands
- project registrations confirmed portable `${KIPRJMOD}` URIs
- root board rules confirmed:
  - Board Setup `min_clearance=0.20`
  - custom rule restores `0.25 mm` general clearance outside same-footprint C2856805 pads
- KiCad SVG export produced:
  - `docs/reports/mcu-tail-ffc-u3-footprint-svg/FPC-05F-24PH20.svg`
- live acceptance passed

## Verification

Focused library suite:

```bash
PYTHONDONTWRITEBYTECODE=1 python -m unittest -v tools.verify_interconnect_library
```

Result:

- `11` tests run
- `11/11` passed

Focused interconnect suites:

```bash
PYTHONDONTWRITEBYTECODE=1 python -m unittest -v tools.verify_interconnect_contract tools.verify_interconnect_library
```

Result:

- `23` tests run
- `23/23` passed

Full Python regression:

```bash
PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s tools -p 'verify_*.py' -v
```

Result:

- `244` tests run
- `244/244` passed

Whitespace sanity:

```bash
git diff --check
```

Result:

- pass

Root board DRC artifact:

- path: `docs/reports/mcu-tail-ffc-u3-root-drc.json`
- summary from artifact:
  - `violations=163`
  - `unconnected_items=367`
  - `schematic_parity=0`
  - `errors=457`
  - `warnings=73`
- This is the known current root-board baseline. Task 2 does not place U3 on the board.

Task 0 real KiCad custom-rule coupon rerun:

```bash
cargo test --test e2e_kicad custom_rule_coupon_proves_board_floor_and_same_footprint_exception -- --ignored --nocapture
```

Result:

- `1` test run
- `1/1` passed

## Files Changed

- `.superpowers/sdd/2026-08-29-external-mcu-ffc-tail/task-2-report.md`
- `tools/lh60_design/interconnect_library.py`
- `tools/verify_interconnect_library.py`
- `tools/check_interconnect_library_acceptance.py`
- `lib/lh60-interconnect/README.md`
- `lib/lh60-interconnect/lh60-interconnect.kicad_sym`
- `lib/lh60-interconnect/lh60-interconnect.pretty/FPC-05F-24PH20.kicad_mod`
- `sym-lib-table`
- `fp-lib-table`
- `lh60.kicad_pro`
- `lh60.kicad_dru`
- `docs/reports/mcu-tail-ffc-u3-root-drc.json`
- `docs/reports/mcu-tail-ffc-u3-footprint-svg/FPC-05F-24PH20.svg`

## Concerns

- The Task 2 brief says to apply the rule to both projects, but the tail project is not created until Task 4. This task applied and read back the rule on the existing root project and encoded reusable apply logic for later use.
- Konnect `create_symbol` supports `datasheet` but does not currently preserve arbitrary library-symbol fields such as `Manufacturer`, `MPN`, or `LCSC`; those are frozen in Python specs/tests and README provenance instead.
- Konnect `get_footprint_info(include_graphics=true)` does not expose pad geometry or pad layers, so live acceptance supplements it with read-only parsing of the Konnect-written footprint file.
- Task 0 KiCad coupon proved `A.Reference == B.Reference` is the working same-footprint discriminator for pad-pair custom rules on KiCad 10. `A.Parent.Reference == B.Parent.Reference` was not used because it does not match that pad-pair case.
