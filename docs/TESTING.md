# Test Chiasm

Chiasm is an early spatial music-exploration experiment. We need to learn whether the field feels clear and inviting with a real collection, and where its minimal interface stops explaining itself.

## Start a test

1. Open the [desktop workflow](https://github.com/DasManPack/chiasm/actions/workflows/desktop.yml).
2. Open the latest successful run and download the artifact for your computer: Apple Silicon Mac, Intel Mac, or Windows.
3. Extract the ZIP. On macOS, open the DMG and move Chiasm to Applications. On Windows, run the installer or portable app.
4. Add or select a local music folder. Chiasm reads the existing files in place; it does not move them.

The public preview is experimental. The CI artifacts linked below are temporary builds from the matching Chiasm commit, retained for a limited time; macOS is not notarized and Windows is not code signed.

### Current C11 test build

The discovery-loop build is commit [`609110a`](https://github.com/DasManPack/chiasm/commit/609110a89df691bbbbfeb645b4719d04848ca687). Use the matching workflow artifact for your device, or download the newer [v0.1.2 public preview](https://github.com/DasManPack/chiasm/releases/tag/v0.1.2) after its release assets finish building:

- [Desktop builds](https://github.com/DasManPack/chiasm/actions/runs/37477412509): `Chiasm-macOS-arm64`, `Chiasm-macOS-intel`, or `Chiasm-Windows-x64`.
- [Linux builds](https://github.com/DasManPack/chiasm/actions/runs/37477412429): `Chiasm-Linux-x86_64` (`.deb` and AppImage).
- [Android build](https://github.com/DasManPack/chiasm/actions/runs/37477412604): `Chiasm-Android` (`.apk` and `.aab`). The Android app is a bridge companion; C11's spatial discovery task is desktop-only.

### C11 discovery-loop test

Run this with five people who have not used Chiasm. Prepare their own music collection in advance and leave the populated field ready. Do not explain the controls or point out Find, Horizon, or Trace before starting the timer.

Read this task aloud: **“Start from an album you know well. Explore an album you do not know well, play it, then return to the album you started from.”** Allow three minutes without coaching. If someone asks for help, note the question and offer help only after the timed attempt ends.

For each person, record whether they completed the task, elapsed time, where they hesitated, what relationship they thought connected the albums, and whether they returned to the correct starting album. Do not record album titles or other details from their private collection. Count a success only if they complete the loop within three minutes, describe the displayed relationship in their own words, and return to the starting album. The gate is at least four successes out of five; keep each person's hesitation notes even if they succeed.

This test measures the discovery loop after a collection is ready. Record folder import, playback failures, accessibility issues, and screen-size problems separately so they remain visible rather than being hidden by the timed task.

## A useful 10-minute test

- Can you tell what the field represents without reading instructions?
- Can you find an album you recognize and focus it?
- Can you move across the field without losing your sense of place?
- Does the album lens give you useful information without taking over the screen?
- Do Horizon links explain why two albums are connected?
- Does Arc make its next choice understandable and easy to override?
- Can you return to where you were after exploring elsewhere?
- Does the interface stay responsive while covers and a large collection load?
- Which labels or controls did you need, and which felt unnecessary?

Try a small collection and a large one if possible. Keyboard navigation and reduced-motion feedback are especially useful. Please describe the operating system, device, approximate collection size, and what you did just before any problem.

## Send feedback

- [Report a bug](https://github.com/DasManPack/chiasm/issues/new?template=bug_report.yml)
- [Share tester feedback](https://github.com/DasManPack/chiasm/issues/new?template=tester_feedback.yml)
- [Discuss an idea](https://github.com/DasManPack/chiasm/discussions)

Do not attach music files, credentials, private media URLs, or other secrets. Chiasm derives parts of its local-library and playback foundation from Melodex; mention if you are also running Melodex when reporting a data or playback issue.
