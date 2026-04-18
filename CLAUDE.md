# Claude Code Guidance — market-radar-forge

## What this project does
Generates 1080×1080 social media posts from a JSON brief. Pure Python rendering (Pillow), FastAPI backend, minimal HTMX + Alpine.js web UI.

## Design principles
1. **Single source of truth for styling:** all colors, fonts, spacing live in `config/design_tokens.yaml`. Never hardcode style values in `renderer/`.
2. **Storage is an interface.** Always go through `AssetStore`. Never write directly to `storage/`.
3. **Layout is computed, not hardcoded.** The adaptive layout engine handles 2/3/4 inspirations with one algorithm in `renderer/layout.py`. Don't add per-count branches in components.
4. **Async for I/O.** Icon fetching and HTTP handlers are async. Don't mix sync `requests` in.

## Phase discipline
Work one phase at a time (see PLAN.md §12). Don't start Phase N+1 until Phase N's tests pass.

## Gotchas
- Pillow draws fonts at exact pixel sizes — anti-aliasing differs slightly per platform. Golden PNG tests allow 2% diff.
- iTunes Search API rate-limits around 20 req/min per IP. Respect the cache.
- When adding a new component, put it in `renderer/components/`, give it a `render(img, tokens, ctx)` signature, and call it from `engine.py`.
- Font files are NOT committed. Drop TTF/OTF into `assets/fonts/` as `title.ttf` and `body.ttf`. The renderer falls back to Pillow's built-in default if missing.

## Adding custom fonts
Place files at:
- `assets/fonts/title.ttf` — bold/black weight title font (e.g. Montserrat Black)
- `assets/fonts/body.ttf` — semibold body font (e.g. Montserrat SemiBold)

## Adding profile assets
- `assets/profile/vamsi.png` — circular avatar (any size, will be cropped to circle)
- `assets/icons/linkedin.png` — LinkedIn icon (32×32 PNG recommended)

## Running locally
```bash
pip install -e .
uvicorn app.main:app --reload
# → http://localhost:8000
```

## CLI render (no server)
```bash
python -m scripts.render_cli tests/fixtures/briefs/sample_3.json out.png
```
