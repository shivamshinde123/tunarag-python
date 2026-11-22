# TunaRAG landing page: design reference

> Warm broadsheet on cream paper, with pastel halos

Adapted from the Popcorn style reference on Refero Styles
(https://styles.refero.design/style/93fe74fd-bac8-4d13-9d5b-3b5e242f74e6).
It borrows the visual system only. The page does not use Popcorn's name, logo or product imagery.
TunaRAG uses its own slider glyph, and its product visuals are code and result panels instead of phones.

## Principles

- A serif headline does the emotional work. Display and section titles are set in a high-contrast
  serif (weight 400, tight tracking). Everything functional is set in a quiet humanist sans.
- The page sits on a warm cream canvas. Lifted surfaces are white and carry a single soft shadow.
- Colour comes from pastels only. The conic Spectrum Wash (mint, sage, sky, cream, blush, lilac)
  forms halos behind the product visuals and fills the feature illustration tiles. The Lilac Field
  band marks a change of content zone. Mist Blue tints informational cards. Controls stay neutral.
- Interactive elements are pills (100px radius). Cards use 12px radius, feature cards 24px.
- The product is the hero. Overlapping, slightly rotated code and results panels float on a halo.

## Tokens

| Token | Value | Role |
|---|---|---|
| `--graphite` | `#393737` | Text, dark pill buttons, borders at low opacity |
| `--canvas` | `#f7f7f7` | Page background, badge fills |
| `--white` | `#ffffff` | Cards and panels |
| `--fog` | `#888787` | Muted helper text, captions |
| `--mist` | `#e9eff6` | Cool informational card tint |
| `--lilac` | `#f3f0f8` | Section-break band |
| `--wash` | conic 180deg: `#ebf6f2` `#e7f3e0` `#e5eff8` `#fef1d8` `#f7f4fa` `#f7dbe5` | Halos and illustration tiles only |

Deeper pastel tints such as mint `#cfeee3`, sky `#d6e6f7`, butter `#fbe7b8`, blush `#f5cfdc` and
lilac `#e4dcf3` may fill icon tiles and wash halos. They never colour text or controls.

Type: Source Serif 4 (substitute for Untitled Serif) at weight 400 for every heading of 30px and
above. The display is 84px with −0.03em tracking and line-height 1.0, and sections use 40–58px with
−0.025em. Inter (substitute for Messina Sans) handles body text at 16px/1.5, the 18px subheading at
−0.02em, 13px captions, and weight 600 for button labels. Never set the serif below 20px.

Elevation: the only shadow is `rgba(0,0,0,.05) 0 4px 20px`, and it is never stacked.

Layout: content is capped at 1200px, sections are about 96px apart, and phone gutters are 16px.
Hero and section titles are centred, while body copy and FAQ items are left-aligned.

## Components

- **Pill CTA**: graphite fill, white Inter 16px/600 text, 100px radius. This is the only filled button.
- **Status pill badge**: cream fill with a 1px graphite border, 13px text and the soft shadow. It sits
  above the hero headline.
- **Icon circle**: a 56px pill circle in cream with a 20%-graphite border and a single-tone line icon.
- **Feature card**: white, 24px radius, soft shadow, with an illustration tile in a pastel wash.
- **Product showcase**: two rotated white panels (code and ranked results) overlapping on a conic halo.
- **Lilac band**: a full-bleed `#f3f0f8` section holding three white cards.
- **FAQ accordion**: native `<details>` rows on white with a 15%-graphite hairline, no radius, and an
  18px serif-free question.

## Don'ts

- Do not use saturated colour on CTAs, links or text.
- Do not put gradients on buttons, badges or cards. Gradients belong only on halos and tiles.
- Do not use pure black text.
- Do not give interactive controls sharp corners.
- Do not use more than one shadow value.
- Do not set body line-height below 1.4.
