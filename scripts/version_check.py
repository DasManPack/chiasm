from __future__ import annotations

import argparse
import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read_text(path: str) -> str:
    return (ROOT / path).read_text("utf-8")


def canonical_version() -> str:
    return read_text("VERSION").strip()


def desktop_package_version() -> str:
    data = tomllib.loads(read_text("desktop/pyproject.toml"))
    return str(data["project"]["version"])


def python_module_version() -> str:
    text = read_text("desktop/melodex/__init__.py")
    match = re.search(r'__version__\s*=\s*"([^"]+)"', text)
    return match.group(1) if match else ""


def windows_installer_version() -> str:
    text = read_text("desktop/installer.iss")
    match = re.search(r'#define\s+MyAppVersion\s+"([^"]+)"', text)
    return match.group(1) if match else ""


def android_version() -> tuple[int, str]:
    text = read_text("android/app/build.gradle.kts")
    code = re.search(r"versionCode\s*=\s*(\d+)", text)
    name = re.search(r'versionName\s*=\s*"([^"]+)"', text)
    return (
        int(code.group(1)) if code else 0,
        name.group(1) if name else "",
    )


def release_triplet(version: str) -> tuple[int, int, int]:
    base = version.split(".dev", 1)[0]
    match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", base)
    if not match:
        raise ValueError(
            f"VERSION must be X.Y.Z or X.Y.Z.devN; received {version!r}"
        )
    return tuple(int(part) for part in match.groups())


def expected_android_code(version: str) -> int:
    major, minor, patch = release_triplet(version)
    return major * 10000 + minor * 100 + patch


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Check Chiasm preview-version consistency."
    )
    parser.add_argument(
        "--release-tag",
        default="",
        help="Optional Git tag, for example v0.3.0. Release tags require a non-dev VERSION.",
    )
    args = parser.parse_args(argv)

    version = canonical_version()
    errors: list[str] = []

    try:
        expected_code = expected_android_code(version)
    except ValueError as exc:
        print(f"Version consistency check failed:\n  - {exc}")
        return 1

    surfaces = {
        "desktop/pyproject.toml": desktop_package_version(),
        "desktop/melodex/__init__.py": python_module_version(),
        "desktop/installer.iss": windows_installer_version(),
        "Android versionName": android_version()[1],
    }
    for label, value in surfaces.items():
        if value != version:
            errors.append(f"{label} version {value!r} != VERSION {version!r}")

    android_code, _ = android_version()
    if android_code != expected_code:
        errors.append(
            f"Android versionCode {android_code} != expected {expected_code} "
            f"for app version {version!r}"
        )

    tag = str(args.release_tag or "").strip()
    if tag:
        expected = tag[1:] if tag.startswith("v") else tag
        if ".dev" in version:
            errors.append(
                f"release tag {tag!r} cannot be built while VERSION is "
                f"development version {version!r}"
            )
        if version != expected:
            errors.append(
                f"release tag {tag!r} does not match VERSION {version!r}"
            )

    if errors:
        print("Version consistency check failed:")
        for error in errors:
            print(f"  - {error}")
        return 1

    print(
        f"Version consistency check passed: app={version}, "
        f"androidVersionCode={android_code}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
