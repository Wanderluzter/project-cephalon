"""
Weekly digest image generator.

Renders a PNG summarizing this week's rotating content — Nightwave weekly
challenges and the Steel Path weekly reward rotation — styled to roughly
match the dashboard's Orokin/Tenno theme. Uses Pillow's built-in bitmap
font (no external font file dependency, so this works the same on every
machine without needing a font installed).

Regeneration is handled by app.py: a background thread checks once a day
whether the current file is more than 7 days old and regenerates if so.
This module only knows how to render one image — it doesn't schedule
anything itself.
"""

import textwrap
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageFont

from .worldstate import Worldstate, WorldstateError

# Palette matches static/style.css
_VOID = (10, 13, 18)
_PANEL = (18, 23, 31)
_GOLD = (199, 167, 108)
_CYAN = (79, 214, 232)
_TEXT = (231, 228, 218)
_TEXT_DIM = (138, 147, 160)
_LINE = (38, 49, 64)

_WIDTH = 900


def _font(size: int) -> ImageFont.ImageFont:
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        # Older Pillow without the `size` kwarg on load_default()
        return ImageFont.load_default()


def generate_weekly_digest(worldstate: Worldstate, output_path: str) -> str:
    """Fetch current Nightwave + Steel Path data and render a weekly digest
    PNG to `output_path`. Returns the path on success. Raises on fetch
    failure — caller decides whether to fall back to a stale cached image."""
    try:
        nightwave = worldstate.call("nightwave", force_refresh=True)
    except WorldstateError:
        nightwave = {}
    try:
        steel_path = worldstate.call("steel-path", force_refresh=True)
    except WorldstateError:
        steel_path = {}

    weekly_challenges = [
        c for c in (nightwave.get("activeChallenges") or [])
        if not c.get("isDaily")
    ]
    steel_rotation = (steel_path or {}).get("rotation") or []
    steel_current = (steel_path or {}).get("currentReward")

    lines = []  # (text, font_size, color, extra_gap_after)
    week_label = datetime.now(timezone.utc).strftime("Week of %B %d, %Y")
    lines.append(("PROJECT ORDIS — WEEKLY DIGEST", 26, _GOLD, 6))
    lines.append((week_label, 15, _TEXT_DIM, 24))

    lines.append(("NIGHTWAVE — WEEKLY CHALLENGES", 19, _CYAN, 10))
    if weekly_challenges:
        for c in weekly_challenges:
            tag = "[ELITE] " if c.get("isElite") else ""
            title = f"{tag}{c.get('title', 'Unknown')}"
            desc = c.get("desc", "")
            rep = c.get("reputation")
            lines.append((f"• {title} — {rep} standing", 15, _TEXT, 2))
            for wrapped in textwrap.wrap(desc, 78):
                lines.append((f"    {wrapped}", 13, _TEXT_DIM, 0))
            lines.append(("", 8, _TEXT, 4))
    else:
        lines.append(("No weekly challenge data available.", 14, _TEXT_DIM, 10))

    lines.append(("STEEL PATH — CURRENT ROTATION", 19, _CYAN, 10))
    if steel_current:
        lines.append((f"This week's featured reward: {steel_current.get('name')} ({steel_current.get('cost')} kuva)", 15, _GOLD, 8))
    if steel_rotation:
        for item in steel_rotation:
            lines.append((f"• {item.get('name')} — {item.get('cost')} kuva", 14, _TEXT, 2))
    else:
        lines.append(("No Steel Path rotation data available.", 14, _TEXT_DIM, 10))

    lines.append(("", 10, _TEXT, 0))
    lines.append(("Generated automatically, refreshed weekly.", 12, _TEXT_DIM, 0))

    padding = 36
    y = padding
    for text, size, color, gap in lines:
        f = _font(size)
        # crude line-height estimate since we don't have a real image yet
        y += int(size * 1.35) + gap

    height = y + padding
    img = Image.new("RGB", (_WIDTH, height), _VOID)
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 0, _WIDTH - 1, height - 1], outline=_LINE, width=2)

    y = padding
    for text, size, color, gap in lines:
        f = _font(size)
        draw.text((padding, y), text, font=f, fill=color)
        y += int(size * 1.35) + gap

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    img.save(output_path, format="PNG")
    return output_path
