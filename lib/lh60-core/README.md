# LH60 Core Library

The production schematic uses KiCad's standard `Switch:SW_Push` and
`Device:D` symbols. The official KiCad symbol libraries must therefore be
installed in the workstation environment before regenerating or updating the
schematic, but the installed standard connector libraries are unavailable in
the target environment. This project therefore carries project-local
reproductions of the reviewed generic connector and vertical THT pin-header
contracts.

This project-local library keeps only the support symbols and custom
front-side footprints that are not supplied directly by the standard symbol
contract.

## Symbols

- `lh60-core:TestPoint`: one passive pin.
- `lh60-core:PowerFlag`: power-output marker for the carrier-provided
  `VSYS`, `3V3`, and `GND` rails so ERC can verify the otherwise passive
  test-point connections.
- `lh60-core:Conn_01x03`, `lh60-core:Conn_01x04`, `lh60-core:Conn_01x05`:
  project-local debug connector symbols mirroring the KiCad generic connector
  contract (`Conn_01x03`, `Conn_01x04`, `Conn_01x05`) with `J` references and
  sequential passive pins on the left at 2.54 mm pitch.

## Footprints

- `D_SOD-323_Bottom`: bottom-side derivative of KiCad
  `Diode_SMD.pretty/D_SOD-323.kicad_mod`.
- `TestPoint_Pad_D1.5mm_Bottom`: bottom-side derivative of KiCad
  `TestPoint.pretty/TestPoint_Pad_D1.5mm.kicad_mod`.
- `PinHeader_1x03_P2.54mm_Vertical`,
  `PinHeader_1x04_P2.54mm_Vertical`,
  `PinHeader_1x05_P2.54mm_Vertical`: project-local 2.54 mm vertical THT
  debug headers matching the reviewed pin-header contract.

The upstream footprint revision audited for these dimensions was
`7ebfa6b23cc292a56f751b7b5f4a0e12eeef69dd`. The project variants use canonical front-side library definitions; production instances are flipped to the back side during PCB placement. Test points are excluded from BOM
and pick-and-place output, SOD-323 diodes remain JLC assembly candidates, and the debug pin headers are excluded from pick-and-place output but stay in the BOM for hand soldering.

The connector symbols and footprints are local on purpose so the schematic and
PCB remain reproducible without guessing a global connector library ID.

The KiCad library license is preserved in
`LICENSE-KICAD-LIBRARIES.md`.
