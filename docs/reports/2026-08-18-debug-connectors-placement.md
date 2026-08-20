# LH60 Debug Connectors Placement Report

## Scope

This report records the production placement evidence for the accepted debug
connector footprint mapping on commit `97b30f0c223d8d77df9562c87ef0045fc67596db`.
It is a production-evidence report, not a fabrication release note.

Evidence source:

- one-off production provenance root: `/data00/home/wangqiyilang/.cache/r3-identity-rebind/l6-production.PN3Aga`
- worktree commit under report: `97b30f0c223d8d77df9562c87ef0045fc67596db`

## Status

The placement evidence is production-derived, but the board is not fabrication
ready.

- routing status: un-routed debug connectors
- DRC status: `163` violations remain after the placement run
- unconnected status: `367` remain
- parity status: `0`
- delta from pre-fix library mismatch run: `169/367/0 -> 163/367/0`
- save count: `1`
- conclusion: placement verified, non-fab-ready

## Placement Summary

All six debug connectors were placed on `B.Cu` with the intended access
envelope and pin-1 readability preserved from the back assembly view. The
placement evidence to preserve here is:

- layer: `B.Cu`
- pin 1 orientation: preserved and readable for every connector
- extraction target: `15 mm`
- nearest `B.CrtYd` net clearance snapshots:
  - `J1`: about `1.243 mm`
  - `J2`: about `3.774 mm`
  - `J3`: about `2.361 mm`
  - `J4`: about `2.07 mm`
  - `J5`: about `2.08 mm`
  - `J6`: about `2.499 mm`

## Connector Table

The production handoff must retain one row per connector pin with:

- connector reference
- pin number
- logical net
- placed `x`
- placed `y`
- placed rotation
- side `B.Cu`
- access envelope
- pin-1 orientation
- `15 mm` extraction note

Populate the table below from the production evidence directory instead of any
temporary shell transcript. This report intentionally keeps the delivery
surface stable and path-based.

| Ref | Pin | Net | X (mm) | Y (mm) | Rot (deg) | Layer | Access Envelope | Pin 1 | 15 mm Extraction |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| J1 | 1 | VSYS | 282.50 | 36.00 | 0.0 | B.Cu | `Rect(280.23, 28.65, 284.77, 38.27)` | readable | yes |
| J1 | 2 | 3V3 | 282.50 | 33.46 | 0.0 | B.Cu | `Rect(280.23, 28.65, 284.77, 38.27)` | readable | yes |
| J1 | 3 | GND | 282.50 | 30.92 | 0.0 | B.Cu | `Rect(280.23, 28.65, 284.77, 38.27)` | readable | yes |
| J2 | 1 | COL0 | 77.50 | 92.00 | 0.0 | B.Cu | `Rect(75.23, 79.57, 79.77, 94.27)` | readable | yes |
| J2 | 2 | COL1 | 77.50 | 89.46 | 0.0 | B.Cu | `Rect(75.23, 79.57, 79.77, 94.27)` | readable | yes |
| J2 | 3 | COL2 | 77.50 | 86.92 | 0.0 | B.Cu | `Rect(75.23, 79.57, 79.77, 94.27)` | readable | yes |
| J2 | 4 | COL3 | 77.50 | 84.38 | 0.0 | B.Cu | `Rect(75.23, 79.57, 79.77, 94.27)` | readable | yes |
| J2 | 5 | COL4 | 77.50 | 81.84 | 0.0 | B.Cu | `Rect(75.23, 79.57, 79.77, 94.27)` | readable | yes |
| J3 | 1 | COL5 | 107.50 | 92.00 | 0.0 | B.Cu | `Rect(105.23, 79.57, 109.77, 94.27)` | readable | yes |
| J3 | 2 | COL6 | 107.50 | 89.46 | 0.0 | B.Cu | `Rect(105.23, 79.57, 109.77, 94.27)` | readable | yes |
| J3 | 3 | COL7 | 107.50 | 86.92 | 0.0 | B.Cu | `Rect(105.23, 79.57, 109.77, 94.27)` | readable | yes |
| J3 | 4 | COL8 | 107.50 | 84.38 | 0.0 | B.Cu | `Rect(105.23, 79.57, 109.77, 94.27)` | readable | yes |
| J3 | 5 | COL9 | 107.50 | 81.84 | 0.0 | B.Cu | `Rect(105.23, 79.57, 109.77, 94.27)` | readable | yes |
| J4 | 1 | ROW0 | 3.00 | 49.50 | 0.0 | B.Cu | `Rect(0.73, 39.61, 5.27, 51.77)` | readable | yes |
| J4 | 2 | ROW1 | 3.00 | 46.96 | 0.0 | B.Cu | `Rect(0.73, 39.61, 5.27, 51.77)` | readable | yes |
| J4 | 3 | ROW2 | 3.00 | 44.42 | 0.0 | B.Cu | `Rect(0.73, 39.61, 5.27, 51.77)` | readable | yes |
| J4 | 4 | ROW3 | 3.00 | 41.88 | 0.0 | B.Cu | `Rect(0.73, 39.61, 5.27, 51.77)` | readable | yes |
| J5 | 1 | ROW4 | 3.00 | 55.50 | 180.0 | B.Cu | `Rect(0.73, 53.23, 5.27, 62.85)` | readable | yes |
| J5 | 2 | ROW5 | 3.00 | 58.04 | 180.0 | B.Cu | `Rect(0.73, 53.23, 5.27, 62.85)` | readable | yes |
| J5 | 3 | ROW6 | 3.00 | 60.58 | 180.0 | B.Cu | `Rect(0.73, 53.23, 5.27, 62.85)` | readable | yes |
| J6 | 1 | GP27 | 282.50 | 42.00 | 180.0 | B.Cu | `Rect(280.23, 39.73, 284.77, 49.35)` | readable | yes |
| J6 | 2 | GP28 | 282.50 | 44.54 | 180.0 | B.Cu | `Rect(280.23, 39.73, 284.77, 49.35)` | readable | yes |
| J6 | 3 | GP29 | 282.50 | 47.08 | 180.0 | B.Cu | `Rect(280.23, 39.73, 284.77, 49.35)` | readable | yes |

## Evidence Digests

Recorded digests and identity points from the production run:

- schematic SHA: `5322b7f21c10854aef14f7ca92ac35353f9fb9b7abd215451b4b4678a41aa1ac`
- PCB SHA: `eb27463ebcb973e44b5aea551c79ac4470615a3a7f0519a4b1c54c2afd466a46`
- PnP exclusion for `J*`: SHA `20aa7bffd369060734beccd919354af74fa7555bed3f5b6b2f389d40935b7300`
- SVG render digest: `51802cc4fa2521cccc8fb52405093b4f4a61b443fd52c25f333cfd39da4a1fac`
- PNG render digest: `b43bbaecfd06f2d14a7a9103c9d0627e5a0a23dd285b0b2f9801b761f3df07af`
- production evidence save count: `1`

## Toolchain Provenance

Konnect changes deployed for the production placement evidence:

- source commits:
  - `7c35a91`
  - `3e73a40`
  - `c3098c1`
  - `136b969`
- deployed binary digest: `ff931a373e205402950a209596ab96958da837393dd84cfd9effcdc499daa0e3`

## Reproducible Gates

The delivery artifact is this repo-local report plus the repo-local checker
entrypoint. The cache directory above is historical provenance from one
production run, not the long-term delivery surface.

Canonical rerun contract for this report family, once the acceptance checker
unit merges into the repository:

```bash
# Preconditions:
# 1. KiCad must be running with the target production board open.
# 2. The Konnect IPC socket must be reachable from the deployed binary.
# 3. The checker writes fresh evidence paths chosen by the operator; those
#    outputs become the new run artifacts, not this historical cache path.
PYTHONDONTWRITEBYTECODE=1 python tools/check_pcb_acceptance.py \
  --production \
  --output docs/reports/2026-08-18-debug-connectors-placement.json \
  --svg docs/reports/2026-08-18-debug-connectors-placement.svg \
  --positions docs/reports/2026-08-18-debug-connectors-placement.csv
python -m compileall -q tools
git diff --check
```

This report preserves `save_count == 1` as immutable historical production
evidence from the run rooted at
`/data00/home/wangqiyilang/.cache/r3-identity-rebind/l6-production.PN3Aga`.
A read-only checker rerun is expected to validate placement, hashes, digests,
and exported tables, but it does not retroactively reproduce that original
write count.

Historical provenance for the recorded production run should still be verified
against:

- the one-off provenance root
- the reported worktree commit
- `readback.json` for connector coordinates, layer, pad nets, and final DRC tuple
- `closed-placement.json` for placement transform summary
- `acceptance-summary.json` for rendered digests, PnP exclusion digest, and `-6` library-mismatch delta
- `positions.csv` to confirm no `J1..J6` rows are emitted in PnP output
- `back.svg` and `back.png` as the rendered back-side review artifacts
- the recorded schematic and PCB hashes
- the historical `save_count == 1` assertion
- the post-run DRC tuple `163/367/0`
- the nearest `B.CrtYd` clearance snapshots
- the connector pin table above

## Risks

- The board remains non-fab-ready because the production placement still has
  `163` DRC violations and `367` unconnected items.
- Connector placement evidence is valid for access and orientation, but not for
  a released manufacturing package.
- Any future rerun must preserve the same evidence roots and update this report
  additively instead of substituting a transient path.
