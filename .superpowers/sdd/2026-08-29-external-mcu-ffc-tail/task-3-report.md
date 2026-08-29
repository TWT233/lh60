# Task 3 Report: U4 Main Schematic Migration

## Result

Task 3 is complete. The main LH60 schematic was migrated from the active-MCU baseline to the passive external-MCU FFC-tail plan.

The production schematic now contains:

- `J1`: one `lh60-interconnect:FPC-05F-24PH20` connector at `(360.68, 76.2)`.
- Matrix inventory: 70 diodes and 75 switches.
- No MCU, debug headers, test points, or power flags on the main board schematic.
- A3 landscape presentation with matrix labels and the approved J1 position.

Task 4 was not implemented. The main board is the final product for this repository.

## Branches

- Task branch: `task/mcu-tail-u4-main-schematic`
- Task final commit: `d02373e feat: migrate main schematic to passive ffc`
- Integration branch: `integration/mcu-tail-ffc`
- Integration merge commit: `d743796 Merge branch 'task/mcu-tail-u4-main-schematic' into integration/mcu-tail-ffc`

## Production Transaction

Production mutation was performed through Konnect only. No direct text edit was used for `lh60.kicad_sch` or `lh60.kicad_pcb`.

The first production transaction passed the evidence, capability, clean-tree, no-writer, and predelete hash gates, then completed the Konnect delete phase. It stopped before apply because the empty-layout response omitted `no_connect_count`; the guard expected that key directly. I fixed the guard to backfill the no-connect count from the schematic when absent, added a regression test, and resumed by applying the approved schematic plan through Konnect.

The production transaction evidence is:

- `.superpowers/sdd/2026-08-29-external-mcu-ffc-tail/evidence/task-3-20260829-151741/production-transaction.json`
- SHA256: `bb064c386183d43f07bfa447120bb41d37913dbe3aca16bbc2b045a312d3eb89`

## Visual Approval Evidence

Approved candidate: `163324-fresh`

- Approved candidate schematic SHA256: `75b606104dab5fd10c04ee16c1f6e3efb4ac18985b39dde0da7a5323f3f2108d`
- Approved SVG SHA256: `678586f254e47f678d36780fbdf65fe7ec8dd720fdf75fb814444a1a870146bd`
- Approved render PNG SHA256: `473f5a50f927b48f0507607e3e17bdfa81ca3730bce18ff8873faf5e33afa9ed`
- Approved evidence JSON SHA256: `7e6d1c7fc4be9cd10fce43437212d262f5eeff633a57a6b7e6523f4a95136d9a`

Visual checklist was recorded as all true for:

- `j1_pin_order`
- `j1_nc_marker`
- `j1_fields`
- `matrix`
- `title_block`

## Verification

Task branch verification:

- `PYTHONDONTWRITEBYTECODE=1 python -m unittest -v tools.verify_schematic_contract tools.verify_schematic_apply tools.verify_schematic_acceptance`
- Result: `78 tests OK`, `40 skipped`
- Production acceptance gates: wire validation true, component validation true, ERC `0 errors / 0 warnings`
- Production inventory: connector `1`, diode `70`, switch `75`
- Production layout: component count `146`, wire count `0`, label count `313`, no-connect count `1`
- Production schematic SHA256: `de6ee0b579280c4950ca3264246698cccfeab4eb2e4a03f6755534a24b23a33e`
- PCB SHA256 unchanged: `eb27463ebcb973e44b5aea551c79ac4470615a3a7f0519a4b1c54c2afd466a46`

Integration verification:

- `PYTHONDONTWRITEBYTECODE=1 python -m tools.check_schematic_acceptance --production --output .superpowers/sdd/2026-08-29-external-mcu-ffc-tail/evidence/task-3-20260829-151741/production-acceptance.integration.json`
- Result: passed
- Integration acceptance JSON SHA256: `76d41d4564feb07bfd42eee5e86dbb721ec2cc360bcd4dab878c33d9278e6f3e`
- Integration acceptance gates: wire validation true, component validation true, ERC `0 errors / 0 warnings`
- Integration inventory: connector `1`, diode `70`, switch `75`
- Integration layout: component count `146`, wire count `0`, label count `313`, no-connect count `1`
- Overlap count: `0`
- Short count: `0`
- Single-pin net count: `0`
- Integration schematic SHA256: `de6ee0b579280c4950ca3264246698cccfeab4eb2e4a03f6755534a24b23a33e`
- Integration PCB SHA256 unchanged: `eb27463ebcb973e44b5aea551c79ac4470615a3a7f0519a4b1c54c2afd466a46`

## Notes

- KiCad explicit no-connect export value `"~"` is ignored as an electrical net assignment while the explicit `J1.23` no-connect marker remains required.
- The production acceptance guard now tolerates Konnect layout responses that omit `no_connect_count` by backfilling from the schematic file for read-only counting.
