# -*- coding: utf-8 -*-
"""
LH60 socket-coexistence test bench generator.

Builds a PCB-only KiCad project (19.05 mm grid) with:
  * both Choc hotswap socket footprints embedded (kiswitch V1/V2 Plated,
    Kailh CPG151101S11 "KaiHua contact")
  * the four KLE conflict zones, attempt A (all 0 deg) and attempt B (big key
    180 deg) so overlapping holes/pads are visible in DRC
  * reference pairs at the measured minimum coexistence distances
  * the split-RShift ambiguity from the KLE ({x:10} vs right-aligned)
  * a 15u x 5u grid at 19.05 mm for freehand experiments
"""

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]          # lh60 repo worktree
MASTER = ROOT.parents[1]                             # lh60 master checkout
OUT_DIR = ROOT / "test"
U = 19.05

KISWITCH_PATH = ("lib/kiswitch/library/footprints/Switch_Keyboard_Hotswap_Kailh.pretty/"
                 "SW_Hotswap_Kailh_Choc_V1V2_Plated_1.00u.kicad_mod")
KAIHUA_PATH = MASTER / "lib" / "mx1a.pretty" / "KaiHua_Contact_1.00u.kicad_mod"


def fetch_kiswitch():
    r = subprocess.run(
        ["git", "-C", str(ROOT), "show", f"540a43a:{KISWITCH_PATH}"],
        capture_output=True, text=True, check=True,
    )
    return r.stdout


def strip_balanced(text, marker):
    """Remove the balanced s-expr block starting at marker (e.g. a group block)."""
    i = text.find(marker)
    if i < 0:
        return text
    depth = 0
    j = i
    while j < len(text):
        if text[j] == "(":
            depth += 1
        elif text[j] == ")":
            depth -= 1
            if depth == 0:
                j += 1
                break
        j += 1
    return text[:i] + text[j:]


def clean_module(text):
    text = re.sub(r"\s*\(tstamp [^)]*\)", "", text)
    text = strip_balanced(text, '(group ""')
    return text.strip()


def make_footprint(src_text, fp_name, ref, at_x, at_y, rot, net_no, is_kiswitch):
    t = clean_module(src_text)
    if is_kiswitch:
        # legacy "(module NAME (layer F.Cu) (tedit 0)" -> KiCad 6+ "(footprint ..."
        t = re.sub(
            r"^\(module ([^\s]+) \(layer F\.Cu\) \(tedit [^)]*\)",
            rf'(footprint "{fp_name}" (layer "F.Cu") (tedit 0)',
            t,
        )
        anchor = "(tedit 0)"
    else:
        anchor = "(tedit 623EC599)"
    # insert (at ...) right after the footprint opening attributes
    t = t.replace(anchor, anchor + f"\n    (at {at_x:.4f} {at_y:.4f} {rot})", 1)
    # unique reference
    t = re.sub(r'\(fp_text reference "?[^"\s)]*"?', f'(fp_text reference "{ref}"', t)
    # assign a unique net to every pad so copper overlaps across footprints show in DRC
    def add_net(m):
        pad = m.group(0)
        return pad[:-1] + f' (net {net_no} "N{net_no}"))'
    t = re.sub(r"\(pad[^\n]*\)", add_net, t)
    return t


def zone_sockets(zone, rot_big):
    """Return list of (ref, kind, rel_x_u, rot) for a zone's mutually-exclusive options."""
    k = "kiswitch"
    if zone == "A":
        return [("2U", k, 1.00, rot_big), ("splitL", k, 0.50, 0), ("splitR", k, 1.50, 0)]
    if zone == "B":
        return [("ANSI", k, 1.125, rot_big), ("FN", k, 0.25, 0), ("splitE", k, 1.625, 0)]
    if zone == "C":
        return [("2U25", k, 1.125, rot_big), ("FN", k, 0.50, 0), ("splitS", k, 1.625, 0)]
    if zone == "D":
        return [("2U75", k, 1.375, rot_big), ("splitS", k, 0.875, 0), ("FN", k, 2.25, 0)]
    raise ValueError(zone)


def main():
    out_dir = OUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    kiswitch_src = fetch_kiswitch()
    kaihua_src = KAIHUA_PATH.read_text(encoding="utf-8")

    net_names = [("", 0)]
    blocks = []
    net_no = 0

    def emit(fp, ref, x, y, rot, is_kiswitch):
        nonlocal net_no
        net_no += 1
        net_names.append((f"N{net_no}", net_no))
        blocks.append(make_footprint(fp, "test", ref, x, y, rot, net_no, is_kiswitch))

    # ---- Section 1+2: conflict zones (attempt A all 0 deg, attempt B big key 180 deg)
    section_origins = [
        ("A", 10.0, 30.0, 2.0),
        ("B", 60.0, 30.0, 2.25),
        ("C", 115.0, 30.0, 2.25),
        ("D", 170.0, 30.0, 2.75),
    ]
    zone_labels = {
        "A": "A top-right 2u vs split 1u+1u  (9.53mm x2)",
        "B": "B Enter ANSI 2.25u vs Fn + 1.25u  (11.91 / 9.53mm)",
        "C": "C LShift 2.25u vs Fn + 1.25u  (11.91 / 9.53mm)",
        "D": "D RShift 2.75u vs 1.75u + Fn  (9.53 / 16.67mm ok)",
    }
    texts = []
    rects = []
    for attempt, rot_big, y_base in (("A", 0, 30.0), ("B", 180, 105.0)):
        for zone, ox, oy, span_u in section_origins:
            oy = y_base
            for role, kind, rel_u, rot in zone_sockets(zone, rot_big):
                ref = f"SW_{attempt}{zone}_{role}_{'R' if rot == 180 else '0'}"
                emit(kiswitch_src, ref, ox + rel_u * U, oy, rot, True)
            rects.append((ox - 8, oy - 13, ox + span_u * U + 8, oy + 13))
            texts.append((ox - 8, oy + 16, zone_labels[zone]))
        texts.append((10.0, y_base - 22, f"attempt {attempt}: "
                      f"{'all sockets 0 deg' if attempt == 'A' else 'big key rotated 180 deg'} "
                      f"(DRC errors expected)"))

    # ---- Section 3: reference pairs at measured minimums + palette
    y_ref = 190.0
    pairs = [
        ("kiswitch same-orient 14.80mm", kiswitch_src, 10.0, 14.80, 0, 0, True),
        ("kiswitch 180deg 13.30mm", kiswitch_src, 60.0, 13.30, 0, 180, True),
        ("kaihua same-orient 16.25mm", kaihua_src, 110.0, 16.25, 0, 0, False),
        ("kaihua 180deg 12.20mm", kaihua_src, 160.0, 12.20, 0, 180, False),
    ]
    for label, fp, x0, dx, rot0, rot1, isk in pairs:
        ref0 = "SW_" + re.sub(r"\W+", "_", label) + "_L"
        ref1 = "SW_" + re.sub(r"\W+", "_", label) + "_R"
        emit(fp, ref0, x0, y_ref, rot0, isk)
        emit(fp, ref1, x0 + dx, y_ref, rot1, isk)
        texts.append((x0 - 8, y_ref + 16, f"{label}  (DRC should be clean)"))
    emit(kiswitch_src, "SW_PAL_KISW", 232.0, y_ref, 0, True)
    emit(kaihua_src, "SW_PAL_KAIH", 262.0, y_ref, 0, False)
    texts.append((232.0, y_ref + 16, "palette: kiswitch / kaihua (copy freely)"))
    texts.append((10.0, y_ref - 22, "reference: minimum coexistence distances "
                 "(+0.05mm safety margin) - DRC should be clean"))

    # ---- Section 4: split-RShift ambiguity (KLE {x:10} as written vs right-aligned)
    y_amb = 265.0
    ox = 10.0
    # letters M < > ? at 8.25..11.25u (centers 8.75/9.75/10.75/11.75)
    for i, ch in enumerate(("M", "<", ">", "?")):
        cx = (8.25 + i) * U
        rects.append((ox + cx - 4, y_amb - 5, ox + cx + 4, y_amb + 5))
        texts.append((ox + cx - 4, y_amb - 9, ch))
    # as-written: {x:10} -> 1.75u at 10..11.75 (center 10.875), Fn at 11.75..12.75 (center 12.25)
    emit(kiswitch_src, "SW_E_WRITTEN_S", ox + 10.875 * U, y_amb, 0, True)
    emit(kiswitch_src, "SW_E_WRITTEN_F", ox + 12.25 * U, y_amb, 0, True)
    texts.append((ox - 8, y_amb + 16, "KLE as written {x:10}: split RShift at 10-12.75u "
                 "(overlaps M < > ?)"))
    # right-aligned: 1.75u at 12.25..14 (center 13.125), Fn at 14..15 (center 14.5)
    emit(kiswitch_src, "SW_E_RIGHT_S", ox + 60 + 13.125 * U, y_amb, 0, True)
    emit(kiswitch_src, "SW_E_RIGHT_F", ox + 60 + 14.5 * U, y_amb, 0, True)
    texts.append((ox + 60 - 8, y_amb + 16, "right-aligned {x:12.25}: split RShift at 12.25-15u"))

    # ---- Section 5: 15u x 5u grid at 19.05
    gx0, gy0 = 10.0, 330.0
    grid_lines = []
    for col in range(16):
        x = gx0 + col * U
        grid_lines.append((x, gy0, x, gy0 + 5 * U))
    for row in range(6):
        y = gy0 + row * U
        grid_lines.append((gx0, y, gx0 + 15 * U, y))
    texts.append((gx0, gy0 - 12, "grid 15u x 5u @ 19.05mm - draw your own layout here"))

    # ---- board edge
    edge = (gx0 - 20, 0.0, gx0 + 15 * U + 120, gy0 + 5 * U + 20)

    # ---- assemble
    nets = "\n".join(f'  (net {n} "{name}")' for name, n in net_names)
    fps = "\n\n".join(blocks)
    gr = []
    for x1, y1, x2, y2 in rects:
        gr.append(f'  (gr_rect (start {x1:.3f} {y1:.3f}) (end {x2:.3f} {y2:.3f}) '
                  f'(stroke (width 0.15) (type solid)) (fill none) (layer "Dwgs.User"))')
    for x, y, label in texts:
        gr.append(f'  (gr_text "{label}" (at {x:.3f} {y:.3f}) (layer "Dwgs.User") '
                  f'(effects (font (size 1.6 1.6) (thickness 0.25))) (tstamp 0))')
    for x1, y1, x2, y2 in grid_lines:
        gr.append(f'  (gr_line (start {x1:.3f} {y1:.3f}) (end {x2:.3f} {y2:.3f}) '
                  f'(stroke (width 0.05) (type solid)) (layer "Dwgs.User"))')
    gr.append(f'  (gr_rect (start {edge[0]:.3f} {edge[1]:.3f}) (end {edge[2]:.3f} {edge[3]:.3f}) '
              f'(stroke (width 0.2) (type solid)) (fill none) (layer "Edge.Cuts"))')

    pcb = f"""(kicad_pcb (version 20221018) (generator pcbnew)

  (general
    (thickness 1.6)
  )

  (paper "A3")
  (layers
    (0 "F.Cu" signal)
    (31 "B.Cu" signal)
    (32 "B.Adhes" user "B.Adhesive")
    (33 "F.Adhes" user "F.Adhesive")
    (34 "B.Paste" user)
    (35 "F.Paste" user)
    (36 "B.SilkS" user "B.Silkscreen")
    (37 "F.SilkS" user "F.Silkscreen")
    (38 "B.Mask" user)
    (39 "F.Mask" user)
    (40 "Dwgs.User" user "User.Drawings")
    (41 "Cmts.User" user "User.Comments")
    (42 "Eco1.User" user "User.Eco1")
    (43 "Eco2.User" user "User.Eco2")
    (44 "Edge.Cuts" user)
    (45 "Margin" user)
    (46 "B.CrtYd" user "B.Courtyard")
    (47 "F.CrtYd" user "F.Courtyard")
    (48 "B.Fab" user)
    (49 "F.Fab" user)
  )

  (setup
    (pad_to_mask_clearance 0)
    (pcbplotparams
      (layerselection 0x00010fc_ffffffff)
      (usegerberextensions false)
      (usegerberattributes true)
      (usegerberadvancedattributes true)
      (creategerberjobfile true)
      (svgprecision 6)
      (plotframeref false)
      (viasonmask false)
      (mode 1)
      (useauxorigin false)
      (hpglpennumber 1)
      (hpglpenspeed 20)
      (hpglpendiameter 15.000000)
      (dxfpolygonmode true)
      (dxfimperialunits true)
      (dxfusepcbnewfont true)
      (psnegative false)
      (psa4output false)
      (plotreference true)
      (plotvalue true)
      (plotinvisibletext false)
      (sketchpadsonfab false)
      (subtractmaskfromsilk false)
      (outputformat 1)
      (mirror false)
      (drillshape 0)
      (scaleselection 1)
      (outputdirectory "FabOutput")
    )
  )

  {nets}

  {fps}

  {chr(10).join(gr)}
)
"""
    (out_dir / "lh60-test.kicad_pcb").write_text(pcb, encoding="utf-8")
    print(f"wrote {out_dir / 'lh60-test.kicad_pcb'} with {len(blocks)} footprints")

    pro = {
        "board": {
            "design_settings": {
                "rule_severities": {
                    "annular_width": "error",
                    "clearance": "error",
                    "courtyards_overlap": "ignore",
                    "hole_clearance": "error",
                    "hole_near_hole": "error",
                    "npth_inside_courtyard": "ignore",
                    "pth_inside_courtyard": "ignore",
                    "silk_over_copper": "ignore",
                    "silk_overlap": "ignore",
                    "solder_mask_bridge": "error",
                    "unconnected_items": "ignore",
                },
                "rules": {
                    "min_clearance": 0.2,
                    "min_hole_clearance": 0.2,
                    "min_hole_to_hole": 0.25,
                    "min_track_width": 0.127,
                    "min_via_diameter": 0.5,
                    "min_via_annular_width": 0.1,
                },
                "meta": {"version": 2},
            }
        },
        "meta": {"filename": "lh60-test.kicad_pro", "version": 1},
        "net_settings": {
            "classes": [{
                "name": "Default",
                "clearance": 0.2,
                "track_width": 0.25,
                "via_diameter": 0.8,
                "via_drill": 0.4,
            }],
            "meta": {"version": 3},
        },
        "pcbnew": {"last_paths": {}},
        "schematic": {"meta": {"version": 1}},
        "text_variables": {},
    }
    import json
    (out_dir / "lh60-test.kicad_pro").write_text(json.dumps(pro, indent=2), encoding="utf-8")
    print(f"wrote {out_dir / 'lh60-test.kicad_pro'}")


if __name__ == "__main__":
    main()
