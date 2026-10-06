# Chiasm spatial field prototype

This standalone prototype explores the collection as a stable, navigable 2D field. It does not import Melodex UI modules or start player, provider, library scan, lyrics, or other production services.

Run it from the desktop project directory:

```bash
python -m chiasm.run
```

Use `python -m chiasm.run --windowed` for a development window.

- Drag empty space or an album to pan; the system drag threshold prevents small click jitter from starting a pan.
- Use the mouse wheel to zoom around the pointer. Trackpad scrolling pans the field; a pinch zooms around the gesture point.
- Use the arrow keys to pan, Shift+arrows for smaller steps, and `+`/`-` to zoom around the center.
- When away from the starting field, follow the small arrow cue toward Home or click it to return. `H` and `Home` do the same.
- Hover for a glance; click an album to focus it.
- Press `Enter` to open the focused album's attached lens. It shows the album and its Horizon links; press `Escape` or click `×` to close it while keeping the focus. A second `Escape` releases focus.
- In the standalone prototype, double-click shows a local mock-play cue. In Melodex, Chiasm loads the local album collection and double-click starts that album through Melodex's existing player.
- In Melodex, use the in-field transport buttons, `Space` for play/pause, and `N` for the next queued track. The field and camera remain present while the music plays; navigating away and back preserves the field view.
- The focused album's attached lens is its Horizon. It names up to three albums linked by same-artist metadata, shared genre labels, or analyzed audio profiles. When a linked album is visible, a line connects it to the focused album; choose a Horizon row or press `1` to `3` to move the field to a distant linked album and open its lens. The row states its evidence. No named link is shown as unresolved, not as proof that two albums are unrelated. Distance alone never creates a relation.
- Audio-profile links reuse the Music Map's analyzed track relationships, aggregated into album pairs from a deterministic sample of up to 700 tracks. The lens shows the audio score and supporting track-link count; the 0–1 score is not a probability. It also shows when the selected album is outside the sound-link sample. Collection region names remain blank unless explicitly present in the local metadata.
- In Melodex, open an album lens and choose **Start Arc** (or focus the album and press `A`) to continue through up to twelve local albums. The next album is chosen by an explicit same-artist or shared-genre label; if those are missing, Chiasm labels the alphabetical fallback. A gold dashed ring marks the next album. Set another album as next from its lens to steer; use **Pause Arc** or `Space` to pause/resume, and **Take Over** or `T` to end the route while the current track continues.

The small status label names the current information layer and zoom. The standalone version has fifty fictional records with deterministic coordinates in five regions. The Melodex page adapts local album rows into field records and keeps their track lists behind the host playback boundary. At wide scale, explicit region names provide orientation; at close scale, album labels resolve progressively. Click targets preserve a 44 px minimum diameter at overview scale. Focus changes nearby scale and depth cues while every album keeps its stored position. The lens stays attached to the focused album as the camera moves. Horizon lines and Arc recommendations use named collection evidence; field distance alone never implies a relationship. The contextual Home cue is drawn inside the field and remains useful from any future spatial lens.
