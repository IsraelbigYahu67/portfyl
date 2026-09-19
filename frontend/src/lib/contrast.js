function srgbToLinear(c) {
  const v = c / 255;
  return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
}

function relativeLuminanceRGB({ r, g, b }) {
  return 0.2126 * srgbToLinear(r) + 0.7152 * srgbToLinear(g) + 0.0722 * srgbToLinear(b);
}

function expandHex(hex) {
  return hex.length === 3 ? hex.split("").map((c) => c + c).join("") : hex;
}

/**
 * Resolves a CSS color string to opaque {r,g,b}. Accepts #rgb, #rrggbb, and
 * rgb()/rgba(). A translucent rgba() is composited channel-by-channel over
 * `backdrop` (itself resolved recursively) since luminance math requires an
 * opaque color.
 */
export function parseColor(color, backdrop) {
  const value = String(color).trim();

  const hexMatch = value.match(/^#([0-9a-f]{3}|[0-9a-f]{6})$/i);
  if (hexMatch) {
    const hex = expandHex(hexMatch[1]);
    return {
      r: parseInt(hex.substring(0, 2), 16),
      g: parseInt(hex.substring(2, 4), 16),
      b: parseInt(hex.substring(4, 6), 16),
    };
  }

  const rgbaMatch = value.match(/^rgba?\(\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)\s*(?:,\s*([\d.]+)\s*)?\)$/i);
  if (rgbaMatch) {
    const [, rStr, gStr, bStr, aStr] = rgbaMatch;
    const r = Number(rStr);
    const g = Number(gStr);
    const b = Number(bStr);
    const alpha = aStr === undefined ? 1 : Number(aStr);
    if (alpha >= 1) return { r, g, b };
    if (!backdrop) {
      throw new Error(`parseColor: translucent color "${color}" requires a backdrop to composite against`);
    }
    const bg = parseColor(backdrop);
    return {
      r: Math.round(alpha * r + (1 - alpha) * bg.r),
      g: Math.round(alpha * g + (1 - alpha) * bg.g),
      b: Math.round(alpha * b + (1 - alpha) * bg.b),
    };
  }

  throw new Error(`parseColor: unsupported color "${color}" (expected #rgb, #rrggbb, rgb(), or rgba())`);
}

/**
 * WCAG contrast ratio between two colors. `backdrop` composites a
 * translucent `foreground`; it defaults to `background` since that is what
 * a translucent foreground almost always sits on.
 */
export function contrastRatio(foreground, background, backdrop) {
  const bg = parseColor(background);
  const fg = parseColor(foreground, backdrop ?? background);
  const lA = relativeLuminanceRGB(fg);
  const lB = relativeLuminanceRGB(bg);
  const lighter = Math.max(lA, lB);
  const darker = Math.min(lA, lB);
  return (lighter + 0.05) / (darker + 0.05);
}
