# Melodex Visual Experience — Campaign 13

## Objective

Make Melodex's visual experiences approach the quality, atmosphere and clarity
of the approved concept mockups while remaining procedural, responsive,
lightweight and meaningfully driven by the music or listening data.

The visual target is **not** "more effects".  Each visual must have a readable
purpose and an explainable mapping from data to presentation.

## Product model

Visuals are grouped by intent rather than presented as one undifferentiated
list.

### Watch
- **Lyric Flow** — immersive timed lyrics, glow and restrained musical breathing.
- **Sonic Weather** — an atmospheric field derived from musical character.
- **Profile Pulse** — a radial, living track profile driven by musical state.

### Explore
- **Constellation** — nearby tracks as a musical neighbourhood; stars for
  overview, artwork for recognition, paths for meaning.
- **Memory Atlas** — listening history with explicit time/session semantics.

### Identity
- **Track Sigil** remains a deterministic recording identity, but should become
  a reusable identity element rather than a primary four-minute visualizer.

## Shared visual language

- Dark spatial canvas with clear depth.
- Blue/white glow used as an active-state language, not as decoration on every
  element.
- Brightness, size and movement establish hierarchy before labels do.
- Motion is restrained and interpolated.  Avoid large bouncing or arcade-style
  pulsing.
- Album artwork may influence palette/background atmosphere, but artwork is not
  required for the visual to work.
- Missing Flow analysis degrades to deterministic identity-based presentation;
  it must never block playback or trigger analysis on the UI thread.
- Visuals consume semantic state.  They never own FlowPlayer.

## P13a shared runtime contract

P13a introduces one Qt-free `VisualState` snapshot shared by renderers:

- progress
- energy
- brightness
- rhythm
- warmth
- density
- pulse
- glow
- drift
- tempo phase
- whether cached Flow analysis is available

This state currently uses the existing cached `VisualProfile` / energy curve.
It deliberately performs **no live FFT or expensive audio work**.  Later stages
may enrich the contract with real bass/mid/treble or onset data without giving
each visualizer a separate analysis loop.

P13a also centralizes rendering budgets:

| Mode | Target | Intent |
| --- | ---: | --- |
| Auto | 15 fps | Default atmospheric presentation; can reduce detail after slow frames |
| Eco | 10 fps | Fewer particles/glow/path samples |
| High | 30 fps | Smooth motion with bounded extra detail |
| Battery | static | No animation timer |

The existing visual scene already stops animation while paused, hidden or
minimized; Campaign 13 preserves that behavior.

## Rendering principles

Prefer cheap procedural composition:

- cached geometry
- alpha-composited glow layers
- gradients
- paths
- low particle counts
- downsampled artwork before blur
- interpolation instead of repeated layout/analysis
- layout computation only when inputs change

Do not use AI image generation during playback.  The approved generated mockups
are visual references, not runtime assets.

## Feature-specific targets

### P13b — one lyrics system
One lyric state feeds:
1. the practical Now Playing reader, and
2. the immersive Lyric Flow presentation.

Reader target:
- readable normal text (roughly 22–26 px)
- stronger active line (roughly 28–32 px)
- high contrast
- search
- click synced line to seek
- source/refresh/translate/edit actions
- sensible manual-scroll vs auto-follow behavior

Full screen is a route into the same Lyric Flow presentation used by Visuals,
not a second lyric implementation.

### P13c — Lyric Flow
- large active typography
- soft blue-white active glow
- faded previous/next context
- smooth vertical movement
- subtle energy-driven breathing (about 1–2% scale)
- artwork-derived dark atmospheric background when available
- word timing when available, line-level fallback otherwise
- Calm / Flow / Karaoke can follow after the default Flow experience is strong

### P13d — Constellation 2.0
- no fixed hub-and-spoke ring
- proximity communicates similarity
- node size/brightness communicates relevance
- meaningful relationship paths
- current track is dominant
- hover brightens node + strongest paths and reveals a cached album-art card
- click holds selection; activation queues/plays through semantic signals
- optional faint journey trail from recent listening

**Stars for overview. Artwork for recognition. Paths for meaning.**

### P13e — Sonic Weather + Profile Pulse
Sonic Weather should become an atmospheric field rather than a literal cloud
icon.  Use mist/haze layers, streaks, particles, depth and internal glow.
Descriptors should support a visual meaning that is already apparent.

Profile Pulse should use mathematical radial geometry.  Musical state controls
shape amplitude, radius, glow and edge detail; it should feel organic rather
than like a static radar chart.

### P13f — Memory Atlas
Every spatial encoding must be explainable. Time should be obvious; sessions
and repeated listening should form readable clusters/islands; chronological
paths should reveal how listening moved.

Current public semantics are:
- left → right = chronological time
- height = average time of day
- colour reinforces daypart
- size = play count
- width = grouped listening span

### P13g — visual information architecture
Visuals are presented by purpose rather than as one flat experiment list.

**Watch**
- Profile Pulse
- Lyric Flow
- Sonic Weather
- Minimal

**Explore**
- Constellation
- Memory Atlas
- Musical Journey

Personal visualizer recipes appear in their own section when installed.

Album World remains available internally for compatibility, but the P13i visual
review found it substantially weaker than the new public visual language, so it
is no longer surfaced as a primary Watch mode.

Track Sigil is no longer a public standalone visualizer. Its fixed geometry is
reusable identity infrastructure: the same deterministic motif appears beside
the current track and at the centre of Constellation. Geometry stays fixed for
the recording; only surrounding glow may reflect playback state. The legacy
fingerprint renderer remains available internally for compatibility, but it is
not surfaced as a primary four-minute experience.

When shaping P13 components that may carry forward into Chiasm, use this design
prompt:

> Will this component still make sense when it becomes a lens inside the spatial collection?

### P13h — performance pass
Profile representative tracks and hardware.  Bound particle count, glow layers,
path samples and artwork work.  Animation must never compromise audio playback
or general UI responsiveness.

### P13i — mockup-parity QA
Compare implementation captures beside the approved reference concepts across:
- sparse acoustic
- dense rock
- ambient
- electronic
- bass-heavy
- highly dynamic tracks

Review composition, typography, hierarchy, glow, density, depth and motion, not
just whether the same widgets exist.

## Acceptance bar

A stage is not complete merely because it implements the concept.  For the
flagship scenes, an unfamiliar reviewer should be able to look at the approved
mockup and an implementation screenshot and recognize the latter as the
intentional realization of the former.

At the same time:
- hidden visuals consume no animation CPU;
- missing artwork/analysis/lyrics has a deliberate fallback;
- reduced-motion/static quality remains usable;
- visual code does not acquire player ownership;
- no runtime-generated image assets are required.
