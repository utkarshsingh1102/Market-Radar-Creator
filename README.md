# Market Radar Forge

Automated 1080×1080 Instagram/LinkedIn post generator for the NextBigGames "Market Radar" series.

Give it a JSON brief (main game + 2–4 inspirations), get a pixel-perfect post.

---

## Quick Start

```bash
pip install fastapi "uvicorn[standard]" pydantic pydantic-settings pillow httpx pyyaml jinja2 python-multipart aiofiles
uvicorn app.main:app --reload
```

Open **http://localhost:8000** → fill the form → Generate → Edit → Export PNG.

### CLI (no server)
```bash
python3 -m scripts.render_cli tests/fixtures/briefs/sample_3.json out.png
```

### Docker
```bash
docker compose up
```

---

## Adding your assets (required for pixel-perfect output)

| File | What it is |
|------|-----------|
| `assets/fonts/title.ttf` | Bold/black title font (e.g. Montserrat Black) |
| `assets/fonts/body.ttf` | SemiBold body font (e.g. Montserrat SemiBold) |
| `assets/profile/vamsi.png` | Vamsi's avatar (any size, auto-cropped to circle) |
| `assets/icons/linkedin.png` | LinkedIn icon PNG (32×32 recommended) |
| `assets/frames/iphone_14.png` | iPhone frame PNG (optional — drawn programmatically if absent) |

---

## Design Tokens

All colors, fonts, and spacing live in `config/design_tokens.yaml`. Edit that file — zero code changes needed — to adjust the look.

---

## JSON Brief Schema

```json
{
  "main_game": {
    "name": "Airport Jam: Crowd Escape",
    "publisher": "Devrim Eribol",
    "screenshot": { "source": "upload", "upload_id": "screenshot.png" }
  },
  "inspirations": [
    { "name": "Pixel flow", "publisher": "loom games", "icon": { "source": "auto", "query": "Pixel Flow loom games" } },
    { "name": "Arrows by Lessmore", "icon": { "source": "auto", "query": "Arrows Lessmore" } },
    { "name": "Airport theme", "icon": { "source": "upload", "upload_id": "airport-icon.png" } }
  ],
  "meta": { "series_number": 34 }
}
```

- `inspirations`: 2–4 items (Pydantic enforced)
- `icon.source: "auto"` → fetches from iTunes Search API, cached by SHA-256
- `icon.source: "upload"` → reads from `storage/uploads/{upload_id}`

---

## API Reference

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/drafts` | Create draft from JSON brief |
| `GET` | `/drafts/{id}` | Get draft metadata + preview URL |
| `PATCH` | `/drafts/{id}/fields` | Update text fields, triggers re-render |
| `POST` | `/drafts/{id}/images/{slot}` | Replace image (`main_screenshot`, `inspiration_0_icon`, …) |
| `POST` | `/drafts/{id}/regenerate` | Force re-render |
| `GET` | `/drafts/{id}/export` | Download final PNG |
| `POST` | `/uploads` | Pre-upload an image, get `upload_id` back |

---

## Calibration

Compare a render against a reference page from the PDF:

```bash
python3 -m scripts.calibrate ilovepdf_pages-to-jpg/page-0003.jpg out.png overlay.png --opacity 0.4
```

Tune `config/design_tokens.yaml` until the overlay aligns.
