# LH60 Core Library

The production environment has no installed KiCad system symbol or footprint
collection: the Konnect library gate searched for switch, diode, test-point,
SOD-323, and test-pad entries; the system library search returned zero results.
This project-local library prevents the production schematic from
depending on an untracked workstation setup.

## Symbols

- `lh60-core:KeySwitch`: passive logical pads 1 and 2.
- `lh60-core:MatrixDiode`: pin 1 cathode, pin 2 anode.
- `lh60-core:TestPoint`: one passive pin.

## Footprints

- `D_SOD-323_Bottom`: bottom-side derivative of KiCad
  `Diode_SMD.pretty/D_SOD-323.kicad_mod`.
- `TestPoint_Pad_D1.5mm_Bottom`: bottom-side derivative of KiCad
  `TestPoint.pretty/TestPoint_Pad_D1.5mm.kicad_mod`.

The upstream footprint revision audited for these dimensions was
`7ebfa6b23cc292a56f751b7b5f4a0e12eeef69dd`. The project variants use bottom
assembly semantics but remain canonical front-side library definitions, then
are flipped to the back side during PCB placement. Test points are excluded
from BOM and pick-and-place output; SOD-323 diodes remain JLC assembly
candidates.

The KiCad library license is preserved in
`LICENSE-KICAD-LIBRARIES.md`.
