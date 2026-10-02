# NutriSense Frontend Landing Page & Design Tokens

This folder contains the complete, standalone frontend code, color palette definitions, and 3D typography tokens for the **NutriSense Cyber-Physical Nutrition Hub** landing page.

---

## 🎨 Color Palette & Design Tokens

| Token Name | HEX Code | RGB | Role / Usage |
|---|---|---|---|
| **Primary Emerald** | `#16a34a` | `rgb(22, 163, 74)` | Brand primary, CTA solid buttons, active navigation pill |
| **Forest Dark** | `#14532d` | `rgb(20, 83, 45)` | Brand typography, top pill badges, deep contrast text |
| **Fresh Mint** | `#dcfce7` | `rgb(220, 252, 231)` | Avatar/icon badge background, ambient glow halo |
| **Morning Lime** | `#84cc16` | `rgb(132, 204, 22)` | Radial organic gradient (top-left) |
| **Citrus Amber** | `#f59e0b` | `rgb(245, 158, 11)` | Radial organic gradient (top-right) |
| **Soft Mint Base** | `#f0fdf4` | `rgb(240, 253, 244)` | Linear gradient base start |
| **Mist Sage Base** | `#daf0e2` | `rgb(218, 240, 226)` | Linear gradient base end |
| **Deep Ink Text** | `#0f172a` | `rgb(15, 23, 42)` | Main headings and descriptions |

---

## 🖼️ Background Formula (Zero Grid Lines, Lush Organic Gradient)
```css
background: 
  radial-gradient(ellipse at 50% 12%, rgba(34, 197, 94, 0.22) 0%, transparent 60%),
  radial-gradient(circle at 12% 25%, rgba(132, 204, 22, 0.15) 0%, transparent 45%),
  radial-gradient(circle at 88% 18%, rgba(245, 158, 11, 0.14) 0%, transparent 40%),
  radial-gradient(circle at 50% 92%, rgba(16, 185, 129, 0.20) 0%, transparent 50%),
  linear-gradient(150deg, #f0fdf4 0%, #e6f7ec 45%, #daf0e2 100%);
background-attachment: fixed;
```

---

## ✨ 3D Typography Recipe (Solid White Perimeter Pop)

### 1. Script Subtitle (`Caveat` 700):
```css
text-shadow: 
  -2px -2px 0 #ffffff,
   0   -2px 0 #ffffff,
   2px -2px 0 #ffffff,
   2px  0   0 #ffffff,
   2px  2px 0 #ffffff,
   0    2px 0 #ffffff,
  -2px  2px 0 #ffffff,
  -2px  0   0 #ffffff,
   0 3px 0 #ffffff,
   0 4px 0 #ffffff,
   0 5px 0 #dcfce7,
   0 8px 20px rgba(22, 163, 74, 0.35);
```

### 2. Main Title (`Outfit` 800):
```css
text-shadow: 
  -2.5px -2.5px 0 #ffffff,
   0     -2.5px 0 #ffffff,
   2.5px -2.5px 0 #ffffff,
   2.5px  0     0 #ffffff,
   2.5px  2.5px 0 #ffffff,
   0      2.5px 0 #ffffff,
  -2.5px  2.5px 0 #ffffff,
  -2.5px  0     0 #ffffff,
   0 3.5px 0 #ffffff,
   0 5px   0 #ffffff,
   0 6px   0 #cbd5e1,
   0 10px 24px rgba(0, 0, 0, 0.2);
```

---

## 📂 Directory Contents
- `index.html`: Standalone, self-contained landing page.
- `styles.css`: Complete CSS design system and tokens.
- `colors.json`: Structured design tokens format.
- `assets/`:
  - `hero_bottom_official.png`: 100% original uncut bottom produce foundation.
  - `hero_curved_accent.png`: Original fruit & vegetable arch.
  - `design.jpg`: Original wireframe reference composition.
