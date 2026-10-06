# Install Melodex (separate project)

This page is for the Melodex music player, not Chiasm. For Chiasm, use the [Chiasm v0.1.1 preview](https://github.com/DasManPack/chiasm/releases/tag/v0.1.1) and the [Chiasm documentation map](README.md).

You do **not** need Python, Git, Android Studio, or any developer tools if you install a release build.

> **Tagged releases vs `main`:** the files below are produced by the release workflows. Documentation on `main` can describe newer development features than the latest downloadable release. See [Releases, `main`, and version numbers](RELEASES_AND_MAIN.md).

Download the latest release from:

**https://github.com/Cliff-Lee/melodex/releases/latest**

Then choose your platform:

| Platform | Download this | Guide |
| --- | --- | --- |
| Apple Silicon Mac (M1/M2/M3/M4…) | `Melodex-macOS-arm64.dmg` | [macOS](INSTALL_MACOS.md) |
| Intel Mac | `Melodex-macOS-intel.dmg` | [macOS](INSTALL_MACOS.md) |
| Windows 10/11 | `Melodex-Windows-x64-Setup.exe` | [Windows](INSTALL_WINDOWS.md) |
| Windows portable | `Melodex-Windows-portable.zip` | [Windows](INSTALL_WINDOWS.md) |
| Ubuntu/Debian x86_64 | `Melodex-linux-x86_64.deb` | [Linux](INSTALL_LINUX.md) |
| Other glibc Linux desktops x86_64 | `Melodex-linux-x86_64.AppImage` | [Linux](INSTALL_LINUX.md) |
| Android phone/tablet | `Melodex-Android.apk` | [Android](INSTALL_ANDROID.md) |

> **Android works differently.** The Android app is currently a client for a Melodex Provider Bridge running on a Mac, Windows PC, NAS, or home server. For the easiest Android setup, install Melodex on the computer first, add your music there, then pair the phone with that computer.

Do **not** download these unless you know you need them:

- `.aab` — intended for app-store publishing, not normal Android installation;
- `source.zip` — source code for developers;
- checksums or build artifacts — useful for verification/development, not required for a normal install.

## After installation

For the quickest first experience:

1. Open Melodex.
2. Open **My Music**.
3. Choose **+ Add music** and select a folder containing music you are allowed to play.
4. Browse the visual Albums view or return to **Home**.
5. Choose **Play something**.

That is enough to start.

Use **Find missing artwork** only when you explicitly want Melodex to look online for missing covers. Artist photos and metadata enrichment are also optional.

Provider configuration, Power tools, third-party plugins and LLM control are optional.

## Need help?

- [Start Here](START_HERE.md)
- [User Guide](USER_GUIDE.md)
- [Troubleshooting](TROUBLESHOOTING.md)
- [FAQ](FAQ.md)
