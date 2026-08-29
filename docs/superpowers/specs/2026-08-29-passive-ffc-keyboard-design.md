# LH60 Passive FFC Keyboard Design

## Decision

The repository deliverable is one root LH60 production keyboard PCB and
schematic containing only:

- 75 physical switch sockets representing 70 logical nodes;
- 70 `1N4148WS` matrix diodes;
- one XUNPU `FPC-05F-24PH20`, LCSC `C2856805`, 24-pin 0.50 mm-pitch
  bottom-contact FFC connector.

No in-repo MCU, tail PCB/project, USB adapter, regulator, debug headers,
testpoints, tail mechanics, tail manufacturing package, or dual-board
mechanical freeze is part of the repository deliverable.

The external MCU or adapter board is intentionally out of repo. This
repository defines only the passive keyboard-side electrical and mechanical
interface that such an external adapter must mate to.

## Current State

Tasks 0-3 of the earlier `external-mcu-ffc-tail` effort are already complete
and remain partially valid:

- Task 0 deployed the Konnect conditional-clearance prerequisite at commit
  `f27cc8d`, including `set_custom_rule` and `list_custom_rules`;
- Task 1 froze the exact 24-pin connector net map in Python;
- Task 2 created and audited the project-local `C2856805` library;
- Task 3 migrated the main schematic generator and acceptance logic toward a
  passive board with one FFC connector and no MCU.

This document supersedes the earlier dual-board objective and narrows the
remaining work to a single passive board.

## Scope

Included:

- one passive keyboard schematic and PCB under the root project;
- the exact 24-pin interface contract already implemented for `J1`;
- keyboard-side connector identity, footprint geometry, clearance rules, and
  placement/access constraints;
- main-board schematic completion, PCB sync, placement, routing, acceptance,
  and single-board prototype manufacturing package;
- external-adapter interface documentation and a later hardware-backed
  continuity/matrix-scan protocol using a user-supplied MCU.

Excluded:

- any in-repo MCU or adapter board design;
- any tail project, tail schematic, tail PCB, or tail manufacturing outputs;
- USB, regulator, power conversion, reset/boot, SWD, or spare GPIO design on
  the keyboard board;
- any claim that arbitrary cable reversal or powered hot-plug is safe;
- fabricated or simulated hardware evidence for external-adapter continuity or
  matrix scan.

## Architecture

### Root keyboard board

The root LH60 PCB is electrically passive apart from switches and matrix
diodes. It contains:

- 75 physical switch sockets;
- 70 matrix diodes;
- one `C2856805` connector referenced as `J1`;
- no MCU, no voltage rails exported across the interconnect, and no non-matrix
  active logic.

A key press only connects a matrix drive line through a diode and switch to a
matrix sense line.

### External adapter

The far-end MCU or adapter board is not defined in this repository. It may map
the 17 matrix signals to any suitable MCU GPIO set that satisfies its own
firmware and electrical constraints.

The historical RP2040-Tiny mapping remains useful as a legacy example:

- `COL0..COL9 -> GP0..GP9`
- `ROW0..ROW6 -> GP10..GP15, GP26`

That mapping is non-normative. Future cleanup must remove
`matrix_gpio_map` from `InterboardContract` so the passive keyboard contract is
not tied to a particular MCU.

## 24-Pin Interface Contract

### Exact pin map

`J1` is frozen to the following pin map:

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

This uses 17 matrix nets, six grounds, and one deliberate no-connect at
`J1.23`. Pin 23 is represented as `net_name=None`; no electrical net named
`NC` is created.

### Prohibited nets

The keyboard-board FFC must not carry:

- `VSYS`;
- `3V3`;
- USB `D+`, `D-`, or `VBUS`;
- `RUN`, `BOOTSEL`, `SWDIO`, or `SWCLK`;
- `GP27`, `GP28`, or `GP29`.

No future revision may repurpose a connector pin as power or debug without a
new interface revision.

### Passive reversal invariant

Pins `1/24`, `5/20`, and `9/16` are mirrored ground pairs. Reversing the cable
end therefore maps ground only to ground and all other conductors only to
matrix signals or the single no-connect.

This is a passive-topology statement only. It is not a powered-reversal safety
API, does not prove safe MCU output states, and must not be used to justify
energized reverse-cable operation.

## Connector and Library Contract

### Exact connector identity

The keyboard-side connector remains exactly:

- manufacturer: `XUNPU`;
- MPN: `FPC-05F-24PH20`;
- LCSC part: `C2856805`;
- horizontal SMT, bottom contact, front-flip hinged lid;
- 24 pins at 0.50 mm pitch;
- nominal body height `2.0 mm`;
- for an FFC end thickness of `0.30 +/- 0.03 mm`.

The project-local `C2856805` symbol and footprint from Task 2 remain the
active source of truth. Hirose `FH12-24S-0.5SH(55)` is not a land-pattern
substitute.

### Frozen keyboard-side geometry

The audited keyboard-side footprint geometry remains unchanged from Task 2:

- 24 signal lands at `0.30 x 1.25 mm` on `0.50 mm` pitch;
- two non-signal mechanical hold-down lands at `2.00 x 2.50 mm`;
- body envelope approximately `16.40 x 5.12 x 2.00 mm`;
- datasheet-derived `F.Fab`, `F.CrtYd`, and pin-1/cable-entry markings;
- same-footprint `0.20 mm` adjacent-pad clearance exception with `0.25 mm`
  general clearance restored through the deployed Konnect custom-rule path.

The already-deployed Konnect prerequisite commit is `f27cc8d`.

## Cable and External Adapter Requirements

The keyboard board mates to a replaceable external cable or adapter assembly
with all of the following keyboard-side requirements:

- `24` conductors at `0.50 mm` pitch;
- mating-end thickness `0.30 +/- 0.03 mm`;
- target cable length `<= 100 mm`;
- hard design maximum `<= 150 mm` unless a later electrical review approves
  more;
- explicit pin-1 observation face and conductor-1 documentation.

The far-end contact orientation depends on the external adapter and is not part
of the repository deliverable. This repo defines only the keyboard-side mating
contract and pin numbering.

## Keyboard-Side Placement and Access Constraints

Only keyboard-side connector placement is in scope.

Before any production PCB mutation, placement must pass a bounded
candidate-search plus visual approval gate. The accepted `J1` pose must satisfy
all of the following:

- connector mouth faces an accessible board edge;
- connector body, copper lands, courtyard, and approved access keepout remain
  within the board outline;
- the `6.00 mm` stiffener insertion zone is clear;
- the first bend starts outside the stiffener zone;
- copper-to-edge remains at least `0.50 mm`;
- no raw text editing of `lh60.kicad_pcb` is used to enforce the pose.

There is no dual-board MIF. Far-end adapter mechanics, cable dressing outside
the root board, and tail support structures are out of scope.

## Verification and Release Status

### In-repo release target

The repository release target is a single-board `PROTOTYPE_READY` manufacturing
package for the root keyboard board after:

- schematic acceptance;
- PCB sync and placement approval;
- routing completion;
- ERC zero-error;
- DRC zero-error and zero-unconnected;
- DFM/manufacturing zero-error gates.

### External hardware gate

Continuity and matrix-scan evidence with a user-supplied external MCU or
adapter is a later external gate before any mass-production status. This
repository may define the protocol and checker schema, but must not fabricate
or simulate that evidence as if hardware had been tested.

Therefore:

- `PROTOTYPE_READY` is allowed after in-repo single-board verification;
- mass-production approval is blocked until real external-hardware evidence is
  provided.

## Legacy Artifact Policy

Historical `lib/lh60-mcu` artifacts may remain in the repository while cleanup
is pending, but they must be inactive:

- not referenced by the active schematic generator or accepted schematic;
- not present on the active PCB;
- not present in active BOM or position exports;
- not required or registered by future project generation logic.

If Konnect lacks a safe unregister API for existing tables, stale project
registrations are treated as legacy nonfunctional state until a safe cleanup
task removes them.
