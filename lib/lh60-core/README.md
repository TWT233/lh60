# LH60 Core Library

The production schematic uses KiCad's standard `Switch:SW_Push` and
`Device:D` symbols. The official KiCad symbol libraries must therefore be
installed in the workstation environment before regenerating or updating the
schematic.

This project-local library keeps only the support symbols and custom
bottom-side footprints that are not supplied directly by the standard symbol
contract.

## Symbols

- `lh60-core:TestPoint`: one passive pin.
- `lh60-core:PowerFlag`: power-output marker for the carrier-provided
  `VSYS`, `3V3`, and `GND` rails so ERC can verify the otherwise passive
  test-point connections.

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
