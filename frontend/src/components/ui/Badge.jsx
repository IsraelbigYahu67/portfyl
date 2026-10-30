// Status pill. Tone colors come only from tokens: a 16% tint of the tone
// token over the card surface, with the text in the tone token itself.
const TONE_TOKEN = {
  gain: "var(--gain)",
  loss: "var(--loss)",
  warn: "var(--chart-3)",
  info: "var(--chart-4)",
  neutral: "var(--chart-8)",
  brand: "var(--brand)",
};

// 12px floor: `sm` uses the financial-meta class, `md` is text-xs.
const SIZES = {
  sm: "financial-meta px-2 py-0.5 gap-1",
  md: "text-xs px-2.5 py-1 gap-1.5",
};

export function Badge({ tone = "neutral", size = "md", title, className = "", children }) {
  const token = TONE_TOKEN[tone] ?? TONE_TOKEN.neutral;
  return (
    <span
      data-tone={tone}
      title={title}
      className={`inline-flex items-center rounded-full font-sans font-semibold whitespace-nowrap ${SIZES[size] ?? SIZES.md} ${className}`}
      style={{
        color: token,
        background: `color-mix(in srgb, ${token} 16%, var(--surface-card))`,
      }}
    >
      {children}
    </span>
  );
}
