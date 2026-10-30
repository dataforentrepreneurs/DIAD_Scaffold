# 🎨 DIAD Company Logo & Favicon Assets

Place your company logo files in this folder to customize the onboarding dashboard and chatbot interfaces.

## File Naming Conventions:

1. **`logo_light.png`** (or `.svg` / `.jpg`):
   - Logo optimized for light background themes.
   - Recommended resolution: 200x50px or 400x100px (PNG with transparent background).

2. **`logo_dark.png`** (or `.svg` / `.jpg`):
   - Logo optimized for dark background themes.
   - Recommended resolution: 200x50px or 400x100px (PNG with transparent background).

3. **`favicon.ico`** (placed in `assets/favicon.ico`):
   - Browser tab icon.
   - Recommended resolution: 32x32px or 64x64px.

---

### How to generate `favicon.ico`:
Once you place `logo_light.png` or `logo_dark.png` in this folder, you can run:
```powershell
python scripts/generate_favicon.py
```
This script will automatically generate `assets/favicon.ico` from your uploaded logo!
