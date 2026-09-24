# Argus UI Plan — "Tropical Cyberpunk" Investigation Browser

Target: static Next.js on Vercel. Data: `web/public/data/*.json` only (25 bundles + `_ablation.json`).
Goal: judges in awe, zero invented facts, everything builds and deploys.

---

## 1. Design language

**Palette (colors only, from `HHGOA_UI_THEME.md` — none of its card/pass concepts):**

| Token | Hex | Role |
|---|---|---|
| Cyber dark forest | `#022B1F` / `#041F13` | Page background / canvas base |
| Primary green | `#0B6839` | Aurora tint, deep panel gradients |
| Deep jungle | `#075029` | Panel depth, borders |
| Sunset gold | `#F4C93B` | Primary accent, CTAs, uncertain verdicts |
| Gold light | `#FEE101` | CTA hover, route badges |
| Neon pink | `#FF0080` | Fraud verdicts, alerts, high-risk flags |
| Cream | `#FFFBE8` | Primary text |
| Sage | `#8EB89B` | Secondary text, neutral status |
| Ink | `#111111` | Deep shadows |

**Typography:** Space Grotesk (display/headings), JetBrains Mono (IDs, probabilities, timestamps), Figtree (body). Via `next/font/google`. **Plus Fraunces (900, uppercase)** — only for the small footer lockup echo (§6); the main band uses the wordmark artwork.

**Signature gradient (fraud-probability gauge):** `linear-gradient(90deg, #8EB89B 0%, #F4C93B 50%, #FF0080 100%)` on a `#021D15` track — straight from the theme file.

---

## 2. Stack

Next.js App Router + Tailwind, `output: 'export'` (static). `framer-motion` (required by the picked components).
CSS custom properties are the source of truth for theme tokens (in `globals.css`), mapped into `tailwind.config` extend.

---

## 3. Component picks — every piece has a link

All picks are **free, MIT, no attribution required**. The worker installs each via the exact CLI command on its doc page (patterns below; doc page is authoritative).

### VengeanceUI (https://www.vengenceui.com) — setup: https://www.vengenceui.com/docs/install-nextjs

| UI element | Component | Link | Install pattern |
|---|---|---|---|
| Landing hero background | Aurora Hero | https://www.vengenceui.com/components/aurora-hero | `npx shadcn@latest add @vengeanceui/aurora-hero` |
| All six panel cards | Glow Border Card | https://www.vengenceui.com/components/glow-border-card | `npx shadcn@latest add @vengeanceui/glow-border-card` |
| Animated stat numbers (hero stats, gauge readout) | Animated Number | https://www.vengenceui.com/components/animated-number | `npx shadcn@latest add @vengeanceui/animated-number` |
| Landing case grid (25 cases) | Agent Bento Grid | https://www.vengenceui.com/components/agent-bento-grid | `npx shadcn@latest add @vengeanceui/agent-bento-grid` |
| Primary CTAs | Radial Glow Button | https://www.vengenceui.com/components/radial-glow-button | `npx shadcn@latest add @vengeanceui/radial-glow-button` |

### unlumen UI (https://ui.unlumen.com) — free MIT tier

| UI element | Component | Link | Install pattern |
|---|---|---|---|
| Verdict pills, LIVE/RECORDED dots | Glowing Badge | https://ui.unlumen.com/docs/ui/unlumen/glowing-badge | `npx shadcn@latest add @unlumen-ui/glowing-badge` |
| Hero wordmark reveal | Scramble Text | https://ui.unlumen.com/docs/ui/unlumen/scramble-text | `npx shadcn@latest add @unlumen-ui/scramble-text` |
| Section headings on scroll | Text Reveal | https://ui.unlumen.com/docs/ui/unlumen/text-reveal | `npx shadcn@latest add @unlumen-ui/text-reveal` |
| Frosted scroll edges on trace feed | Progressive Blur | https://ui.unlumen.com/docs/ui/unlumen/progressive-blur | `npx shadcn@latest add @unlumen-ui/progressive-blur` |

---

## 4. Custom builds (no library had these — all confirmed absent)

- **Confidence arc gauge** — hand-built SVG arc, theme gradient fill, animated sweep + Animated Number readout. The centerpiece of Panel 4.
- **Case progression timeline** — hand-built vertical timeline (gold-dim spine, verdict-colored nodes, mono probability chips).
- **Evidence table** — hand-built, theme table tokens (cream rows, sage headers, pink/gold source chips).
- **Tool-trace replay feed** — hand-built staggered reveal on "Replay investigation" click (framer-motion, already a dependency), Progressive Blur on scroll edges.
- **"The Ring" network visualization** (landing) — hand-built SVG: 19 card-nodes + 1 shared-device hub for HHG-014, edges draw in on scroll, fraud nodes pulse pink. Deterministic layout, no physics engine.

---

## 5. Deliberate cuts — what we are NOT using and why

- **liquid-glass-js** (https://github.com/dashersw/liquid-glass-js) — the *real* iPhone liquid-glass refraction, but demo-grade: 1 commit, no React wrapper, no npm package, per-instance WebGL page-capture cost, "performance optimizations unimplemented." CSS `backdrop-filter` glass + Glow Border Card gets 90% of the look at zero risk.
- **react-three-fiber** (https://github.com/pmndrs/react-three-fiber) — a 3D renderer, not a component kit; nothing drop-in for our panels. A DIY 3D hero is worker risk with no fallback. The SVG ring viz covers the "graph" wow safely.
- **shadergradient** (https://github.com/ruucm/shadergradient) — beautiful but drags the full three.js stack for a background Aurora Hero does dependency-free.
- **liquid-logo** (https://github.com/collidingScopes/liquid-logo) — a one-off demo toy, not a component; nothing drop-in for Next.js. Scramble-text wordmark instead.
- **Skiper UI** (https://skiper-ui.com) — its timeline, bento, and text-reveal components are all **paid ($129 Pro)** and the free tier demands attribution. VengeanceUI + unlumen cover every need free with no attribution.
- **SmoothUI** (https://smoothui.dev) — catalog mostly unverifiable (JS-rendered), nothing we need that isn't covered above.

---

## 6. Landing page (`/`) — section by section

0. **MANDATORY brand band — "Hacker House Goa" lockup** (faithful reproduction of the reference artwork; see §6a). Full-bleed, at the very top of the page, above the hero. This is event branding — non-negotiable, pixel-faithful to the reference.
1. **Hero** — Aurora Hero background tinted deep green + gold. Scramble-text "ARGUS" wordmark (cream, Space Grotesk). Tagline: "Agentic fraud investigation on TigerGraph." Sub: "25 investigations. 590,742 transactions. One graph." Animated stat row: 590,742 transactions · 5,565 closed cases · 25 investigations · 21 fraud findings. CTAs: gold Radial Glow Button "Enter the investigations" + outline "How it works."
2. **"The Ring"** — full-width section, dark. SVG network viz of HHG-014: 19 pink-pulsing card nodes around the shared-proxy hub, edges drawing on scroll. Caption with real bundle stats (fraud 0.996, SAR filed). This is the awe moment — it *is* the product (graph investigation).
3. **Innovations** — 4 glass cards: Autonomous Monitor (5 D9 discoveries) · Case Memory (HHG-012 ablation 0.0454 → 0.9838) · Expected-Value Economics · Deterministic Counterfactuals. Each card: one-line description + the headline number.
4. **Case grid** — Agent Bento Grid, 25 tiles. HHG-014 / HHG-012 / HHG-017 as featured large tiles. Verdict pills via Glowing Badge (pink fraud / sage legitimate / gold uncertain). Bonus tiles badged "Innovation · D9" (gold).
5. **Footer** — compact echo of the brand band: small gold Fraunces "HACKER HOUSE" + the pink sticker at 48px + mono line "GOA, INDIA · 28 – 31 OCT 2026". Below it, the honest label: "Recorded investigations — replayed from live TigerGraph runs, not live execution." Selection color pink (theme).

## 6a. MANDATORY brand band spec — "Hacker House Goa" lockup

Faithful reproduction of the reference artwork Parv supplied (gold serif HACKER HOUSE on deep green, pink गोवा sticker, mono info strip). Do NOT restyle it — match the reference.

- **Container:** full-bleed band, background primary green `#0B6839`, padding ~`clamp(2rem, 6vw, 5rem)` top/bottom. Bottom edge: 1px gold rule (`#F4C93B` at 40% opacity) separating it from the hero.
- **Wordmark:** the actual artwork `web/public/brand/Hacker-house.png` (gold serif on transparency, 1148×237 — use as-is, do NOT recolor, do NOT substitute a font). Displayed centered at `width: min(92vw, 1100px)`, height auto. It must read instantly like the poster — no scramble animation on it.
- **Pink sticker:** asset `web/public/brand/goa_hindi.svg` (complete artwork: gold `#FEE101` lettering with neon-pink `#FF0080` outline — use as-is, do NOT recolor). Absolutely positioned overlapping the wordmark's right-center (as in the reference), rotated `-8deg`, width `clamp(90px, 12vw, 170px)`, with a soft drop-shadow for lift. On mobile it may sit slightly smaller but must still overlap the wordmark.
- **Mono strip:** below the wordmark, JetBrains Mono, gold `#F4C93B`, uppercase, `letter-spacing: 0.18em`, small (`0.75rem`). Left: `GOA, INDIA · 28 – 31 OCT 2026`. Right: `2:47 PM STUDIO`. Space-between layout; stack on mobile.
- **`2-47.svg` asset:** open `web/public/brand/2-47.svg` and look at it. It is gold artwork — if it depicts the "2:47" time mark, use it in place of the right-side "2:47 PM STUDIO" text at matching x-height; if it is any other HH-brand artwork, place it in the site footer next to the compact lockup echo; never invent a use for it, and if it is unusable, report that and continue.
- **Entrance:** subtle — fade/slide-up on load (200–400ms), no heavy effects. The poster's boldness IS the effect.

## 7. Case page (`/case/[id]`) — the six panels

Every panel is a Glow Border Card (glass: `rgba(4,31,19,.55)`, `blur(20px)`, hairline gold-dim border; glow tint follows verdict: pink/sage/gold).

1. **Investigation** — trigger card (case ID mono, card, amounts, trigger text) + trace replay feed with "Replay investigation" gold button. Rows: query name (mono gold) → result summary (cream) → latency (sage).
2. **Case progression** — vertical timeline: evidence rounds with post-query probabilities → stopping decision (rule fired: hard stop 0.85/0.15, marginal-value gate, or cap) → final actions.
3. **Evidence** — table: ID (E1…En) · claim · source · type · supports. Source chips pink/gold.
4. **Uncertainty** — SVG arc gauge (theme gradient) + Animated Number + per-feature contribution bars + economics `reading` as a designed strip + unknowns or "not recorded."
5. **Recommendations** — NBA initial vs. final side-by-side, `what_changed` highlighted gold, counterfactual `sentence` as a callout with gold left-border.
6. **Next actions** — action list with route badges (AUTO/L1/L2 in gold-tint pills per theme) + policy-rule citations (mono sage).
- **HHG-012 only:** ablation strip — with-memory vs. without-memory bars (0.0454 → 0.9838), verdict flip, labeled "Case-memory ablation."

## 8. Color assignments — every element

| Element | Color |
|---|---|
| Page background | `#022B1F` with `#0B6839` radial vignettes |
| Panel cards (glass) | `rgba(4,31,19,.55)` + blur(20px) + `rgba(244,201,59,.18)` border |
| Headings | Cream `#FFFBE8`, Space Grotesk |
| Body copy | Sage `#8EB89B`, Figtree |
| IDs / probabilities / timestamps | Cream, JetBrains Mono, tabular-nums |
| Primary CTA | Gold `#F4C93B` bg, `#041F13` text; hover `#FEE101` |
| Fraud accents (pills, nodes, gauge zone) | Pink `#FF0080` |
| Legitimate accents | Sage `#8EB89B` on `#062C1B` (theme's approved badge) |
| Uncertain accents | Gold `#F4C93B` |
| Gauge track / fill | `#021D15` track, sage→gold→pink gradient fill |
| Route badges (AUTO/L1/L2) | `bg-[#FEE101]/15 text-[#FEE101] border-[#EDD723]` |
| D9 bonus badges | Gold tint (pink is reserved for fraud) |
| Timeline spine | Gold-dim `#EDD723` at 40% |
| Text selection | Pink bg, white text |
| Trace query names | Mono gold; latencies sage |

---

## 9. Data contract (non-negotiable)

Only `web/public/data/*.json` + `_ablation.json`. Every rendered value traceable to a bundle file. No hardcoded case content in source. Missing field → "not recorded", never invented.

## 10. Acceptance

`npm run build` clean with `output: 'export'`; all 25 case pages static; trace replay animates; bento grid + ring viz render; **brand band reproduces the reference lockup (green bg, gold wordmark artwork, pink sticker overlapping, mono date strip)**; spot-check HHG-014/017/BONUS_003 values against bundles; nothing committed.
