# Chiasm

**Move through your music.**

Chiasm is an experimental spatial music experience derived from Melodex.

## Product idea

Your music collection is a place rather than a catalogue.

The primary experience is a calm spatial field in which the user can move, focus, listen, follow relationships, hand control to Autopilot, open lyrics without losing context, and later retrace the route they took.

## Design doctrine

- The collection is the interface.
- Direct manipulation before permanent controls.
- Movement replaces page navigation.
- Detail follows attention.
- Motion must communicate state.
- Preserve stable geography and spatial memory.
- Use ordinary 2D/2.5D engineering, not a heavyweight 3D engine.
- Responsiveness beats visual richness.
- Administrative workflows may remain conventional.
- The world should mostly rest; movement follows user intent or Autopilot.
- Spatial UX must remain usable on ordinary computers.

## Internal vocabulary

- **Field** — the collection space.
- **Arc** — the active or Autopilot route.
- **Horizon** — peripheral and unresolved musical possibilities.
- **Trace** — exploration history.

## First prototype

Do not begin by rebuilding Melodex.

Start with a deliberately isolated prototype:

1. 50 album covers.
2. Full-window spatial field.
3. Drag to pan.
4. Pointer-centred zoom.
5. Hover for glance.
6. Click for focus.
7. Double-click for play/mock play.
8. Escape to release focus.
9. Almost no permanent UI.
10. No 3D camera, particles, physics, lyrics, provider work, or multiple lenses.

### First acceptance test

The prototype should already feel enjoyable to explore for five minutes before any additional visual or product complexity is added.

The isolated implementation lives in `desktop/chiasm`; start it from `desktop` with `python -m chiasm.run`. Its first pass uses a deterministic 50-album field, pointer-centred zoom, hover glance, click focus, mocked double-click playback, Escape to release focus, and Home to return.

### Later expansion gate

Keep C0 a single field with one focus surface. After its first acceptance test, ask before adding any component or lens:

> Will this component still make sense when it becomes a lens inside the spatial collection?

This question gates later additions; it does not expand the C0 prototype into multiple lenses, lyrics, or provider work.

The staged follow-on work and acceptance gates are tracked in [`CHIASM_CAMPAIGN.md`](CHIASM_CAMPAIGN.md).

## Keyboard navigation

Arrow keys pan the field and `Shift` with an arrow uses a shorter step. Use
`[` / `]` to focus the previous or next album in collection
order; Chiasm centers it while preserving zoom. If the album lens was open, it
stays open as focus moves. Use `Enter` to open or close the lens, `Ctrl+Tab` /
`Ctrl+Shift+Tab` to switch between Horizon and Trace, `PageUp` / `PageDown`
to browse older / newer Trace stops, `1` to `3` to follow a Horizon or Trace
entry, and `H` or `Home` to return to the starting view. In integrated Melodex,
`Ctrl+Enter` starts playback from the focused album.

## C4 local playback bridge

In the Melodex app, open **Explore → Chiasm** or choose Chiasm from the command palette. The page adapts the local Album Wall collection and keeps album track lists in the host. Double-click an album or press play in its attached lens to start that album through Melodex's existing `FlowPlayer`; the in-field transport, `Space`, and `N` control playback while the field stays visible. Leaving the page keeps the field mounted so the listener can return to the same view.

The standalone `python -m chiasm.run` demo remains a fictional 50-album field with mock-play. Chiasm does not create a separate audio engine, and this stage does not add provider playback.

## C5 explainable Arc

In the integrated field, open an album lens and choose **Start Arc**, or focus an album and press `A`. Arc continues through at most twelve playable local albums, using explicit same-artist links first, then shared genre labels. If those links are missing, the field labels its alphabetical fallback. It never treats distance on screen as musical evidence. The next album receives a gold dashed ring, and the transport explains the choice.

Open another album's lens and choose **Set as next album** (or focus it and press `A`) to steer the route. **Pause Arc** and `Space` pause or resume the route; **Take Over** or `T` ends the Arc queue while the current track continues. Starting direct playback from another album also returns control to the listener.

## C6 Horizon and relations

The focused album's existing lens is also its **Horizon**. It names up to three albums connected by same-artist metadata, shared genre labels, or analyzed sound-profile links from the Music Map. If a linked album is visible, a line from the focused album shows the connection; choose a Horizon row or press `1` to `3` to move to a distant linked album and open its lens while keeping the current zoom. The lens also counts albums whose relation remains unresolved. Unresolved does not mean unrelated, and proximity by itself never creates a link.

Audio-profile evidence reuses local analyzed tracks and is capped to a deterministic sample of 700 track profiles for responsiveness. The displayed 0–1 score is a Music Map similarity score, not a probability; the lens shows the supporting track-link count and whether the current album is in the sound-link sample. Region labels appear only when provided by the collection. Chiasm does not infer places from artist names.

## C7 Trace and return

Open an album lens and switch between **Horizon** and **Trace** in the same attached surface. Use `Ctrl+Tab` to switch panels and `Ctrl+Shift+Tab` to switch back. Trace records album focus changes and album-level listening stops on this device, up to 48 stops. Consecutive focus and listening activity on one album coalesces into a single stop. Each entry keeps only its album ID, title, artist, activity type, and time; full track listening history remains in its existing store.

Trace shows two stops at a time, with Earlier and Later controls for the rest of the route. Selecting an entry centers that album and opens its lens without changing zoom or the field's stored positions. The play control starts the selected album through the existing local queue. It begins at the album rather than restoring a saved track position. Entries for albums outside the current collection remain visible but cannot be played. The P13 design gate remains:

> Will this component still make sense when it becomes a lens inside the spatial collection?

## C8 real collection foundations

The integrated field now uses a narrow adapter to Melodex's existing local catalog, Album Wall model, cached artwork service, and FlowPlayer host path. Collection and position work stays in the background. It considers up to 5,000 tracks for positions, keeps the existing 700-track Horizon evidence sample, and displays up to 1,200 albums. If Flow analysis is unavailable, the field uses stable metadata positions; if the local provider is unavailable, it clears cleanly and reports the state.

Album art loads only for visible and near-visible records at album/detail zoom and for the focused album lens. Each visible-set context requests up to 24 images, decoded off the UI thread and held in a 48-image memory cache. The metadata service checks local artwork and its existing cache only; missing or unreadable art keeps the procedural cover motif. Chiasm does not start online lookups or add another artwork surface.

## Relationship to Melodex

Melodex remains the stable existing application.

Chiasm should initially reuse proven Melodex library, playback, caching and provider foundations while experimenting with a radically different interaction model.

No production Melodex behavior should be changed merely to satisfy the Chiasm prototype.
