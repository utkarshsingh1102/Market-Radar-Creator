"""
CLI renderer — no server needed.

Usage:
    python -m scripts.render_cli brief.json output.png
    python -m scripts.render_cli brief.json          # writes to storage/outputs/

The CLI resolves icons synchronously (wraps async in asyncio.run).
All icon upload_ids must reference files in storage/uploads/.
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

# Ensure project root is on sys.path when run as a script
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.config import settings, tokens
from app.orchestrator import Orchestrator
from app.schemas import BriefIn
from app.storage.local import LocalAssetStore


async def _run(brief_path: Path, output_path: Path) -> None:
    raw = json.loads(brief_path.read_text())
    brief = BriefIn.model_validate(raw)

    store = LocalAssetStore(settings.storage_root)
    orchestrator = Orchestrator(store)

    print(f"Creating draft for: {brief.main_game.name}")
    draft = await orchestrator.create_draft(brief)

    png = await orchestrator.export_draft(draft)
    output_path.write_bytes(png)
    print(f"Rendered → {output_path}  ({len(png):,} bytes)")
    print(f"Draft ID: {draft.id}")


def main() -> None:
    args = sys.argv[1:]
    if not args:
        print("Usage: python -m scripts.render_cli <brief.json> [output.png]")
        sys.exit(1)

    brief_path = Path(args[0])
    if not brief_path.exists():
        print(f"Error: {brief_path} not found")
        sys.exit(1)

    if len(args) >= 2:
        output_path = Path(args[1])
    else:
        output_path = settings.storage_root / "outputs" / (brief_path.stem + "_out.png")
        output_path.parent.mkdir(parents=True, exist_ok=True)

    asyncio.run(_run(brief_path, output_path))


if __name__ == "__main__":
    main()
