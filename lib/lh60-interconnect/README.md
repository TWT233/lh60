# LH60 Interconnect Library

This project-local KiCad library contains the exact 24-pin external-MCU FFC
connector selected for the LH60 split MCU tail plan.

## Controlled Part

- Manufacturer: XUNPU
- MPN: `FPC-05F-24PH20`
- LCSC/JLCPCB part: `C2856805`
- Product URL: `https://item.szlcsc.com/2856805.html`
- Permanent LCSC PDF:
  `https://datasheet.lcsc.com/datasheet/pdf/0ee18373cdadd5e6c8c1fa51e58ba102.pdf?productCode=C2856805`
- XUNPU series drawing: `FPC-05F` 0.50 mm pitch bottom-contact
  horizontal front-flip FFC/FPC connector drawing as published through LCSC.
- Retrieval date: 2026-08-29
- EasyEDA component UUID: not adopted as source of truth in this branch;
  acceptance is based on the controlled LCSC/XUNPU drawing and Konnect
  readback instead.
- EasyEDA footprint UUID: not adopted as source of truth in this branch;
  acceptance is based on the controlled LCSC/XUNPU drawing and Konnect
  readback instead.

## Frozen Geometry

- 24 signal pads, top-view pin 1 at the leftmost signal land.
- Signal pad pitch: 0.50 mm.
- Signal pad centers: X = -5.75 mm through +5.75 mm, Y = 0.00 mm.
- Signal pad size: 0.30 x 1.25 mm.
- Mechanical hold-down lands: unnumbered SMD pads at X = +/-7.44 mm,
  Y = 2.575 mm, size 2.00 x 2.50 mm.
- Pad layers: `F.Cu`, `F.Paste`, and `F.Mask`.
- Closed housing envelope: 16.40 x 5.12 x 2.00 mm.
- Fabrication outline spans X = -8.20..8.20 mm and Y = 0.68..5.80 mm.
- Courtyard is drawn with 0.25 mm clearance around the body and all lands.
- Cable mouth/insertion direction is `+Y`.
- FFC end: 12.50 +/- 0.03 mm wide, 0.30 +/- 0.03 mm thick, at least
  3.00 mm exposed conductor, 6.00 mm stiffener.

## Model Policy

No exact trusted STEP model was available for `C2856805` during this task.
The footprint intentionally has no 3D model association. Do not attach an
approximate FH12 or generic FFC STEP model without a separate provenance gate.

## Why FH12 Is Not A Substitute

Hirose `FH12-24S-0.5SH(55)` shares the same nominal 24-conductor, 0.50 mm cable
interface class, but its PCB land pattern and mechanical envelope are not the
same as XUNPU `FPC-05F-24PH20`. It is not a drop-in replacement for fabrication
or assembly, and this library must remain bound to `C2856805`.
