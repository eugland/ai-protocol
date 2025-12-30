#!/usr/bin/env python3
import argparse, json, math
from pathlib import Path

def parse_hex(s: str):
    t = s.strip()
    if t.startswith("#"): t = t[1:]
    if len(t) != 6:
        raise ValueError(f"bad hex: {s}")
    r = int(t[0:2], 16)
    g = int(t[2:4], 16)
    b = int(t[4:6], 16)
    return r, g, b

def esc_kotlin(s: str) -> str:
    return s.replace("\\", "\\\\").replace("\"", "\\\"")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", required=True)
    ap.add_argument("--out", dest="outp", required=True)
    ap.add_argument("--package", dest="pkg", required=True)
    ap.add_argument("--object", dest="obj", default="ColorLut")
    ap.add_argument("--grid", dest="grid", type=int, default=32, help="grid size per channel (e.g., 16/32/64)")
    args = ap.parse_args()

    raw = json.loads(Path(args.inp).read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("input must be a list of objects")

    names = []
    rgbs = []  # packed 0xRRGGBB
    rs, gs, bs = [], [], []

    for i, item in enumerate(raw):
        name = str(item["name"])
        color = str(item["color"])
        r, g, b = parse_hex(color)
        names.append(name)
        rs.append(r); gs.append(g); bs.append(b)
        rgbs.append((r << 16) | (g << 8) | b)

    N = len(names)
    G = args.grid
    if G <= 1 or G > 256:
        raise ValueError("--grid must be in 2..256")

    # LUT maps each grid cell center to nearest named color by RGB euclidean distance.
    # Quantization:
    #   bin = round(channel / 255 * (G-1))
    # We'll store lut[ri*G*G + gi*G + bi] = best color index (0..N-1)
    lut = [0] * (G * G * G)

    # Precompute grid center values for each bin (0..G-1)
    # center = round(bin * 255 / (G-1))
    centers = [int(round(i * 255 / (G - 1))) for i in range(G)]

    for ri in range(G):
        r0 = centers[ri]
        for gi in range(G):
            g0 = centers[gi]
            for bi in range(G):
                b0 = centers[bi]

                best = 0
                bestd = 1e18
                for i in range(N):
                    dr = r0 - rs[i]
                    dg = g0 - gs[i]
                    db = b0 - bs[i]
                    d = dr*dr + dg*dg + db*db  # squared euclidean (no sqrt needed)
                    if d < bestd:
                        bestd = d
                        best = i

                lut[ri*G*G + gi*G + bi] = best

    outp = Path(args.outp)
    outp.parent.mkdir(parents=True, exist_ok=True)

    with outp.open("w", encoding="utf-8") as w:
        w.write(f"package {args.pkg}\n\n")
        w.write("// AUTO-GENERATED. DO NOT EDIT.\n")
        w.write(f"// Source: {Path(args.inp).name}\n")
        w.write(f"// RGB LUT: grid={G}, entries={G*G*G}, colors={N}\n\n")
        w.write(f"internal object {args.obj} {{\n")
        w.write(f"  const val GRID: Int = {G}\n\n")

        w.write("  val names: Array<String> = arrayOf(\n")
        for n in names:
            w.write(f"    \"{esc_kotlin(n)}\",\n")
        w.write("  )\n\n")

        w.write("  // packed 0xRRGGBB\n")
        w.write("  val rgb: IntArray = intArrayOf(\n")
        for v in rgbs:
            w.write(f"    0x{v:06X},\n")
        w.write("  )\n\n")

        # Store LUT as ShortArray if N <= 32767 else IntArray
        if N <= 32767:
            w.write("  // LUT index -> color index (Short)\n")
            w.write("  val lut: ShortArray = shortArrayOf(\n")
            for v in lut:
                w.write(f"    {v},\n")
            w.write("  )\n")
        else:
            w.write("  // LUT index -> color index (Int)\n")
            w.write("  val lut: IntArray = intArrayOf(\n")
            for v in lut:
                w.write(f"    {v},\n")
            w.write("  )\n")

        w.write("}\n")

    print(f"OK: wrote {outp} (grid={G}, lut={G*G*G} entries, colors={N})")

if __name__ == "__main__":
    main()
