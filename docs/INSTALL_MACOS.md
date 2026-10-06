# Install Chiasm on macOS

Chiasm is currently distributed as a test build from GitHub Actions, not as a public release.

## Download

1. Open the [Build desktop workflow](https://github.com/DasManPack/chiasm/actions/workflows/desktop.yml).
2. Choose the latest successful run and download `Chiasm-macOS-arm64` for Apple Silicon or `Chiasm-macOS-intel` for an Intel Mac.
3. Unzip the artifact and open its `Chiasm-*.dmg` file.
4. Drag **Chiasm** into **Applications**, eject the disk image, then launch Chiasm.

Check **Apple menu → About This Mac** if you are unsure which Mac you have.

## First use

Chiasm opens in its spatial collection field. Choose **Add folder** if it has no albums yet, select a music folder, and let indexing finish. Your audio files remain in their original locations.

These test builds are not notarized. Only follow macOS's open-anyway steps for a build downloaded from the Chiasm workflow above. Workflow artifacts expire; a future public release will have its own download instructions.
