# LH60 Debug Connectors and Schematic Layout Design

## Goal

Replace the 23 individual debug test pads with six small, logically grouped
2.54 mm pin headers, and make the single-page schematic readable without
changing the keyboard matrix, GPIO allocation, switch footprints, or diode
footprints.

## Scope

Included:

- replace schematic and PCB instances `TP1..TP23` with `J1..J6`;
- expose the same 23 nets through grouped through-hole headers;
- use straight, single-row, 2.54 mm headers for Dupont or ribbon-cable leads;
- enlarge the schematic to A3 landscape and reflow the MCU, connectors, and
  matrix;
- hide diode Reference and Value fields;
- hide switch Reference fields and keep switch Value fields visible.

Excluded:

- SWD, RUN, BOOTSEL, USB data, or any signal not exposed by RP2040-Tiny;
- changes to the 10 x 7 matrix or its GPIO allocation;
- duplicated ground pins on signal headers;
- connector keying, shrouds, latches, or custom cables;
- routing or final placement optimization beyond placing the new headers in
  the existing PCB layout for subsequent routing work.

## Connector Contract

All headers are hand-soldered, vertical, single-row, 2.54 mm through-hole
parts mounted on the PCB back side. Signal headers do not duplicate ground;
test equipment and external boards use `J1.3` as the common ground. Pin 1 must
be identifiable in the PCB footprint and remain explicit in the schematic pin
map.

| Reference | Value | Size | Pin map |
|---|---|---:|---|
| `J1` | `PWR` | 1x3 | `1=VSYS`, `2=3V3`, `3=GND` |
| `J2` | `COL_A` | 1x5 | `1=COL0`, `2=COL1`, `3=COL2`, `4=COL3`, `5=COL4` |
| `J3` | `COL_B` | 1x5 | `1=COL5`, `2=COL6`, `3=COL7`, `4=COL8`, `5=COL9` |
| `J4` | `ROW_A` | 1x4 | `1=ROW0`, `2=ROW1`, `3=ROW2`, `4=ROW3` |
| `J5` | `ROW_B` | 1x3 | `1=ROW4`, `2=ROW5`, `3=ROW6` |
| `J6` | `AUX` | 1x3 | `1=GP27`, `2=GP28`, `3=GP29` |

The project must own reproducible `lh60-core` symbols and footprints for the
1x03, 1x04, and 1x05 connectors. Their electrical and mechanical contracts
match KiCad's `Connector_Generic:Conn_01x03/04/05` symbols and the vertical
`Connector_PinHeader_2.54mm:PinHeader_1x03/04/05_P2.54mm_Vertical` footprints.
The currently installed KiCad environment does not resolve those standard
connector libraries, so implementation must generate and register the
equivalent project-local assets through Konnect. It must not guess a library
ID, depend on an unregistered user-global library, or edit a library table as
text.

Freeze the project-local assets as:

- symbols: `lh60-core:Conn_01x03`, `lh60-core:Conn_01x04`, and
  `lh60-core:Conn_01x05`;
- footprints: `lh60-core:PinHeader_1x03_P2.54mm_Vertical`,
  `lh60-core:PinHeader_1x04_P2.54mm_Vertical`, and
  `lh60-core:PinHeader_1x05_P2.54mm_Vertical`.

Every footprint uses sequential pads `1..N` on a straight 2.54 mm pitch,
1.00 mm finished drills, and 1.70 mm copper pads. Pad 1 is round-rect or square
and the remaining pads are round or oval, so pin 1 remains mechanically and
visually distinct. All pads are plated through-holes on `*.Cu` and `*.Mask`.

The library footprint uses canonical front-side artwork. With pad 1 at `(0,
0)`, pads increase along positive Y at 2.54 mm intervals. For an N-pin header,
the `F.Fab` body is the rectangle:

```text
x = -1.27 .. +1.27 mm
y = -1.27 .. ((N - 1) * 2.54 + 1.27) mm
```

`F.CrtYd` is that rectangle expanded by 0.50 mm on every side. `F.SilkS`
stays outside exposed copper and includes an unambiguous pin-1 marker. Fab,
courtyard, and silk line widths are 0.10 mm, 0.05 mm, and 0.15 mm
respectively. Each footprint carries `exclude_from_pos_files` because assembly
is manual.

Every production instance `J1..J6` is flipped exactly once onto `B.Cu`. KiCad
therefore maps the canonical `F.Fab/F.CrtYd/F.SilkS` artwork to
`B.Fab/B.CrtYd/B.SilkS`. The library itself must not pre-place artwork on
back-side layers. Verification inspects both the canonical library geometry
and the placed-instance layers so a double flip cannot silently move artwork
to the front.

The connector value communicates the functional group. Connector References
and Values remain visible in the schematic. `B.SilkS`, read from the back-side
assembly view, shows the connector Reference and pin-1 orientation; individual
net names need not be duplicated on PCB silkscreen.

## Electrical Behavior

The connector conversion is electrically transparent:

- the exported-net set remains exactly `VSYS`, `3V3`, `GND`, `COL0..COL9`,
  `ROW0..ROW6`, and `GP27..GP29`;
- each exported net appears on exactly one connector pin;
- no connector pin bridges two exported nets;
- `J1` does not imply an alternate power-input topology: `VSYS` and `3V3` keep
  their existing board roles;
- the RP2040-Tiny pin map and the `COL2ROW` diode direction remain unchanged;
- the existing three power flags remain connected to `VSYS`, `3V3`, and
  `GND`.

The 23 test-point footprints are removed rather than retained in parallel.
This avoids duplicate debug interfaces and reduces scattered PCB objects.

## Schematic Layout and Display

The design remains a single schematic page and changes from A4 landscape to
A3 landscape. The larger page is used to improve spacing, not to add new
circuits.

### Functional regions

- Matrix: left and center, preserving the visible 10-column by 7-row logical
  organization.
- MCU: upper right, with pin labels and the `RP2040-Tiny` Value separated from
  the symbol body by at least 5 mm of clear vertical space.
- Headers: right side below the MCU, grouped as PWR, COL, ROW, and AUX with
  enough spacing that connector Reference, Value, and net labels do not share
  a text line.
- Power flags: adjacent to the PWR group without intruding into the page frame
  or title block.

No component, field, or net label may intrude into the A3 title block or page
frame. Layout coordinates remain on KiCad's 1.27 mm schematic grid.

### Matrix cell readability

Each logical matrix cell must use separate visual bands for:

1. column label and diode;
2. the `KEY_nn` local node;
3. one or more switch symbols and their physical-key Values;
4. the row label.

The vertical pitch must accommodate the longest currently active physical-key
Value without overlapping the next cell. Shared logical nodes may stack their
multiple switch symbols, but each visible Value must remain distinct. Net
labels must lead away from component bodies instead of reading back across pin
names.

### Field visibility contract

| Component kind | Reference | Value |
|---|---|---|
| Diode | hidden | hidden |
| Switch | hidden | visible |
| Connector | visible | visible |
| MCU | visible | visible |
| Power flag | normal KiCad behavior | normal KiCad behavior |

References and Values remain semantically populated even when hidden. Hiding a
field must not blank it, rename the component, or remove BOM/netlist identity.

The currently deployed Konnect schema can edit field contents but does not
expose per-instance Reference/Value visibility. Implementation therefore has a
hard tool-capability gate: add or deploy a Konnect field-visibility operation
before mutating the production schematic. Direct S-expression edits and empty
field values are not acceptable fallbacks. The generator must own these
visibility settings so regeneration cannot reintroduce overlaps.

Freeze the required Konnect interface as one atomic batch operation:

```text
batch_set_schematic_field_visibility(
  schematic: string,
  edits: [
    {
      reference: string,
      reference_visible?: boolean,
      value_visible?: boolean
    }
  ]
)
```

Each edit must provide at least one visibility field. The tool validates every
reference and every requested field before writing; any missing component,
missing Reference/Value property, duplicate reference, malformed edit, or file
revision conflict rejects the whole batch without changing the schematic. It
changes only the `hide` state of the requested Reference/Value properties and
preserves their text, positions, styles, UUIDs, symbol identity, and all other
fields. The result reports the old and new visibility of each requested field.
Applying the same state twice is a successful no-op.

## PCB Integration

The six new through-hole headers replace `TP1..TP23` in the PCB netlist. They
may be distributed along available board space instead of forming one large
20-pin block. Placement priorities are:

1. avoid every switch/socket, MCU, diode, board edge, and courtyard;
2. preserve access for Dupont housings and vertical cable removal;
3. keep the two column headers near column trunks and the two row headers near
   row trunks where practical;
4. keep `J1` and `J6` accessible without forcing signal headers into one bank;
5. preserve a clear pin-1 orientation for every header.

For placement acceptance, model each Dupont housing as a 2.54 mm wide body
whose length is `N * 2.54 mm`, then add 1.00 mm access margin on every planar
side. These access envelopes must not overlap each other, any socket or
component courtyard, or the board edge. Keep at least 15 mm of vertical
extraction space below the back-side PCB surface; enclosure design is outside
this task but must not later consume that volume.

The connectors are hand-soldered and carry `exclude_from_pos_files`; none may
appear in position/PnP output. Final coordinates are not frozen by this design;
placement must be checked against the live production board through Konnect and
verified by DRC. Existing switch, diode, MCU, and board-outline placements are
outside this change.

## Source-of-Truth Changes

`tools/lh60_design/schematic.py` remains the deterministic source of truth. It
must define:

- the six connector components and exact pin maps above;
- A3 landscape page setup;
- component coordinates and matrix spacing;
- the field-visibility contract.

The old `test_point_nets()` inventory and `test_point` components are replaced
by a connector-group contract. Tests must validate semantic pin maps rather
than infer them from connector order.

KiCad source changes remain Konnect-only. Python and documentation files may be
edited normally. Any PCB synchronization must use Konnect's schematic-to-PCB
update flow and exact dry-run revision gate before apply.

## Verification

Implementation is accepted only when all of the following are fresh:

- connector contract tests prove all six References, Values, sizes, footprints,
  exact pin-to-net assignments, pad geometry, bottom-side graphics, pin-1
  markings, and `exclude_from_pos_files`;
- the plan contains 1 MCU, 75 switches, 70 diodes, 6 connectors, and 3 power
  flags, with no `TP*` components;
- every exported debug net occurs on exactly one connector pin;
- switch and diode references/values remain populated in the netlist even when
  hidden in the drawing;
- page configuration is A3 landscape;
- SVG or rendered schematic inspection shows no text/component overlaps and no
  title-block intrusion;
- Konnect overlap, orphan, shorted-net, single-pin-net, wire, and component
  checks have no new unexplained findings;
- KiCad ERC reports zero errors and zero warnings;
- schematic-to-PCB dry run removes 23 test points and adds exactly 6 connector
  footprints without unrelated changes, and exposes 23 connector pads on the
  expected nets;
- after PCB synchronization and placement, DRC introduces no connector-related
  clearance, edge, or courtyard violations; the 23 connector pads remain
  intentionally unrouted in this placement-only scope and must appear as the
  expected ratsnest rather than shorts or missing nets;
- all six connector References and pin-1 markers are readable on `B.SilkS`
  from the back-side assembly view, their Dupont access envelopes do not
  overlap, and the required 15 mm extraction volume is recorded in the
  placement report;
- position/PnP export contains none of `J1..J6`;
- the full `verify_*.py` suite, Python compilation, and `git diff --check` pass.

## Delivery Units and Dependency Graph

### Units

1. **Specification**: this reviewed design document. Independently reviewable
   and revertible.
2. **Konnect visibility capability**: safe instance-field visibility support
   and its tests. Independently verified in the Konnect repository and deployed
   before schematic mutation.
3. **Connector and layout contract**: failing then passing Python contract
   tests plus deterministic plan changes.
4. **Production schematic**: Konnect-only replacement, A3 reflow, field hiding,
   visual checks, and ERC.
5. **PCB synchronization and connector placement**: Konnect dry run/apply,
   placement, and DRC.

### Dependencies

- Unit 2 -> Unit 4: **true blocker**; field visibility cannot otherwise be
  applied safely.
- Unit 3 -> Unit 4: **true blocker**; the production schematic must implement a
  reviewed deterministic contract.
- Unit 4 -> Unit 5: **true blocker**; PCB synchronization consumes the completed
  schematic.
- Unit 2 and Unit 3 share only the agreed visibility interface and may proceed
  in parallel once that interface is frozen.

## Rollback

Revert the implementation commits in reverse order. The previous schematic and
PCB restore `TP1..TP23`, A4 layout, and existing field display without changing
the matrix or GPIO mapping. Do not partially retain connector footprints after
restoring test-point symbols.
