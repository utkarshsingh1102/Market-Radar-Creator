"""
Calibration helper.
Overlays a reference JPG (from the PDF export) onto a rendered PNG so you can
visually compare spacing and tune design_tokens.yaml.

Usage:
    python -m scripts.calibrate reference.jpg rendered.png out_overlay.png [--opacity 0.4]
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def calibrate(ref_path: Path, render_path: Path, out_path: Path, opacity: float = 0.4) -> None:
    from PIL import Image

    ref = Image.open(ref_path).convert("RGBA").resize((1080, 1080))
    rendered = Image.open(render_path).convert("RGBA")

    # Blend: rendered base + semi-transparent reference overlay
    overlay = Image.blend(rendered, ref, alpha=opacity)
    overlay.save(out_path)
    print(f"Overlay written to {out_path}")


def main() -> None:
    import argparse
    p = argparse.ArgumentParser(description="Overlay reference image on rendered output")
    p.add_argument("reference", type=Path)
    p.add_argument("rendered", type=Path)
    p.add_argument("output", type=Path)
    p.add_argument("--opacity", type=float, default=0.4)
    args = p.parse_args()
    calibrate(args.reference, args.rendered, args.output, args.opacity)


if __name__ == "__main__":
    main()
