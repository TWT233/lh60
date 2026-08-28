# LH60 RP2040-Tiny Library

This project-local library contains the audited carrier-board interface for the
Waveshare RP2040-Tiny V1.1 module.

## Sources

- Waveshare RP2040-Tiny product page and official resources:
  <https://www.waveshare.com/wiki/RP2040-Tiny>
- Waveshare RP2040-Tiny V1.1 schematic:
  <https://files.waveshare.com/upload/7/70/RP2040-Tiny-Sch.pdf>
- Waveshare official STEP model:
  <https://files.waveshare.com/upload/2/2a/RP2040-Tiny-3D-Model.7z>
- LambdaKB `kicad-lkbd` baseline commit:
  `9bb38d7e67c561dfa24428686992abeb17d0a9aa`
- LambdaKB baseline license: MIT; preserved in
  `LICENSE-LambdaKB-MIT.txt`.

## Audited Interface

The symbol exposes only the 23 castellated carrier pads:

| Module pins | Signals |
|---|---|
| 1–16 | `GP0`–`GP15` |
| 17–20 | `GP26`–`GP29` |
| 21 | `3V3` |
| 22 | `GND` |
| 23 | `VSYS` |

The LambdaKB symbol inherited a `5V` name for pin 23 from RP2040-Zero. The
Waveshare V1.1 schematic labels this carrier pad `VSYS`, so the project symbol
uses `VSYS`. USB data, USB power, SWD, RUN, and BOOTSEL are not exposed because
they are available only through the module and its FPC adapter, not through the
23 castellated carrier pads.

## Footprint

`lh60-mcu.pretty/MCU_RP2040-Tiny_SMD.kicad_mod` uses the audited LambdaKB SMD
coordinates: 2.54 mm pad pitch, 2.4 × 1.6 mm pads, and an 18 × 23.5 mm module
body. The fabrication outline marks the FPC connector edge. The footprint is
hand-soldered and excluded from pick-and-place output. Its associated
`RP2040-Tiny-V1.1.step` model is the Waveshare official model.
