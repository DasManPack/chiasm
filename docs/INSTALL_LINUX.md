# Install Chiasm on Linux

Chiasm Linux packages are currently test builds from GitHub Actions, not public releases. The workflow currently builds 64-bit x86 packages.

## Download

1. Open the [Build Linux packages workflow](https://github.com/DasManPack/chiasm/actions/workflows/linux.yml).
2. Choose the latest successful run and download `Chiasm-Linux-x86_64`.
3. The artifact contains `Chiasm-linux-x86_64.deb` and `Chiasm-linux-x86_64.AppImage`.

On Ubuntu or Debian, install the `.deb` from its download folder:

```bash
sudo apt install ./Chiasm-linux-x86_64.deb
```

On another compatible distribution, make the AppImage executable and run it:

```bash
chmod +x Chiasm-linux-x86_64.AppImage
./Chiasm-linux-x86_64.AppImage
```

## First use

Chiasm opens in its spatial collection field. Choose **Add folder** if it has no albums yet, select a music folder, and let indexing finish. Your audio files remain in their original locations.

Workflow artifacts expire; a future public release will have its own download instructions.
