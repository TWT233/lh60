# LH60 Default Schematic Symbols Design

## Goal

Use KiCad's standard schematic symbols for every keyboard switch and matrix
diode while preserving the existing electrical and PCB contracts.

## Symbol Contract

- Switches use `Switch:SW_Push`.
- Diodes use `Device:D`.
- Switch references remain `SW1..SW58, SW60..SW76`.
- Diode references remain `D1..D70`.
- Existing values, footprints, positions, rotations, and net labels remain
  unchanged.
- The diode mapping remains pin `1 = K` and pin `2 = A`, matching the current
  `COL2ROW` matrix plan.
- Project-local `TestPoint` and `PowerFlag` symbols remain in `lh60-core`.
- Project-local switch and diode footprints remain unchanged.

## Implementation

`tools/lh60_design/schematic.py` becomes the source of truth for the standard
symbol library IDs. The no-longer-used `KeySwitch` and `MatrixDiode`
definitions are removed from the generated `lh60-core` symbol inventory.

The production schematic is updated only through Konnect
`replace_component`, retaining each placed instance's reference, fields,
footprint, position, rotation, and connectivity. Official KiCad symbol
libraries may be installed and registered in the local user environment to
let Konnect resolve the standard IDs; they are not copied into this
repository.

## Verification

- A focused contract test must fail before implementation because the source
  and production schematic still use `lh60-core` switch and diode symbols.
- The focused test must pass after source and schematic updates.
- KiCad ERC must report zero errors and zero warnings.
- The full `verify_*.py` suite, Python compilation, JSON parsing, and
  `git diff --check` must pass.
- The PCB file must not change.

## Rollback

Revert the implementation commit. The previous project-local symbol
definitions and embedded schematic symbols are restored together without
renumbering or PCB changes.
