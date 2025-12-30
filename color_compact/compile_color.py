#!/usr/bin/env python3
# gen_color_bins_kt.py
#
# Convert a JSON list of {"name": "...", "color": "#RRGGBB"} into a Kotlin .kt file
# that contains:
# - names[] (Array<String>)
# - LAB arrays (FloatArray)
# - LAB 3D bin index (bucketKey/bucketStart/bucketLen/bucketItems)
#
# Usage:
#   python gen_color_bins_kt.py --in colors.json --out ColorIndex.kt --package com.primortex.color.service --object ColorIndex
#
# Optional bin sizes:
#   --lstep 2.0 --astep 4.0 --bstep 4.0
#
# Input JSON example:
# [
#   {"name":"Absolute Zero","color":"#0048BA"},
#   {"name":"Acid","color":"#B0BF1A"}
# ]

import argparse
import json
import math
from pathlib import Path
from typing import Dict, List, Tuple


def clamp_int(v: int, lo: int, hi: int) -> int:
    return lo if v < lo else hi if v > hi else v


def parse_hex_color(s: str) -> Tuple[int, int, int]:
    t = str(s).strip()
    if t.startswith("#"):
        t = t[1:]
    if len(t) != 6 or any(c not in "0123456789abcdefABCDEF" for c in t):
        raise ValueError(f"Invalid hex color: {s}")
    return int(t[0:2], 16), int(t[2:4], 16), int(t[4:6], 16)


def srgb_to_linear(u: float) -> float:
    return ((u + 0.055) / 1.055) ** 2.4 if u > 0.04045 else (u / 12.92)


def rgb_to_lab(r: int, g: int, b: int) -> Tuple[float, float, float]:
    rr = srgb_to_linear(r / 255.0)
    gg = srgb_to_linear(g / 255.0)
    bb = srgb_to_linear(b / 255.0)

    # sRGB -> XYZ (D65)
    x = (0.4124 * rr + 0.3576 * gg + 0.1805 * bb) / 0.95047
    y = (0.2126 * rr + 0.7152 * gg + 0.0722 * bb)
    z = (0.0193 * rr + 0.1192 * gg + 0.9505 * bb) / 1.08883

    def f(t: float) -> float:
        return t ** (1 / 3) if t > 0.008856 else (7.787 * t + 16.0 / 116.0)

    fx, fy, fz = f(x), f(y), f(z)
    L = 116.0 * fy - 16.0
    A = 500.0 * (fx - fy)
    B = 200.0 * (fy - fz)
    return L, A, B


def lab_key(L: float, A: float, B: float, lstep: float, astep: float, bstep: float) -> int:
    lmax = int(100.0 / lstep)
    amax = int(256.0 / astep) - 1
    bmax = int(256.0 / bstep) - 1

    lbin = clamp_int(int(L / lstep), 0, lmax)
    abin = clamp_int(int((A + 128.0) / astep), 0, amax)
    bbin = clamp_int(int((B + 128.0) / bstep), 0, bmax)

    return (lbin << 12) | (abin << 6) | bbin


def esc_kotlin(s: str) -> str:
    return str(s).replace("\\", "\\\\").replace("\"", "\\\"")


def write_kotlin_array_of_strings(w, indent: str, name: str, arr: List[str]) -> None:
    w.write(f"{indent}val {name}: Array<String> = arrayOf(\n")
    for s in arr:
        w.write(f'{indent}  "{esc_kotlin(s)}",\n')
    w.write(f"{indent})\n\n")


def write_kotlin_float_array(w, indent: str, name: str, arr: List[float]) -> None:
    w.write(f"{indent}val {name}: FloatArray = floatArrayOf(\n")
    for v in arr:
        # keep enough precision but not insane
        w.write(f"{indent}  {v:.6f}f,\n")
    w.write(f"{indent})\n\n")


def write_kotlin_int_array(w, indent: str, name: str, arr: List[int]) -> None:
    w.write(f"{indent}val {name}: IntArray = intArrayOf(\n")
    for v in arr:
        w.write(f"{indent}  {int(v)},\n")
    w.write(f"{indent})\n\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", required=True, help="Input JSON file")
    ap.add_argument("--out", dest="outp", required=True, help="Output Kotlin .kt file")
    ap.add_argument("--package", dest="pkg", required=True, help="Kotlin package name")
    ap.add_argument("--object", dest="obj", default="ColorIndex", help="Kotlin object name (default: ColorIndex)")
    ap.add_argument("--lstep", type=float, default=2.0)
    ap.add_argument("--astep", type=float, default=4.0)
    ap.add_argument("--bstep", type=float, default=4.0)
    args = ap.parse_args()

    inp = Path(args.inp)
    outp = Path(args.outp)

    raw = json.loads(inp.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("Input JSON must be a list")

    names: List[str] = []
    Ls: List[float] = []
    As: List[float] = []
    Bs: List[float] = []
    buckets: Dict[int, List[int]] = {}

    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            raise ValueError(f"Item {i} must be an object")
        if "name" not in item or "color" not in item:
            raise ValueError(f"Item {i} must have keys: name, color")

        name = str(item["name"])
        r, g, b = parse_hex_color(item["color"])
        L, A, B = rgb_to_lab(r, g, b)

        idx = len(names)
        names.append(name)
        Ls.append(L)
        As.append(A)
        Bs.append(B)

        k = lab_key(L, A, B, args.lstep, args.astep, args.bstep)
        buckets.setdefault(k, []).append(idx)

    # Build bucket arrays (sorted by key)
    keys = sorted(buckets.keys())
    bucket_key: List[int] = []
    bucket_start: List[int] = []
    bucket_len: List[int] = []
    bucket_items: List[int] = []

    start = 0
    for k in keys:
        idxs = buckets[k]
        bucket_key.append(k)
        bucket_start.append(start)
        bucket_len.append(len(idxs))
        bucket_items.extend(idxs)
        start += len(idxs)

    outp.parent.mkdir(parents=True, exist_ok=True)
    with outp.open("w", encoding="utf-8") as w:
        w.write(f"package {args.pkg}\n\n")
        w.write("// AUTO-GENERATED. DO NOT EDIT.\n")
        w.write(f"// Source: {inp.name}\n")
        w.write(f"// Colors: {len(names)}\n")
        w.write(f"// Binning: L_STEP={args.lstep}, A_STEP={args.astep}, B_STEP={args.bstep}\n\n")
        w.write(f"internal object {args.obj} {{\n")
        indent = "  "
        w.write(f"{indent}const val L_STEP: Float = {args.lstep}f\n")
        w.write(f"{indent}const val A_STEP: Float = {args.astep}f\n")
        w.write(f"{indent}const val B_STEP: Float = {args.bstep}f\n\n")

        write_kotlin_array_of_strings(w, indent, "names", names)
        write_kotlin_float_array(w, indent, "L", Ls)
        write_kotlin_float_array(w, indent, "A", As)
        write_kotlin_float_array(w, indent, "B", Bs)

        write_kotlin_int_array(w, indent, "bucketKey", bucket_key)
        write_kotlin_int_array(w, indent, "bucketStart", bucket_start)
        write_kotlin_int_array(w, indent, "bucketLen", bucket_len)
        write_kotlin_int_array(w, indent, "bucketItems", bucket_items)

        w.write("}\n")

    print(f"OK: wrote {outp}  colors={len(names)} buckets={len(bucket_key)} items={len(bucket_items)}")


if __name__ == "__main__":
    main()
