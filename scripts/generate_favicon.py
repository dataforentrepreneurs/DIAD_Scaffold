"""
scripts/generate_favicon.py

Generates assets/favicon.ico from assets/logo/logo_light.png or logo_dark.png.
Uses PIL / Pillow if available, or creates an SVG fallback.
"""

from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parent.parent
LOGO_DIR = ROOT_DIR / "assets" / "logo"
FAVICON_PATH = ROOT_DIR / "assets" / "favicon.ico"

def generate_favicon():
    logo_file = None
    for candidate in ["logo_dark.png", "logo_light.png", "logo_dark.jpg", "logo_light.jpg"]:
        p = LOGO_DIR / candidate
        if p.exists():
            logo_file = p
            break

    if logo_file:
        try:
            from PIL import Image
            img = Image.open(logo_file)
            img.save(FAVICON_PATH, format="ICO", sizes=[(32, 32), (48, 48), (64, 64)])
            print(f"✅ Generated favicon.ico from {logo_file.name} -> {FAVICON_PATH}")
            return
        except Exception as e:
            print(f"⚠️ Pillow conversion failed ({e}). Creating default SVG favicon...")

    # Fallback SVG favicon if no PIL or no logo image found yet
    svg_content = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
  <rect width="100" height="100" rx="22" fill="#7f5af0"/>
  <text x="50" y="68" font-size="55" font-weight="bold" fill="#ffffff" text-anchor="middle" font-family="sans-serif">D</text>
</svg>"""
    svg_path = ROOT_DIR / "assets" / "favicon.svg"
    svg_path.parent.mkdir(parents=True, exist_ok=True)
    with open(svg_path, "w", encoding="utf-8") as f:
        f.write(svg_content)
    print(f"✅ Created default branding SVG favicon at {svg_path}")

if __name__ == "__main__":
    generate_favicon()
