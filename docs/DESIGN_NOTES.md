# UI-3 Design Notes — visual depth pass

Sources: `awesome-design-md` `design-md/elevenlabs/DESIGN.md` and
`design-md/together.ai/DESIGN.md`. This phase adapts surfaces/motifs only —
no new npm deps, no stock photography, no external CDNs. Everything below is
procedural (SVG/CSS) or real product data.

## Taken from elevenlabs (atmosphere + waveform motif)

- **Atmospheric gradient orbs as pure decoration.** Pastel orbs are the only
  "color moments" and never a card surface. SignalScope already ships
  `.aurora-bg` blobs — we keep them and place the waveform layer *on top*,
  matching "atmospheric blooms behind hero copy."
- **Audio waveform card.** Our recording thumbnails are generated from each
  recording's real `/preview` samples (I/Q trace) — a waveform glyph that is
  honest data, not decoration.
- **One CTA per view-port.** Reserves primary accent for a single action —
  enforced by using the waveform as atmosphere, never as a clickable surface.
- **Soft drop / hairline elevation.** Cards float via hairline + one subtle
  shadow tier; hover is a single-tier lift. We implement an explicit
  `--elevation-1..3` scale (adapts `0 4px 16px rgba(0,0,0,0.04)` touches).
- **Generous 96px section rhythm → scaled to dashboard hero spacing.**

## Adapted from together.ai (technical surface + instrument voice)

- **Near-black technical band with `surface-dark-soft` hairlines.** Matches
  our deep charcoal-navy `--background`; hairline token = `--border`.
- **Uppercase mono eyebrows for every technical label.** Together uses a mono
  caps voice for labels; ours is JetBrains Mono. Kept — already in the system.
- **Blueprint grid + corner ticks (interpreted adaptation).** Together's own
  chrome is a three-colour gradient ribbon; that palette conflicts with our
  semantic strictness (cyan precision / violet data / amber-red warnings only).
  We translate the *drafting-tool posture* into a schematic blueprint grid +
  corner registration marks on the analysis workspace — an instrument-readout
  framing that fits RF tooling better than a brand-gradient ribbon.
- **Dual surface rhythm.** Bands alternate canvas / canvas-dark; we alternate
  solid cards on the blueprint-damped workspace rather than adding a fifth
  surface tone.

## Strict rules kept from existing product design

- Warning amber / destructive red appear only for semantic states, never as
  decoration.
- Glass + blur used on hero/CTA panels only; content cards stay flat-opaque
  for readability.
- All decorative SVG layers are `aria-hidden`; contrast unchanged for text.