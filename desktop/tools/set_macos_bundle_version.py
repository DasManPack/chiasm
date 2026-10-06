#!/usr/bin/env python3
from __future__ import annotations

import argparse
import plistlib
import re
from pathlib import Path


def bundle_versions(version: str) -> tuple[str, str]:
    text = str(version or "").strip()
    base = text.split(".dev", 1)[0]
    match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", base)
    if not match:
        raise ValueError(
            f"VERSION must be X.Y.Z or X.Y.Z.devN; received {version!r}"
        )
    major, minor, patch = (int(part) for part in match.groups())
    short_version = f"{major}.{minor}.{patch}"
    build_version = str(major * 10000 + minor * 100 + patch)
    return short_version, build_version


def stamp_bundle(app_path: Path, version: str) -> tuple[str, str]:
    app_path = Path(app_path)
    plist_path = app_path / "Contents" / "Info.plist"
    if not plist_path.is_file():
        raise FileNotFoundError(f"Info.plist not found: {plist_path}")

    short_version, build_version = bundle_versions(version)
    with plist_path.open("rb") as handle:
        payload = plistlib.load(handle)

    payload["CFBundleShortVersionString"] = short_version
    payload["CFBundleVersion"] = build_version

    with plist_path.open("wb") as handle:
        plistlib.dump(payload, handle, sort_keys=False)

    return short_version, build_version


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Stamp a PyInstaller macOS app bundle with the Chiasm preview version."
    )
    parser.add_argument("app", type=Path)
    parser.add_argument(
        "--version-file",
        type=Path,
        default=Path(__file__).resolve().parents[2] / "VERSION",
    )
    args = parser.parse_args()

    version = args.version_file.read_text("utf-8").strip()
    short_version, build_version = stamp_bundle(args.app, version)
    print(
        f"Stamped {args.app.name}: "
        f"CFBundleShortVersionString={short_version}, "
        f"CFBundleVersion={build_version}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
