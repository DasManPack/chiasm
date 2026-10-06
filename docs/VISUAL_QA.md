# Campaign 13 visual QA

P13i is an acceptance pass, not another feature campaign.

The objective is to decide whether the actual rendered Melodex screens are good
enough to represent the product publicly. Architectural changes are allowed only
when a visual defect proves they are necessary.

## Acceptance question

For every flagship scene:

> Would this exact screen be acceptable in the README, release notes or product
> screenshots without an apology or explanation?

If the answer is no, P13i remains open.

## Canonical captures

`scripts/visual_qa_capture.py` renders deterministic representative scenes at
1440×900 by default. CI also captures the full set at 1280×720 and 1024×640,
so laptop-size clipping and hierarchy can be reviewed from the same run.

The capture set includes:

- Visuals shell / Track Sigil / grouped Watch–Explore selector
- Profile Pulse
- synced immersive Lyric Flow and the full Visuals page in Lyric Flow
- untimed Lyric Flow
- Constellation with a pinned recognition card
- Sonic Weather
- Memory Atlas with a pinned session card
- Musical Journey
- legacy/internal Album World compatibility renderer
- Minimal
- reduced-Auto Sonic Weather
- Lyric Flow empty state
- bright and dark synthetic artwork
- calm and energetic profiles plus sparse-acoustic, dense-rock, ambient,
  electronic, bass-heavy and highly dynamic analysis fixtures
- synced windowed Lyric Flow, sparse Constellation and short Memory Atlas

The full-page Lyric Flow capture includes the mode selector, track identity,
status, seek control and timed lyric state. The immersive capture isolates the
lyrics scene itself.

CI uploads these PNGs as a `visual-qa-captures` artifact.

Each `manifest.json` records fixture coverage and reference-comparison status.
Fixtures are synthetic state probes. They do not stand in for approved concept
art or establish mockup parity.

## Reference concepts

No approved P13 reference concepts are stored in this repository. P13i can
expand and render its deterministic coverage set without them, but it cannot
close the mockup-parity gate until the approved concepts are reviewed beside
the matching implementation captures. Record that comparison in the review;
do not infer approval from the capture manifest.

## Review rubric

Each capture is reviewed for the following.

### 1. Hierarchy
- The primary subject is obvious within one second.
- Current track / current lyric / selected node is dominant.
- Secondary labels do not compete with the visual.

### 2. Composition
- No accidental dead zones or edge crowding.
- Cards feel attached to the object they describe.
- Dense data remains spatially legible.
- The scene still works at ordinary laptop proportions.

### 3. Typography
- Text is readable at normal display scale.
- Active lyrics feel cinematic rather than oversized UI labels.
- Captions are subordinate and do not resemble debug output.
- No clipping or awkward wrapping.

### 4. Glow and depth
- Glow creates atmosphere and hierarchy.
- Nothing looks like gaming RGB, neon outlines or generic sci-fi HUD chrome.
- Reduced Auto keeps the same visual identity.

### 5. Meaning
- Constellation distance/path emphasis is understandable.
- Memory Atlas spatial encodings remain readable.
- Track Sigil reads as identity, not as a mysterious chart.
- Empty states explain what is missing without dominating the screen.

### 6. Motion readiness
Static captures should still suggest where motion belongs. Runtime checks must
confirm that breathing, drift and lyric transitions remain restrained.

### 7. Product consistency
- dark navy / blue-black base
- luminous blue-white core language
- related typography and card treatment
- no scene looks as if it came from a different app

## Required representative states

Before Campaign 13 closes, manually inspect:

- bright artwork and dark artwork
- energetic and calm profiles
- synced, unsynced and missing lyrics
- sparse and dense Constellation
- short and large Memory Atlas histories
- normal window and immersive Lyric Flow
- Auto and Auto-reduced rendering
- paused / hidden / Battery behavior

## P13i completion gate

P13i is complete only when:

1. deterministic capture generation is green;
2. each flagship capture has been reviewed beside its approved concept;
3. all package/test/performance checks remain green;
4. no flagship capture contains a known visual defect;
5. reduced Auto remains recognizably the same design;
6. no new accessibility or interaction regression is introduced;
7. the final screenshots are good enough for public-facing product material.

Do not open another visual redesign campaign merely to postpone obvious polish.
Fix visual defects in P13i until this gate is met.
