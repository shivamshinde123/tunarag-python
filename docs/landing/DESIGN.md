# TunaRAG landing page: design reference

> A terminal typeset on white paper

Adapted from the Vercel style reference on Refero Styles
(https://styles.refero.design/style/f24daf3a-d43f-4dec-85a9-8ac1d5148a03).
It borrows the visual system only. The page does not use Vercel's name, triangle mark or brand assets.
TunaRAG uses its own slider glyph.

## Principles

- Monochrome: a near-white canvas, near-black type and hairline borders. The only colour is
  Terminal Green, used for confirmations and short emphasised phrases.
- Two type families. Geist handles reading text and Geist Mono handles labels. Labels, metadata
  and code are always mono, uppercase where they act as labels, and 11–13px.
- Depth comes from tone (`#fafafa` → `#ffffff` → `#171717`) and hairline rings, never from drop shadows.
- The terminal is the demo. Code and run output serve as the product imagery, with no photos or
  illustrations.
- Work on a 4px grid with compact density and generous gaps (96–128px) between sections.

## Tokens

| Token | Value | Role |
|---|---|---|
| `--paper` | `#fafafa` | Page canvas |
| `--white` | `#ffffff` | Cards, code panels |
| `--hairline` | `#ebebeb` | 1px borders |
| `--smoke` | `#a8a8a8` | Placeholder, tertiary |
| `--slate` | `#7d7d7d` | Integration strip names |
| `--stone` | `#666666` | Captions, helper text |
| `--charcoal` | `#4d4d4d` | Body copy |
| `--obsidian` | `#171717` | Headings, primary buttons, inverted card |
| `--carbon` | `#000000` | Brand glyph only |
| `--green` | `#297a3a` | ✓ confirmations, accent phrases |

Type scale: eyebrow 11px mono +0.071em uppercase · caption 13px · body 16px/1.5 · heading
30px/1.1 −1.5px · display 56–64px/1.0 −0.06em at weight 450 (never above 500).

Radius: 6px for cards and buttons, 9999px only for nav pills. Card ring:
`0 0 0 1px rgba(0,0,0,.08), 0 0 0 2px #fafafa`. Ghost ring: `0 0 0 1px #ebebeb`.

Layout: content is capped at 1280px, with 24–48px gutters (16px on phones). The nav is 64px,
sticky and blurred, with no bottom border.

## Components

- **Filled button**: `#171717` with white text, 14px, 6px radius. This is the single primary action.
- **Ghost button**: transparent with a `#ebebeb` ring and `#4d4d4d` text.
- **Eyebrow**: Geist Mono, 11px, uppercase, 12px above the heading it introduces.
- **CLI panel**: a white card in 12–13px mono. Commands start with `›` and confirmations with a
  green `✓`.
- **Bordered card**: a white card with the ring above, a 30px title and 14–16px charcoal body copy.
- **Inverted card**: `#171717` with white text. Use at most one per grid.
- **Integration strip**: framework names in Geist, `#7d7d7d`, on one row with gaps of 24–32px.

## Don'ts

- Do not add chromatic colour beyond Terminal Green.
- Do not use radius above 6px on rectangles.
- Do not use drop shadows.
- Do not use bold display type.
- Do not put labels in sans or body copy in mono.
