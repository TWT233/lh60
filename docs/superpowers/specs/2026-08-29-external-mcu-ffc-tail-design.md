# LH60 External MCU FFC Tail Design

## Decision

Move the Waveshare RP2040-Tiny and its official 8-pin USB adapter off the
keyboard matrix PCB onto a separately mounted rigid MCU tail board. Connect
the two rigid boards with one replaceable 24-conductor, 0.5 mm-pitch FFC.

Both boards use the same bottom-contact flip-lock connector:

- manufacturer: XUNPU;
- MPN: `FPC-05F-24PH20`;
- LCSC/JLCPCB part: `C2856805`;
- 24 contacts at 0.5 mm pitch;
- horizontal SMT, bottom contact, hinged lid;
- 2.0 mm board height;
- 0.30 mm FFC/FPC mating-end thickness.

The design must use the `C2856805`-specific land pattern. Hirose
`FH12-24S-0.5SH(55)` has the same cable-side interface but a different PCB
land pattern and is not a drop-in alternate.

## Motivation

The current RP2040-Tiny placement cannot fit within the 285.75 x 95.25 mm
keyboard outline. Its placed mechanical envelope extends roughly 11.3 mm
beyond the lower board edge. Moving the MCU off-board also separates the
keyboard matrix from the USB connector and removes the MCU body, USB FPC, and
adapter-access constraints from the dense socket area.

## Scope

Included:

- replace the production keyboard-board MCU connection with one 24-pin FFC
  connector;
- create a separate rigid MCU tail board with the matching connector and the
  existing RP2040-Tiny module;
- preserve the current 10 x 7 matrix and GPIO assignment;
- keep the RP2040-Tiny official 8-pin USB adapter entirely on the MCU side;
- define the connector pinout, cable orientation, mechanics, protection
  provisions, libraries, and verification gates.

Excluded:

- I/O expanders or shift registers on the keyboard board;
- carrying USB, `VSYS`, `3V3`, or spare GPIO across the 24-pin FFC;
- changing switch, socket, diode, matrix, or QMK `COL2ROW` behavior;
- integrating the two rigid boards with a custom flex or rigid-flex PCB;
- enclosure styling and exterior industrial design; the mechanical interface
  datums, keepouts, supports, and service states required to mount the PCBs,
  cable, and USB adapter remain in scope;
- final routing and fabrication release in the specification unit.

## Architecture

### Keyboard matrix board

The main keyboard PCB is electrically passive apart from switches and matrix
diodes. It contains:

- 75 physical switch sockets representing 70 logical nodes;
- 70 `1N4148WS` matrix diodes;
- one `C2856805` connector;
- no MCU, USB data path, voltage regulator, I/O expander, or serial matrix
  logic.

The keyboard board does not need `VSYS` or `3V3`. A key press only connects a
matrix drive line through a diode and switch to a matrix sense line.

### MCU tail board

The tail is an ordinary two-layer rigid PCB. It contains:

- one Waveshare RP2040-Tiny V1.1 using the existing audited project library;
- one matching `C2856805`;
- the existing official 8-pin FPC path to the Waveshare USB adapter;
- one normally fitted `0R` series-resistor footprint in every matrix signal,
  replaceable with a measured 33-100 ohm value;
- local access to `GP27..GP29`, `VSYS`, `3V3`, and `GND`;
- at least two mechanically separated M2 mounting points.

The official Waveshare adapter and its supplied 8-pin FFC are a controlled
vendor assembly. U5 records their revision or other traceable baseline and
audits the vendor schematic for CC1/CC2, VBUS, `D+`/`D-`, ESD, and shield/chassis
relationships. USB data must have no added stub. The internal 8-pin FFC is
power-off service only; only the external USB-C plug is hot-pluggable.

The initial tail-board envelope target is 28 x 35-40 mm. Final dimensions may
grow only as required by the actual connector, RP2040-Tiny STEP model, official
USB-FPC bend and insertion volume, mounting holes, routing, and courtyards.

### Cable

Use a replaceable 24-conductor FFC with:

- 0.5 mm pitch;
- 0.30 mm mating-end thickness;
- length target 100 mm or shorter;
- hard design maximum 150 mm unless signal-integrity validation approves a
  longer assembly;
- contact orientation selected from the final board-side placement readback,
  not from a seller's Type A/Type B naming alone.

The Mechanical Interface Freeze defined below selects one purchasable cable MPN
or controlled procurement drawing and states whether its contacts are on the
same side at both ends or on opposite sides. That decision depends on the two
placed connector orientations and is a prerequisite for PCB placement, not a
final-BOM cleanup item.

## 24-Pin Interface Contract

### Pin map

The following map is frozen at both connectors. Pin 1 on the keyboard board
connects to pin 1 on the tail board; no logical reversal is permitted in the
schematic to compensate for an incorrectly selected cable.

| Pin | Net | Pin | Net |
|---:|---|---:|---|
| 1 | `GND` | 24 | `GND` |
| 2 | `COL0` | 23 | `NC` |
| 3 | `COL1` | 22 | `ROW6` |
| 4 | `COL2` | 21 | `ROW5` |
| 5 | `GND` | 20 | `GND` |
| 6 | `COL3` | 19 | `ROW4` |
| 7 | `COL4` | 18 | `ROW3` |
| 8 | `COL5` | 17 | `ROW2` |
| 9 | `GND` | 16 | `GND` |
| 10 | `COL6` | 15 | `ROW1` |
| 11 | `COL7` | 14 | `ROW0` |
| 12 | `COL8` | 13 | `COL9` |

This uses 17 matrix nets, six ground conductors, and one deliberate no-connect.
Pins 1/24, 5/20, and 9/16 are mirrored ground pairs. Reversing the cable end
therefore maps ground only to ground; every matrix signal maps to another
matrix signal or the single NC. No reversal can put ground or a power rail on
a GPIO. This proves only the passive net topology. It does not prove that every
firmware, bootloader, reset, or transient GPIO state is free of output
contention. Standard QMK `COL2ROW` operation drives one row at a time and reads
columns, and no direct output-to-output conflict is expected under that mode,
but reversed pin order remains unsupported and must not be energized. The
explicit `1 <-> 24` fault fixture is evaluated unpowered unless a later
electrical review first proves all relevant GPIO states and freezes safe
current limits.

### Preserved MCU map

The tail board preserves the existing firmware-facing mapping without an
adapter layer:

- `COL0..COL9 -> GP0..GP9`;
- `ROW0..ROW5 -> GP10..GP15`;
- `ROW6 -> GP26`;
- `GP27..GP29` remain spare and local to the tail board.

QMK remains `COL2ROW`; its physical-key-to-logical-node mapping is unchanged.

### Prohibited FFC nets

The FFC must not carry:

- `VSYS`;
- `3V3`;
- USB `D+` or `D-`;
- USB VBUS;
- `RUN`, `BOOTSEL`, SWDIO, or SWCLK;
- `GP27`, `GP28`, or `GP29`.

No connector pin may be repurposed as a power pin in a later revision without
changing the connector keying and this interface revision.

## Connector and Library Contract

### Exact part binding

The schematic component carries at least these fields:

- `Manufacturer = XUNPU`;
- `MPN = FPC-05F-24PH20`;
- `LCSC = C2856805`;
- datasheet URL for the exact LCSC part.

Use a generic 24-pin connector symbol with sequential pins `1..24`; pin 23 is
marked no-connect on both boards. A dedicated symbol is unnecessary unless the
generic symbol cannot retain the exact manufacturer fields.

### Footprint source

Create or import one project-local, audited footprint for `C2856805` through
Konnect. Do not text-edit `*.kicad_mod` or a library table. The footprint must
be derived from the exact XUNPU/LCSC drawing, not from the Hirose FH12 library
footprint or a generic 24-pin connector.

The audit must freeze at least:

- 24 signal-pad centers at 0.50 mm pitch;
- signal-pad size and solder-mask/paste behavior;
- both mechanical hold-down pad positions, sizes, copper, paste, and mask; the
  hold-downs are non-signal mechanical SMD pads and must not appear as
  interface pins 25/26 or carry a logical net;
- housing, actuator, and insertion-edge `F.Fab` geometry;
- datasheet-based `F.CrtYd`;
- pin-1 mark and cable-entry direction on `F.SilkS`;
- 0.30 mm cable-end requirement;
- a STEP model when an exact trustworthy model is available.

The current manufacturer drawing states 0.30 x 1.25 mm signal lands at 0.50 mm
pitch, 2.00 x 2.50 mm hold-down lands at 14.88 mm center spacing, and an
approximately 16.40 x 5.12 x 2.00 mm closed housing. It specifies an FFC end
12.50 +/- 0.03 mm wide and 0.30 +/- 0.03 mm thick, at least 3.00 mm of exposed
conductor, and a 6.00 mm stiffener. U3 must verify and freeze every exact
coordinate, tolerance, paste aperture, mask opening, and housing dimension from
the controlled drawing before authoring the production footprint.

### Copper-clearance rule

Adjacent 0.30 mm signal lands at 0.50 mm pitch have 0.20 mm copper spacing.
KiCad's Board Setup minimum is an absolute floor and cannot be reduced by a
pad-local override. Both projects therefore use a 0.20 mm absolute clearance
floor plus a custom 0.25 mm rule for every unrelated copper pair. The sole
0.20 mm exception is a pair of distinct signal pads belonging to the same
placed `lh60-interconnect:FPC-05F-24PH20` footprint. Traces, vias, zones, other
components, and copper belonging to different connector instances remain at
0.25 mm or greater.

This rule must be authored through a safe Konnect custom-rule operation and
read back from the project. Before either production PCB uses it, a real KiCad
10 DRC coupon must prove all three cases: the connector's 0.20 mm adjacent pads
pass, unrelated copper at 0.24 mm fails, and unrelated copper at 0.25 mm passes.
Lowering the global minimum without the complementary custom rule is forbidden.

### Pin numbering and orientation

Pin 1 must be explicit in the symbol, footprint, both PCB silkscreens, assembly
drawing, and cable drawing. Every drawing uses a stated observation face and
shows PCB top/bottom, connector mouth, signal-land tail, bottom-contact face,
FFC exposed-contact face, stiffener face, and conductor 1. The audited LCSC
baseline is pad 1 at the left when the PCB is viewed from the top with signal
lands above the body and the cable mouth below it; U3 must confirm that mapping
against the controlled manufacturer drawing and physical continuity. The
implementation must render and review both boards together with the chosen FFC
contact orientation. It must prove all of the following rather than relying on
`bottom contact` or `same side` wording:

1. keyboard-board connector pin 1 reaches cable conductor 1;
2. cable conductor 1 reaches tail-board connector pin 1;
3. the exposed FFC contacts face the connector contacts at both ends;
4. insertion directions and actuators remain reachable after enclosure
   assembly.

## Electrical Details

### Signal damping

Place a normally fitted `0R` series resistor in each matrix signal on the tail
board, as close as practical to its RP2040 GPIO. A DNP resistor would open that
matrix line and is not a valid default. QMK `COL2ROW` makes seven row lines
source outputs and ten column lines pulled-up inputs, so damping and input
settling criteria need not use the same fitted value. Validate the footprints
and routing for a measured 33-100 ohm output-side option if edge ringing is
observed. Do not fit arbitrary resistance without scope or logic-analyzer
evidence from the controlled maximum-length cable.

The signal-integrity report freezes firmware scan/settle timing, GPIO drive and
slew configuration, cable SKU/length and, where the supplier provides them,
conductor resistance, capacitance, and crosstalk. At the maximum cable length
it measures the worst adjacent-aggressor and multi-key patterns and records
VIH/VIL margin, over/undershoot against RP2040 absolute limits, settling before
sampling, and extra threshold crossings. The report also freezes a typing/scan
soak duration with zero missed, duplicated, or phantom transitions.

### Power ownership

The supported power source is the official Waveshare USB adapter only. Local
`VSYS` and `3V3` access on the tail board is measurement-only; neither rail may
be driven, back-powered, or paralleled with another source. Label those points
accordingly and document their output/current limitations. Any future external
power input requires a new revision with voltage/current range, ORing or reverse
blocking, inrush, sequencing, USB-connected/disconnected leakage, and backfeed
verification.

### ESD and hot plug

The cable is an internal, non-hot-plug interface. Documentation and silkscreen
must state that it is connected or disconnected only while USB power is off.
The enclosure must prevent normal user contact with the ZIF ends.

Reserve placement and routing space near the tail connector for optional
protection. The protection decision must state whether the array is rail-less
or rail-steering and must account for leakage, capacitance, clamp voltage, VRWM,
and injection/backfeed while 3V3 is off; an unpowered rail-steering array must
not silently lift the tail-board supply. Population is decided by a documented
IEC 61000-4-2 system test plan that freezes level, contact/air injection points,
powered/unpowered states, 17-channel coverage, acceptable reset behavior, and
permanent-failure criteria. The keyboard board remains passive and does not
receive a power rail solely to support protection components.

### Ground conductors

All six FFC ground pins join the same tail-board and keyboard-board ground
nets through low-inductance connector escapes and continuous local reference
copper. Add stitching wherever the escape changes reference layer. On the
passive keyboard board this reference copper may be localized around the
connector, but it must provide a continuous path under the connector fanout
and may not be an isolated decorative island. It must not connect to switch or
diode nets.

## Mechanical Integration

### Keyboard board

- Place the connector near the lower/rear board edge and near the former MCU X
  region, with the FFC leaving toward the edge instead of crossing sockets.
- Keep copper at least 0.50 mm from the board edge.
- Use the exact connector courtyard for closed-body placement. A separate
  mechanical/user keepout must cover the fully open actuator sweep, straight
  cable insertion path, finger or tweezer access, 6 mm stiffener, and first
  permitted bend point.
- Keep the stiffener and cable insertion path clear of sockets, case ribs,
  screws, and the plate.
- The connector and its solder joints must not support the tail board.

### Tail board

- Mount the tail board to the enclosure with at least two M2 fasteners.
- Separate the mounting holes enough to resist rotation during cable and USB
  insertion.
- Keep both the 24-pin ZIF actuator and the RP2040-Tiny USB-FPC interface
  serviceable after mounting.
- Include the RP2040-Tiny STEP body, its 8-pin FPC, the USB adapter, and both
  insertion/extraction volumes in the enclosure review.
- Fix the official USB adapter independently to the enclosure or panel. USB-C
  insertion and extraction loads must not be carried by the 8-pin FPC, either
  FPC connector, or the RP2040-Tiny tail board.

### Cable management

- Leave a shallow S-shaped service loop; do not tension the FFC.
- Do not fold the cable immediately at the stiffener.
- Use at least `max(5 mm, selected-cable requirement)` as the provisional
  static bend radius. The Mechanical Interface Freeze must replace this with a
  validated static and assembly-dynamic radius, minimum straight length after
  the stiffener, and service-loop allowance. Edgewise bends and twists are
  prohibited.
- Use enclosure guides or a clamp so keyboard flex and transport loads are not
  transferred to either ZIF connector.
- Do not use an unseparated mouse-bite bridge as a finished flexible hinge.

### Mechanical Interface Freeze

Main- or tail-board PCB placement may not start until one Mechanical Interface
Freeze (MIF) report has been reviewed, approved, committed, and pushed. It
freezes:

- one purchasable FFC MPN or controlled procurement drawing, one nominal
  length, allowed tolerance, same-side/opposite-side contacts, end width, end
  thickness, exposed conductor, stiffener, and permanent conductor-1 marking;
- both PCB observation faces, connector sides and rotations, cable-mouth
  directions, and the exact physical `pin 1 -> conductor 1 -> pin 1` path;
- main- and tail-board relative XY/Z position and orientation;
- main-board local insertion support; tail-board, USB-adapter, and enclosure
  mounting datums; and plate, wall, rib, screw, socket, and cable keepouts;
- board thickness and the M2 hole type, diameter, locations, spacing, edge and
  copper clearances, fastener/washer/nut/standoff stack, Z height, and torque;
- open-actuator sweep, straight insertion, tool/finger access, stiffener, first
  bend, service-loop, clamp/guide, and enclosure-closure volumes;
- normal-use and cover-removed maintenance states plus the step-by-step
  assembly/disassembly order;
- strain-relief geometry and its cable-retention, pull, vibration, and
  intermittent-contact acceptance values.

The final tail outline, connector coordinates, M2 values, cable SKU, and these
mechanical measurements are outputs of MIF rather than guesses in this
architecture specification.

## Debug Connector Transition

The current `J1..J6` headers remain useful for a short proof-of-concept because
`J2..J5` expose all 17 matrix nets and `J1.3` provides ground. They are not the
production inter-board connector because signal groups lack adjacent return
conductors, the housings are tall and unkeyed, and the three 1x3 groups can be
misplugged.

Implementation sequence:

1. use the existing headers and a separately fixed RP2040-Tiny prototype to
   validate firmware and a short cable;
2. add the `C2856805` library contract and both board schematics;
3. replace the six production headers and U1 on the keyboard board with the
   single 24-pin connector;
4. create and verify the tail board;
5. retain only deliberate local debug access on the tail board.

Do not retain J1-J6 in parallel on the final keyboard board unless a later
mechanical review explicitly proves their access volume and purpose.

## Source of Truth and Project Structure

The deterministic Python model remains the non-KiCad source of truth. Add one
module for the inter-board interface rather than scattering the pin map across
schematic and PCB scripts. It owns:

- exact connector MPN and LCSC number;
- pins `1..24` and their net/NC assignments;
- matrix-to-RP2040 GPIO mapping;
- prohibited FFC nets;
- passive reversal-topology invariants;
- cable pitch, mating thickness, and maximum validated length;
- the approved MIF report revision and cable-orientation contract once MIF is
  complete.

Recommended KiCad project structure:

```text
lh60.kicad_pro / lh60.kicad_sch / lh60.kicad_pcb
    production keyboard matrix board

mcu-tail/mcu-tail.kicad_pro
mcu-tail/mcu-tail.kicad_sch
mcu-tail/mcu-tail.kicad_pcb
    RP2040-Tiny tail board

lib/lh60-interconnect/
    exact C2856805 symbol metadata, footprint, provenance, and model
```

Every KiCad source mutation must go through Konnect. Python, Markdown, and test
files may be edited normally. PCB writes remain serialized even when schematic,
library, and model/test units are developed in parallel.

## Units, Dependency Graph, and Shared Contracts

### Independently verifiable units

| Unit | Deliverable | Independent verification |
|---|---|---|
| U1 | Approved design specification | self-review and user review |
| U2 | Inter-board Python contract and tests | exact pin map, reversal, prohibited-net tests |
| U3 | `C2856805` project library and provenance | datasheet geometry, export, and pad readback |
| U4 | Main-board schematic migration | ERC and netlist contract |
| U5 | Tail-board schematic | ERC, GPIO map, and power-boundary contract |
| U6 | Mechanical Interface Freeze | controlled cable, datums, keepouts, mounting, service sequence, and strain-relief report |
| U7 | Main-board PCB connector integration | placement, access, DRC, and ratsnest gates |
| U8 | Tail-board PCB | placement, routing, DRC, and 3D envelope gates |
| U9 | Prototype cable and assembly validation | continuity, current, SI, ESD, retention, and full-key tests |
| U10 | Production manufacturing package | both board packages, BOMs, assembly and cable drawings |

Each unit is one independently reviewable commit and is pushed after its own
verification. U7 and U8 may be implemented independently only in separate
worktrees because they own different `*.kicad_pcb` files.

### Dependency graph

```text
U1 -> U2                       true block: interface is approved first
U2 -> U3                       shared interface: exact part binding and pin count
U2 + U3 -> U4                 true block: main schematic needs both contracts
U2 + U3 -> U5                 true block: tail schematic needs both contracts
U2 + U3 -> U6                 shared interface: MIF freezes physical realization
U4 + U6 -> U7                 true block: main PCB needs schematic and MIF
U5 + U6 -> U8                 true block: tail PCB needs schematic and MIF
U7 + U8 -> prototype fab      true block: physical validation needs boards
prototype fab -> U9           true block: validation consumes prototype hardware
U7 + U8 + U9 -> U10           true block: production release follows evidence
```

U4, U5, and the mechanical work feeding U6 may proceed in parallel after
U2/U3. U7 and U8 are parallel only after U6 and their own schematics, because
their shared pin map and physical cable/orientation contract are then frozen.

### Write scopes

- U2 owns the new Python interface module and its tests only.
- U3 owns `lib/lh60-interconnect/` plus project library registration via
  Konnect.
- U4 owns the root schematic and root schematic generator/tests.
- U5 owns `mcu-tail/*.kicad_sch` and tail schematic generator/tests.
- U6 owns the MIF report and its controlled cable/mechanical drawings.
- U7 owns only the root PCB and root PCB verification logic.
- U8 owns only `mcu-tail/*.kicad_pcb` and tail PCB verification logic.
- U9/U10 own reports and export/acceptance tooling, not upstream design files.

Any pin-map or footprint-geometry change stops dependent writes until U2 or U3
is updated, verified, committed, pushed, and merged into the integration branch.

## Verification and Acceptance

### Contract tests

- exactly 24 connector positions exist on each board;
- exact table above appears on both sides, including NC pin 23;
- the set of signal nets is exactly `COL0..COL9` plus `ROW0..ROW6`;
- the set of connector grounds is exactly `{1, 5, 9, 16, 20, 24}`;
- reversing `pin -> 25 - pin` maps GND only to GND and never maps a matrix net
  to GND; this is explicitly a passive-topology property, not a powered safety
  claim;
- no prohibited FFC net appears on either connector;
- MCU pin mapping remains the current RP2040 contract;
- the two connector components bind to `C2856805`, not a generic or FH12
  footprint.

### Library checks

- footprint pad centers, pad sizes, hold-downs, fab, courtyard, pin-1 mark, and
  cable edge match the exact manufacturer drawing;
- symbol and footprint exports render correctly;
- both placed instances read back with the expected pad numbering;
- library provenance records source URL, retrieval date, manufacturer, MPN,
  LCSC ID, and every deliberate deviation from the source.

### Schematic checks

- ERC reports zero unexplained errors or warnings on both projects;
- the root keyboard schematic contains no RP2040-Tiny;
- the tail schematic contains exactly one RP2040-Tiny;
- the keyboard-board BOM allow-list is exactly the approved switch sockets, 70
  matrix diodes, one `C2856805`, and non-electrical mechanical items; it contains
  no active IC, pull network, local power source, or powered protection device;
- USB-only signals remain local to the module/adapter side;
- pin 23 is explicitly no-connect on both FFC connectors;
- no matrix net is shorted to another matrix net or ground.

### PCB checks

- both connectors and actuators are inside their board outlines and accessible;
- MIF mechanical/user keepouts remain clear in normal-use and maintenance
  states;
- root-board former U1 out-of-bounds geometry is absent;
- no socket, case, cable-stiffener, or connector courtyard overlap exists;
- DRC has zero errors and zero unconnected matrix/FFC items on both boards;
- root-board and tail-board renderings explicitly show pin 1 and cable entry;
- 3D assembly review includes both boards, FFC bend, RP2040-Tiny, USB FPC, USB
  adapter, mounting holes, and enclosure keepouts.

### Prototype-fabrication gate

Before ordering prototype hardware, U2-U8 must be complete and the exact
libraries, ERC, DRC, MIF, 3D assembly, prototype BOMs, cable procurement
drawing, and manufacturing exports must pass. Physical test results are not a
prerequisite to building the specimens that produce those results.

### Prototype physical validation and production-release gate

Before production release:

1. continuity-test the complete `1 -> 1` through `24 -> 24` permutation with
   power disconnected;
2. verify the six grounds and NC independently;
3. continuity-test an explicit `1 <-> 24` pin-order-reversal fault fixture
   unpowered; do not treat an upside-down, non-contacting cable as this fault and
   do not energize the fixture unless a separate electrical review has proven
   every relevant GPIO state and frozen current limits;
4. power only from the official USB adapter;
5. measure USB-connected/disconnected rail leakage and backfeed, startup inrush,
   and supported-source current against thresholds frozen before the test;
6. verify all 75 physical sockets individually and the expected 70 logical
   nodes, including every alternate socket;
7. capture the worst row/column and adjacent-aggressor scan waveforms with 0
   ohm links and apply the frozen VIH/VIL, absolute-limit, settling, and
   double-crossing gates;
8. fit 33-100 ohm series values only if measurements justify them, then repeat
   the full typing/debounce test;
9. verify full insertion, fully closed locks, conductor-1 marking, no fold,
   scrape, exposed copper, or enclosure pinch, and the MIF retention/load
   criteria;
10. run the frozen scan/typing soak with zero missed, duplicate, or phantom key
    events and the IEC 61000-4-2 plan with no disallowed reset or damage;
11. run a documented type test for mating, enclosure, pull, vibration, and
    intermittent contact. The connector datasheet rates 20 mating cycles, so
    cycle count, test load/direction, contact-resistance change, and reject
    thresholds must be frozen before test; type-test samples are separate from
    production end-of-line units.

Production EOL checks every unit for visual seating/lock state, the complete
permutation, matrix operation, and enclosure pinch. U10 freezes component side,
PnP rotation, SMT/hand-solder sequence, AOI/manual inspection, FFC incoming
inspection, fiducials, and the panel/process-rail strategy or documented
assembler approval for single-board placement.

## Failure Handling

- If the selected same-side/opposite-side cable does not preserve pin numbers,
  change cable orientation or connector placement; do not silently reverse the
  logical schematic map.
- If MIF is not approved, U7/U8 PCB placement is blocked; schematic and library
  work may continue without guessing mechanical values.
- If a board cannot provide actuator and stiffener access, move the connector
  before routing; do not accept a cable that must be sharply folded at its end.
- If the 100-150 mm cable produces unstable scanning, first inspect grounding,
  edge rate, series damping, scan settle time, and debounce. Do not jump directly
  to I2C expanders.
- If the passive-board topology still cannot route, the next alternative is a
  `74HC595 + 74HC165` serial matrix board. It is a new interface revision and
  requires a separate design approval because it changes firmware and failure
  modes.

## Superseded Baseline Statements

After this design is implemented and verified, these old production statements
are superseded:

- RP2040-Tiny mounted on the keyboard PCB;
- six `J1..J6` headers as the production matrix breakout;
- `VSYS`, `3V3`, and spare GPIO exported from the keyboard board;
- the keyboard board and MCU sharing one KiCad PCB.

They remain valid only as historical or prototype evidence until the new boards
pass the acceptance gates above.
