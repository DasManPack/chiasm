# P13i — Manual visual review

Use this runbook to close the visual checks that need a real Qt desktop. The
capture manifest confirms which fixtures were requested; it does not establish
that a scene looks good or matches a concept.

## 1. Prepare a Qt-enabled checkout

From the Chiasm repository root, use Python 3.11 or 3.12:

```bash
python3 -m venv .venv
source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e desktop pytest
```

Download the approved `Melodex Lyrics Visualizer Mockup.png` to a location you
can open beside the screenshots. Do not edit or crop the reference.

## 2. Generate the deterministic captures

Run from the repository root. The capture script sets Qt to offscreen mode:

```bash
python scripts/visual_qa_capture.py --width 1440 --height 900 --output visual-qa/1440x900
python scripts/visual_qa_capture.py --width 1280 --height 720 --output visual-qa/1280x720
python scripts/visual_qa_capture.py --width 1024 --height 640 --output visual-qa/1024x640
```

Confirm each output folder contains `manifest.json` and every PNG listed in its
`captures` array. Keep the manifest's reference status as pending until the
side-by-side review is complete.

## 3. Compare the scenes

Open the approved mockup beside the 1440×900 captures. Use the smaller sizes
to check that the same hierarchy survives laptop layouts. Review these groups:

| Scene | Capture files |
|---|---|
| Lyrics | `02-lyric-flow.png`, `03-lyric-flow-unsynced.png`, `11-lyrics-empty.png`, `16-lyric-flow-windowed-bright-artwork.png`, `19-lyric-flow-page.png` |
| Artwork | `00-visuals-overview.png`, `14-visuals-overview-bright-artwork.png` |
| Constellation | `04-constellation.png`, `17-constellation-sparse.png` |
| Memory Atlas | `06-memory-atlas.png`, `18-memory-atlas-short.png` |
| Profile Pulse and Sonic Weather | `01-profile-pulse.png`, `05-sonic-weather.png`, `10-auto-reduced-weather.png`, and the archetype-specific `15-*` captures |
| Chiasm field | `12-chiasm-50-album-lens.png`, `13-chiasm-1200-album-playing-lens.png` |

For each scene, record **Pass** or **Fix** for:

- hierarchy: the current lyric, track, or selected album is immediately clear;
- composition: the scene has no accidental dead zones, clipping, or crowded edges;
- typography: text is readable at normal scale and lyric lines do not resemble debug labels;
- glow and depth: light establishes focus without looking like generic neon chrome;
- meaning: spatial distance, history, and audio-reactive changes remain interpretable;
- consistency: the scene belongs to the same dark, blue-white visual system.

For the lyric mockup, compare the lyric area, active-line emphasis, artwork treatment,
track identity, playback/seek controls, and surrounding navigation. Do not judge
parity from matching placeholder text or synthetic cover art.

## 4. Check runtime behavior

Run the focused visual tests and the existing Fluid gate:

```bash
python -m pytest -q \
  desktop/tests/test_lyric_flow.py \
  desktop/tests/test_living_canvas_widget.py \
  desktop/tests/test_weather_profile_pulse.py \
  desktop/tests/test_visualization_models.py \
  desktop/tests/test_visual_performance.py
python scripts/fluid_ci_gate.py
```

With the virtual environment active, start the editable development build by
running `melodex`. For the isolated 50-album field, run this from the `desktop`
directory; it uses fictional albums and mock playback:

```bash
python -m chiasm.run --windowed
```

For real collection, artwork, and playback behavior, open **Explore → Chiasm** in
the integrated Melodex app. That page uses local albums and shows at most 1,200.
Record the actual album count tested; if it is below 1,200, mark the on-device cap
check as pending because the automated fixture does not replace a real-device run.

1. Switch between windowed and immersive Lyric Flow; confirm the same lyric
   document and current position are retained.
2. Check synced, untimed, and missing lyrics. Seek to another line, pause, and
   resume. Untimed lyrics must remain static rather than guessing the active line.
3. Pause playback, hide/minimize the visual window, and enable Battery mode.
   Confirm animation stops or becomes static as specified, then resumes correctly.
4. Pan/focus in Constellation and open a recognition card. Browse a short and
   long Memory Atlas history. Confirm selection stays readable and does not cover
   the object it describes.
5. Open Chiasm at 50 and 1,200 albums. Pan, zoom, open/close the attached lens,
   focus albums with `[` / `]`, switch between Horizon and Trace with `Ctrl+Tab` /
   `Ctrl+Shift+Tab`, page Trace with `PageUp` / `PageDown`, return Home, and test
   keyboard playback with `Ctrl+Enter`. The lens must remain attached to the
   focused album inside the same field; it must not turn into a separate page or
   obscure the surrounding collection. At 1,200 albums, check that pan, focus,
   and zoom remain responsive while artwork is visible.
6. After exercising the 50- and 1,200-album fields, export redacted diagnostics
   from **Sources & plugins → Export redacted diagnostics…** and evaluate the
   saved JSON:

   ```bash
   python scripts/fluid_gate_check.py /path/to/melodex-diagnostics.json \
     --require-interaction-prefix chiasm:
   ```

   Record the app-wide interaction p95 during the Chiasm run, the count of
   recent `chiasm:` samples, event-loop p99, and stall counts. The
   limits are p95 ≤100 ms (≤50 ms preferred), p99 ≤100 ms, and no foreground
   stall ≥250 ms. Also time collection-ready and visible-artwork-ready separately;
   synthetic model timings do not qualify the rendered field.
7. Enable the operating system's reduced-motion setting, then repeat pan, zoom,
   and focus. Confirm that Chiasm has no ambient camera movement or easing after
   input and that direct manipulation still works. Restore the previous system
   setting after the check.
8. With the platform screen reader enabled, focus Chiasm and retrieve its
   accessible description. Move between albums and lens panels; in Trace, confirm
   the visible stop titles and whether earlier or newer stops are available are
   announced and updated after paging. Confirm playback and Arc state updates are
   announced when those states change.
9. Ask someone who has not used Chiasm to explore for five minutes without
   coaching. They should discover pan, zoom, focus, the lens, and Home while
   retaining their sense of place. If no first-time participant is available,
   record this acceptance check as pending.

## 5. Record the decision

Create `visual-qa/REVIEW.md` with the date, app commit, OS/display scale, tested
window sizes, test results, and a short Pass/Fix note for every scene group above.
Use this table to make the three viewport reviews explicit:

| Scene group | 1440×900 | 1280×720 | 1024×640 | Notes / capture filename |
|---|---|---|---|---|
| Lyrics |  |  |  |  |
| Artwork |  |  |  |  |
| Constellation |  |  |  |  |
| Memory Atlas |  |  |  |  |
| Profile Pulse and Sonic Weather |  |  |  |  |
| Chiasm field |  |  |  |  |

Also record the results for Qt tests, Fluid thresholds, windowed/immersive lyric
continuity, reduced motion, keyboard navigation, screen reader, and the five-minute
uncoached exploration. Attach screenshots only for defects or borderline
decisions. List each blocking defect with its capture filename and the smallest
reproducible interaction.

P13i closes only when all required scenes pass beside their approved concepts,
the runtime checks pass, no flagship defect remains, and reduced Auto retains
the same visual identity. Otherwise, fix the defect and repeat the affected
capture and review.
