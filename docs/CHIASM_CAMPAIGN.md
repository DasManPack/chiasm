# Chiasm extended campaign

## Product contract

Chiasm should make a music collection feel like a place that can be entered, explored, attended to, and revisited. The interaction should remain understandable on an ordinary laptop, calm when idle, and spatially stable enough to remember. Movement, depth, and reveal must communicate a user action or a meaningful musical relationship.

Use the embodied design questions as acceptance criteria:

- Where am I in the collection, and can I recognize this place again?
- What becomes figure when I attend to it, and what stays available in the ground?
- Does movement help me explore, or merely animate the screen?
- Does each level of zoom reveal useful meaning at the right moment?
- Can I return to where I was without losing context?
- Will this component still make sense when it becomes a lens inside the spatial collection?

No heavyweight 3D camera, physics simulation, particle field, or permanent toolbar is required to satisfy these questions.

## Campaign sequence

| Stage | Outcome | Exit gate |
|---|---|---|
| C0 — Field proof | A full-window field of 50 albums with pan, pointer-centred zoom, hover, focus, mock play, Escape, and Home. | A first-time user can explore for five minutes, identify how to move and focus, and still feel oriented. |
| C1 — Attention and depth | One consistent focus model for scale, recession, opacity, hit targets, and semantic labels. | Focus is obvious within one second; nearby context remains legible; stored album geography never changes. |
| C2 — Embodied navigation | Reliable mouse, trackpad, keyboard, and return-home behavior with explicit orientation cues. | A laptop user can explore without accidental selection, disorientation, or loss of the starting point. |
| C3 — Contextual lens contract | One album lens follows the focused record and reveals explicit context from its named region. | Opening and closing preserve camera, focus, and album geography. Every candidate passes the lens question before implementation; C0 itself remains single-focus. |
| C4 — Listening in place | Real playback starts from the field while the collection remains present and current state is visible. | Play, pause, next, and return do not strand the listener in a separate page or lose the chosen place. |
| C5 — Arc and Autopilot | An optional, explainable listening route can continue from the current place. | The user can see why the next album is suggested, steer the route, pause it, or take control back immediately. |
| C6 — Horizon and relations | Nearby, distant, and unresolved musical possibilities gain meaning through reliable collection relationships. | Distance and connection encode something explainable; visual proximity never implies unsupported facts. |
| C7 — Trace and return | A local, revisitable record of the path through albums and listening. | A user can retrace or resume a route without making history a permanent navigation burden. |
| C8 — Real collection foundations | Chiasm uses proven library, artwork cache, playback, and provider foundations behind isolated adapters. | The field remains responsive on ordinary collections and degrades cleanly when artwork or providers are unavailable. |
| C9 — Qualification | Accessibility, performance, visual quality, and first-run acceptance across representative machines and collections. | Five-minute exploration succeeds; keyboard and reduced-motion paths work; no known blocking visual or responsiveness defect remains. |
| C10 — First-use and field residency | Chiasm opens as a focused app, lets a new listener add a folder from the field, and keeps indexing and collection feedback inside that surface. | A first-time listener can load a folder, see progress, enter the populated field, and keep exploring without encountering Melodex navigation or getting stranded on a blank page. |

## Current state

- **C0 implementation:** present in `desktop/chiasm`; offscreen GUI render/input, live-playback, Arc, Horizon, Trace, artwork, and large-collection interaction regression tests are authored. The focused Chiasm Qt suite passes all 25 tests. The five-minute human acceptance is still open.
- **C1 model preparation:** `album_depth_cue` provides one shared, testable focus-depth curve for drawing and hit detection; `semantic_zoom_level` names the overview, albums, and detail layers; hit targets retain a 44px minimum diameter across supported zoom levels. Album positions stay fixed, and drag keeps the world point under the pointer. Model checks pass; the visual exit gate remains open.
- **C2 — Embodied navigation:** implementation and regression assertions are in place at the user's direction: keyboard navigation, trackpad pan/pinch, a system-sized drag threshold, a semantic zoom status chip, and a contextual Home cue. Qt regression tests ran in the desktop suite; representative-device acceptance is still open. C0/C1 acceptance remains open and is not recorded as passed.
- **C3 — Contextual lens:** one in-field album lens follows the focused album and connects back to its screen position. It retains the title, artist, close, and playback controls; C6 evolves its context area into the Horizon relationship view. Missing region metadata stays blank rather than being filled from the artist name. `Enter` opens or toggles the lens; its close control or `Escape` closes it without clearing focus; a second `Escape` releases focus. The Qt state-preservation regression runs in the desktop suite. C3 visual acceptance and the earlier C0/C1/C2 gates remain open.
- **C4 — Listening in place:** an opt-in Chiasm page is wired from Explore and the command palette. It adapts the existing local Album Wall collection and track lists, while the field sends playback requests to the Melodex host and existing `FlowPlayer`. Double-clicking an album or pressing the play button in its lens starts its local album queue. The in-field transport and `Space`/`N` control pause and next; current track, play state, elapsed time, and the playing album are visible in the field. The canvas remains mounted when navigating away, preserving camera and focus when the collection still contains the album. The live-control/state Qt regression passes in the desktop suite; actual audio, return behavior, and visual acceptance remain open. Chiasm uses an additive queue-replacement helper; the default player controls are unchanged.
- **C5 — Arc and Autopilot:** starting from a focused local album builds a deterministic route of up to 12 playable albums without repeats. It prefers the same artist, then explicit shared genre labels; when neither is available it uses a clearly named alphabetical fallback. Spatial proximity is never used as evidence. The suggested album is highlighted in the field and its reason is shown beside the transport. The lens starts an Arc or sets a new next album; `A` does the same from the focused album. `Pause Arc`/`Space` pauses and resumes playback, including both decks during a crossfade, through an additive player method; existing `play_pause` behavior is unchanged. `Take Over` removes the remaining Arc queue while the current track continues. Route model and GUI regressions pass in the desktop suite; actual audio and crossfade-device acceptance remain open.
- **C6 — Horizon and relations:** the existing album lens now names relations supported by the collection: same artist, shared genre, and links between analyzed audio profiles. Audio links aggregate existing Music Map track edges into symmetric album links from a deterministic pass capped at 700 tracks. Their score and supporting track-link count are visible; the score is an evidence value, not a probability. Up to three named links connect from the focused album when their targets are in view; the same lens rows can move the field to a distant target while preserving zoom and opening its lens. The header counts resolved and unresolved albums. An unresolved result is explicitly not a claim that albums are unrelated. Audio sample coverage is shown, proximity alone never creates a relation, and absent region metadata remains absent rather than being inferred from artist. Model and Qt interaction regressions pass in the desktop suite; representative-library and visual acceptance remain open.
- **C7 — Trace and return:** the existing attached album lens gains a Trace tab beside Horizon. It records focused albums and album-level listening stops in a separate, device-local table capped at 48 entries; consecutive activity on one album coalesces. The trace stores album ID, display title, artist, activity type, and time, with no track paths. The lens shows two stops at a time with Earlier/Later paging. Selecting a stop recenters the same field and opens its album lens without changing zoom; its play control starts that album through the existing local queue. Stops whose album is no longer in the collection remain visible but cannot be played. This trace is separate from full track listening history, does not replace it, and adds no permanent control. Model and Qt interaction regressions pass in the desktop suite; visual acceptance remains open.
- **C8 — Real collection foundations:** `desktop/melodex/chiasm_feature.py` owns Chiasm's page, Trace, Arc, playback presentation, and artwork requests; the shell connects its semantic signals to the existing playback owner. `desktop/chiasm/melodex_adapter.py` owns the boundary to Melodex's local catalog, Album Wall grouping/layout, bounded Music Map projection, cached local artwork, and existing metadata service. Collection building remains off the UI thread, with a 5,000-track position pass and 1,200-album limit; Horizon keeps its 700-track evidence cap. If the local provider is unavailable, Chiasm shows an empty field with a status message; if Flow/local intelligence is unavailable, album metadata still produces a stable fallback layout. Artwork is requested only at album/detail zoom for the current visible and near-visible set and attached lens, in batches of at most 24; worker-side decoding produces centered thumbnails no larger than 320px, the field keeps an LRU of 48 images, and missing art falls back to the existing motif. Artwork uses `metadata.local_artwork` only and never calls online lookup. Playback remains a host request to the existing `FlowPlayer`. Pure adapter tests, including the 1,200-album cap, pass. A 12,700-row synthetic catalog through Melodex's actual `LocalIntelligenceService` produced the capped 1,200-album field model in 0.58 seconds; a 50,000-row metadata-only model smoke took 1.68 seconds. The Qt batch/stale-result regression passes in the desktop suite; representative-library UI responsiveness and visual acceptance remain open.
- **C9 qualification preparation:** the field's accessibility description now reflects the focused album, open Horizon or Trace lens, playback state, and active Arc; its shortcut help matches the implemented keys. Chiasm pans and zooms directly and has no canvas property animations, so reduced-motion users do not receive camera easing or ambient movement. Pointer, drag, wheel, keyboard, and native-gesture acknowledgement times now feed the existing content-free Fluid responsiveness summary. The Fluid release gate now runs six Chiasm checks covering 1,200-album input acknowledgement, direct manipulation, playback controls, Trace, accessible-description notifications, and interaction-measurement export. The visual QA script includes 50- and 1,200-album lens scenes, with playback, Horizon, and Arc state in the large case. The 72-test Fluid gate and all 600 desktop tests pass. Deterministic captures were rendered at 1440×900, 1280×720, and 1024×640; approved-reference comparison remains pending, and the 1024×640 Chiasm framing needs human edge/crowding review. C9 itself remains unaccepted; first-run, screen-reader, device-size, actual local-library/audio, and system reduced-motion checks are still required. C8 and earlier visual/device acceptance gates remain pending.
- **C10 — First-use and field residency (started):** the desktop entry point now swaps the inherited shell for Chiasm's field, hides the Melodex menu bar and shortcuts, and leaves only a Chiasm mark, an explicit **Add folder** control, and the spatial collection. The empty field names its next action; indexing and collection feedback render inside the field. The regression test checks that the inherited shell is not visible and that the add-folder control is present. This is the first implementation slice, not acceptance: Qt tests and packaged first-run checks still need to run, and an uncoached user must confirm the folder-to-field path at laptop size.
- **C11 — The discovery loop (started):** a compact **Find** action opens an in-field album/artist finder only when the collection is populated; `Ctrl+F` opens the same control. Selecting a result recenters the existing field, keeps its zoom, focuses that album, and opens its Horizon lens in place. This makes a known album a practical starting point in a large collection without adding a search page or persistent text panel. Focus remains in the same field, so its existing Trace can record the starting album and later return to it. The Qt regression covers artist search, focus, lens, camera position, and zoom; it does not count as the five-listener task or real-library acceptance.
- **P13 steering:** recorded in `docs/VISUAL_DESIGN.md` and retained as the later lens gate in `docs/CHIASM.md`.

### C10 first-use contract

- Launch into the Chiasm field every time; do not expose Melodex navigation, menus, or hidden-page shortcuts in the user-facing mode.
- When the local collection is empty, keep the field visible and offer a clear **Add folder** action. Do not populate it with fictional albums.
- Show folder indexing and collection preparation feedback inside the field, then refresh the field in place when the scan completes.
- Keep album focus, playback, Horizon, Trace, and Arc in the spatial field. There is no page-switching route that can strand the listener away from Chiasm.
- On scan cancellation or failure, leave the current field intact and state what happened.

**C10 exit gate:** on a clean install, identify how to load music without coaching; add a representative folder; understand indexing while it runs; explore and play from the populated field; confirm scan failure/cancellation leaves the field recoverable; and complete the same flow at 1024×640. Automated Qt launch, folder-add, scan-refresh, and keyboard regressions must pass. C9's still-open real-library, audio, accessibility, reference-comparison, and human-acceptance checks remain separate gates.

### C2 contract

- Mouse drag pans; the platform's drag threshold separates a click from an intentional pan.
- The mouse wheel zooms around the pointer. Trackpad scrolling pans, and native pinch zooms around the gesture point.
- Arrow keys pan; Shift+arrows use smaller steps; `[`/`]` focus the previous/next album in collection order and center it while preserving zoom; `+`/`-` zoom around the field center; `H` or `Home` restores the starting view; Escape releases focus.
- A quiet status chip names the semantic zoom layer. A direction-to-Home cue appears only after leaving the starting view and also returns home when clicked.
- The cue stays attached to the field so it remains useful if the field later sits inside a spatial lens. No minimap, toolbar, or new detail surface is introduced in this stage.

**C2 exit gate:** mouse, trackpad, and keyboard navigation feel consistent on an ordinary laptop; a small click movement does not pan; the direction cue is legible but unobtrusive; Home restores the starting view exactly. GUI tests and representative-device checks remain part of qualification.

**C2 device review:** exercise mouse drag and wheel zoom; trackpad scroll and pinch; arrow pan and `+`/`-` zoom; `[`/`]` album focus; `H`/`Home`, Escape, and the clickable Home cue; then click an album with slight pointer jitter and confirm the camera did not pan. Confirm that the status chip clarifies the current zoom layer and the Home cue points toward the starting view without pulling attention from the albums.

### C3 lens contract

- The focused album stays the figure; the lens is a small surface drawn inside the same field and connected to that album's current screen position. It follows pan and zoom, and pins its connector to the visible field edge if the album moves offscreen.
- The lens shows the album cover motif, title, artist, region, and up to three other titles with the same explicit region label. It describes shared membership only; generated coordinates do not stand in for genre, taste, or musical similarity.
- `Enter` toggles the lens. The close control and the first `Escape` close only the lens; a second `Escape` releases focus. Changing focus dismisses the prior lens. Lens clicks are contained so they cannot accidentally select or play an album underneath.
- Opening or closing must leave camera center, zoom, focused album, and all stored album coordinates unchanged. Pan, zoom, and Home remain available around the lens.

**C3 exit gate:** Qt regression tests pass; keyboard and close-control exit preserve the field state; the lens follows its album while navigating; and a visual review confirms the lens is readable without hiding the selected album or making the surrounding field feel like a dialog backdrop. The automated GUI test and human visual review remain pending in this environment.

### C4 listening contract

- The Chiasm page is an opt-in field inside Melodex, opened from Explore or the command palette. Its adapter reuses local Album Wall rows and track order; `FieldCanvas` emits host requests and does not own the player.
- Double-clicking an album, using the play control inside its lens, or pressing `Ctrl+Enter` with that album focused starts it through the existing `FlowPlayer`. The attached lens stays in the field and does not become a separate playback page.
- The in-field transport, `Space`, and `N` use Melodex's existing play/pause and next actions. Current artist, title, play state, elapsed time, and the playing album are reflected in the field.
- The Chiasm page remains mounted when navigating elsewhere, so audio continues and the camera/focused album/lens remain available on return if that album is still in the local collection. If the collection changes and removes the focused album, the lens closes while the camera remains.
- The standalone `python -m chiasm.run` remains a fictional 50-album demo with mock-play. Integrated C4 uses the local collection only; provider playback is outside this stage.

**C4 exit gate:** in a Qt-enabled Melodex run, play an album both by double-click and from its lens; confirm playback is audible and follows local track order. Pause and resume from the field and with `Space`, advance with the field control and `N`, and verify unavailable actions are disabled. Navigate to another Melodex page and back while listening; confirm audio continues and the camera and chosen focus remain. Check that the current track and playing album are visible without obscuring field navigation. Automated Qt interaction, representative-device audio, and this human return check remain pending here.

### C5 Arc contract

- Start from the focused album's lens with **Start Arc** or press `A`. The field queues the rest of the current album if it is already playing, then continues through the route using the existing `FlowPlayer` queue.
- Each hop is justified by explicit collection metadata: same artist first, then one or more shared genre labels. If metadata has no such link, the route says it is using the alphabetical collection fallback. Coordinates and visual closeness never affect the recommendation.
- The route is bounded to 12 albums and never repeats one. A gold dashed ring marks the next album; the in-field Arc line names it and states the reason.
- Open another album's lens and choose **Set as next album** (or focus it and press `A`) to steer. The remainder of the current album stays queued, followed by the chosen album and a new explainable route from there.
- **Pause Arc** and `Space` pause/resume the route's audio; during a crossfade, both player decks freeze together. **Take Over** clears the Arc tail but lets the current track continue. Double-clicking another album starts that album directly and leaves Arc mode.

**C5 exit gate:** with a Qt-enabled local library, confirm the route uses artist and genre labels before the labeled fallback, never repeats albums, and visibly marks the next album with its reason. Start from a currently playing album and confirm it does not restart; steer to another album and confirm the current album's remaining tracks play first. Pause and resume during a crossfade and confirm the incoming deck does not drift ahead. Take over and confirm the current track continues without another Arc album starting. Confirm direct album play exits Arc immediately. Model tests pass here; Qt interaction, audio, crossfade, and visual acceptance remain pending in this environment.

### C6 Horizon contract

- The existing album lens is the entry to Horizon; it does not add a permanent toolbar or a second floating surface. It names up to three records linked by explicit same-artist metadata, shared genre labels, or analyzed audio-profile edges. Mouse selection or keys `1` to `3` follow the displayed links.
- Audio-profile links reuse the Music Map's track graph, aggregated to album pairs. The bounded evidence pass analyzes up to 700 track profiles and reports its sampled coverage. Its 0–1 score comes from the Music Map similarity function and is not a probability; support counts report how many track edges contributed.
- When visible, evidence links use distinct field lines for metadata, audio-profile, or combined evidence. The target album also receives a quiet outline. A lens row can move the field to a linked album and open that album's lens; the zoom and stored album coordinates stay unchanged.
- Distance on the sound field does not create a relation. A nearby album without explicit artist, genre, or analyzed-track evidence remains unlinked. Missing evidence appears as unresolved; it never means the albums are unrelated.
- Region names are displayed only when the collection provides them. The artist field is never copied into region to make a cluster.

**C6 exit gate:** in a Qt-enabled library with analyzed audio, inspect a visible metadata link and an audio-profile link and confirm each line matches its labeled evidence. Follow a distant link from the album lens and confirm it centers the target without changing zoom or album geography. Inspect a nearby album with no evidence and an album outside the bounded sound sample; confirm neither is labeled related by proximity. Check a collection with blank region metadata and confirm Chiasm does not present artist names as places. Confirm the lens remains readable inside the field on a laptop-sized window. Model checks pass here; Qt interaction, representative-library, and human visual acceptance remain pending.

### C7 Trace contract

- Trace is a second view inside the existing focused album lens, beside Horizon. It does not add a page, toolbar, modal, or second spatial surface.
- `Ctrl+Tab` and `Ctrl+Shift+Tab` switch between the lens panels when it is open, so keyboard users can reach Trace without relying on the painted tab hit targets. `PageUp`/`PageDown` page through older/newer Trace stops, and the accessible description names the currently displayed stops and available direction.
- Chiasm records album focus changes as exploration and album changes during playback as listening. Consecutive activity on the same album combines into one stop; moving to another album and returning creates a new stop.
- The trace remains on this device and keeps at most 48 stops. It stores album ID, title, artist, activity, and time only; the existing full listening history stays separate.
- The lens shows two stops at a time. Earlier/Later pages through the route. Selecting a stop returns to that album, centers it in the field, and opens its Horizon lens without changing zoom or album geography.
- The play control explicitly starts that album through the existing local queue. It starts at the album, rather than restoring a track position. A stop outside the current collection remains readable and cannot be played.

**C7 exit gate:** record a route across several albums, switch pages and return, and confirm the trace persists while the field view remains in place. Browse earlier and later stops; follow one and verify camera zoom and album positions remain stable. Start playback from a stop and confirm the current album queue starts only after the explicit play action. Inspect a removed album stop and confirm it is labeled unavailable. Confirm the cap, local storage, and lack of track paths; verify the Trace remains legible inside the lens at laptop size. Model persistence and Qt interaction regressions pass in the desktop suite; representative-library and visual acceptance remain pending.

### C8 real collection contract

- The Melodex host owns a `MelodexCollectionAdapter` that reads the existing local provider catalog and Album Wall model. Chiasm does not scan folders independently or create a second collection store. Album IDs and fallback geography come from the established collection model; track queues stay attached to those IDs.
- Collection building runs in the existing background scheduler. The spatial position pass considers up to 5,000 tracks and 1,200 albums; the separate nearest-neighbor evidence pass remains capped at 700 tracks. If Flow analysis cannot be loaded, metadata still yields stable positions. If the local provider is unavailable, the field clears cleanly and reports that state.
- Playback remains behind `FieldCanvas` host signals and the existing `FlowPlayer` path. Chiasm does not add provider-specific playback or change Melodex's default controls.
- Artwork requests begin at album/detail zoom and follow the visible and near-visible albums plus the focused album lens. Each visible-set context can request at most 24 items, with one worker batch in flight. Existing local files and the metadata artwork cache are resolved through `local_artwork`, decoded off the UI thread, and held in a 48-image LRU. Each thumbnail is at most 320px per edge. Missing, unreadable, or unavailable art keeps the procedural motif. No online lookup is triggered.
- Artwork remains part of the album tile and its attached lens. It adds no page, toolbar, or persistent control and stays subject to the lens question: “Will this component still make sense when it becomes a lens inside the spatial collection?”

**C8 exit gate:** with a representative local collection, confirm album identity, track order, stable geography, and existing FlowPlayer playback; inspect ordinary and large collections while panning, focusing, and zooming, and confirm input remains responsive while collection and art work run in the background. Confirm missing/corrupt covers show motifs, provider loss leaves a usable empty field, and unavailable Flow analysis leaves metadata-positioned albums. Qt interaction regressions pass in the desktop suite; visual review, real collection responsiveness, and audible playback remain pending because a representative library and live audio session are unavailable here.

### C9 qualification contract

- The accessible field description names the current focus, lens panel, visible Trace stops, playback state, and active Arc. Chiasm sends a Qt description-changed accessibility event only when that text changes. Keyboard help documents album focus traversal, direct play, pan, zoom, lens, Horizon/Trace panel switching and paging, transport, Arc, and Home actions. A screen-reader user must be able to retrieve the current field state and operate the supported keyboard paths; verify this with the platform screen reader because the canvas remains one custom-painted widget.
- Pan and zoom respond immediately to direct input. The field has no camera interpolation or ambient animation, so its spatial movement is already still under reduced-motion settings. Verify the platform preference in a real desktop session and confirm other host transitions respect the user's setting.
- Run the field at 50 albums and at the 1,200-album cap on a representative laptop. Use the existing Fluid thresholds: interaction acknowledgement p95 at or below 100 ms (below 50 ms preferred), event-loop p99 gap at or below 100 ms, and no foreground stall at or above 250 ms. The field records content-free interaction labels in the normal responsiveness summary; inspect the p95, p99, and stall counts after pan, focus, zoom, lens, and artwork activity. Measure collection-ready time and visible-set artwork work separately; the synthetic model timings above do not qualify rendered UI performance.
- Review at 1280×720 and 1024×640, including a high-DPI display. Check text contrast and truncation, the focus cue, attached lens placement, transport visibility, and that the field still reads as a collection when the lens is open.
- Give a first-time user five minutes with no coaching. They should find pan, zoom, focus, lens, and return-home behavior and retain their sense of place. Ask where the component belongs when encountered as a lens inside the spatial collection.

The deterministic Chiasm scenes are `12-chiasm-50-album-lens.png` and `13-chiasm-1200-album-playing-lens.png` from `scripts/visual_qa_capture.py`. Capture both target sizes with:

```bash
python scripts/visual_qa_capture.py --width 1280 --height 720 --output visual-qa/1280x720
python scripts/visual_qa_capture.py --width 1024 --height 640 --output visual-qa/1024x640
```

Inspect the rendered field and lens together. These scenes prepare the review; they do not count as visual acceptance.

**C9 exit gate:** close only after Qt interaction tests run, the Fluid p95/p99/stall budgets pass at representative collection sizes, keyboard and screen-reader paths are usable, reduced-motion behavior is confirmed on-device, representative-size visual review is clear, and first-run exploration completes without a blocking orientation or responsiveness issue. This workspace cannot close that gate without the approved visual reference, a screen reader/desktop session, and a representative local collection. C0–C8 acceptance remains explicitly pending where noted above.

## C0 acceptance run

Run from `desktop` in an environment with the desktop requirements installed:

```bash
python -m chiasm.run
```

Explore for five minutes without coaching. Check that the initial clusters are readable, hover and focus are easy to distinguish, zoom stays anchored under the pointer, dragging preserves recognizable geography, and Home restores the starting view. Note any moment where the user loses their place, selects by accident, or cannot tell what has focus. Keep C0/C1 marked open until this run feels comfortable and the Qt regression test runs successfully. A user-directed later-stage slice may proceed while these gates stay explicitly pending.

## Working rules

1. Keep each stage independently runnable and reversible.
2. Use exit gates to determine what is accepted; explicit user direction can start later work without marking an earlier gate as passed.
3. Preserve the spatial field during detail, lyrics, playback, and route exploration.
4. Prefer useful stillness and direct manipulation to ambient motion.
5. Keep Melodex production behavior outside the prototype changes.

## Product campaigns after C10

### Product bet

Chiasm earns its place when a listener can start from an album they know, find a less familiar album through a credible collection relationship, start listening immediately, and return to their place without building a playlist or navigating a stack of pages. The field should make this loop feel natural, with very little permanent text.

The proof task is: **find a familiar album, follow one understandable relationship to something less familiar, play it, then return to the starting point.** A visual effect, an algorithmic score, or a long feature list does not count as discovery by itself.

| Campaign | User-visible outcome | Exit gate |
|---|---|---|
| **C11 — The discovery loop** | A listener can locate a known album, move to a less familiar one through a supported collection relationship, inspect why they are connected, play it, and return. | Five first-time listeners try the task without coaching; at least four complete it in three minutes, can describe the connection in their own words, and can return to the starting album. Record where each person hesitates. |
| **C12 — Topography with meaning** | Album placement gives the listener useful orientation while remaining stable across scans and launches. | On a real collection, listeners can identify a meaningful nearby option and explain what the placement does and does not claim. No relation is inferred from screen distance alone; positions do not jump after an unchanged rescan. |
| **C13 — A listening route you can steer** | Arc carries the listener from a chosen album into a short, evidence-based listening path while leaving control close at hand. | In a representative library, a listener can start, understand the next choice, steer to another album, pause, or take over immediately. A route with weak evidence is labeled plainly and never presented as personalized certainty. |
| **C14 — Return to a lived-in field** | The listener recognizes the collection's geography and can revisit a prior exploration through Trace. | After closing and reopening Chiasm, the user can find a familiar region, revisit an earlier stop, and resume without a history page or loss of the current listening queue. Removed or changed albums recover cleanly. |
| **C15 — Real-listener release proof** | A small group of external listeners can install Chiasm, add a collection, explore, play, and give useful feedback. | Run the same tasks on macOS, Windows, and Linux, including a large library. Publish the exact build SHA, test results, known limitations, and the highest-impact fixes before calling the preview ready for broader release. |

### Campaign order and scope

C11 evaluates the core exploration loop already present in Field, Horizon, Arc, and Trace; its first implementation adds only the temporary Find action needed to reach a known starting album in a large library. Search stays in the field and opens the album's relationship lens. Do not add another visualization or recommendation engine for this campaign. C12 changes spatial organization only when C11 observations show that placement makes exploration hard to understand. C13 then improves the listening route using those real-library findings. C14 makes return behavior dependable, and C15 gathers independent evidence before broad release.

Keep the work anchored to local collections and the listener's next action. Defer social rooms, online recommendation services, generative playlist creation, and heavyweight 3D until the discovery loop works reliably without them. Every campaign must end with a listener behavior that can be observed and a clear result that can be reported.

**C11 starting condition:** the corrected C10 test matrix passes, and at least one current Chiasm build completes the clean-install folder-to-field flow. C10's human first-use and C9's remaining accessibility, reference-comparison, and representative-device checks stay open until their own gates are performed.
