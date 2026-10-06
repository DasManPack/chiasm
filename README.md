<p align="center">
  <img src="docs/images/chiasm-mark.svg" width="112" alt="Chiasm mark: connected paths through a collection">
</p>

<p align="center"><strong>Explore your music, spatially.</strong></p>

<p align="center">
  <a href="https://github.com/DasManPack/chiasm/actions/workflows/desktop.yml"><strong>Download a test build</strong></a> ·
  <a href="docs/CHIASM.md">How Chiasm works</a> ·
  <a href="docs/TESTING.md">Test Chiasm</a> ·
  <a href="docs/CHIASM_CAMPAIGN.md">Development notes</a>
</p>

# Chiasm

Chiasm is an experimental project about exploring a music collection as a place. Albums become landmarks in a navigable visual field. You move through the collection, focus on an album, and follow relationships when you choose. Detail appears with attention; most of the time, the collection itself is the interface.

The aim is **music exploration with very little permanent text**: less managing lists and screens, more noticing where you might go next.

## A separate experiment, built from Melodex

Chiasm is a distinct project derived from the open-source [Melodex](https://github.com/Cliff-Lee/melodex) codebase. It is not a Melodex release or a renamed copy. The experiment reuses Melodex's local library, artwork cache, and playback foundations while developing a different, spatial-first interaction model. Melodex remains a separate project.

This preview retains inherited Melodex modules internally, including pages and technical names that support compatibility. Chiasm launches directly into its spatial field; those inherited pages, menus, and shortcuts are removed from the visible Chiasm experience. The public identity, launcher, app window, and test packages are Chiasm.

## Try the preview

1. Open the [Build desktop workflow](https://github.com/DasManPack/chiasm/actions/workflows/desktop.yml) and choose its latest successful run.
2. Download the `Chiasm-macOS-arm64`, `Chiasm-macOS-intel`, or `Chiasm-Windows-x64` artifact for your computer.
3. Extract the ZIP. On macOS, open the included DMG and move Chiasm to Applications. On Windows, run the installer or the portable app.
4. Add or select a local music folder, then explore the spatial field. Your audio files stay where they are.

These are temporary test artifacts, not signed or notarized public releases. GitHub keeps workflow artifacts for a limited time. The current preview has been built on Apple Silicon, Intel Mac, and Windows; human usability and accessibility checks are still in progress.

### Android companion

The [Android workflow](https://github.com/DasManPack/chiasm/actions/workflows/android.yml) produces `Chiasm-Android.apk` and `Chiasm-Android.aab`. The app now has Chiasm's name, icon, and separate Android package identity. Its current Android experience is still an early bridge companion that connects to a Chiasm desktop host; the spatial collection field is currently desktop-focused.

## Run the isolated field prototype

The repository also contains a small standalone field demo with fictional albums and mock playback:

```bash
cd desktop
python -m chiasm.run
```

For the integrated test app, see [build and test instructions](docs/CHIASM.md).

## Project principles

- The collection is the interface.
- Keep the field calm and legible; motion follows user intent.
- Reveal labels and controls when they help with a decision.
- Show why a relationship exists; screen distance alone is not evidence.
- Keep local music local and make optional services clear.
- Prefer responsiveness and spatial memory over visual effects.

## Lineage and licence

Chiasm's original spatial field work is combined with software derived from Melodex. The inherited code and third-party components retain their existing notices and licences; see [LICENSE](LICENSE) and [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). Chiasm-specific contributions are distributed under the MIT licence as well.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for the development setup. Please frame product ideas around spatial music exploration and explain how they fit the principle: **will this still make sense as a lens inside the collection?**
