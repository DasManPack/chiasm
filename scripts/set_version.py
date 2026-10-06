from __future__ import annotations

import argparse
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def release_triplet(version: str) -> tuple[int, int, int]:
    base = version.split(".dev", 1)[0]
    match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", base)
    if not match:
        raise ValueError("version must be X.Y.Z or X.Y.Z.devN")
    if ".dev" in version and not re.fullmatch(r"\d+\.\d+\.\d+\.dev\d+", version):
        raise ValueError("development version must use X.Y.Z.devN")
    return tuple(int(part) for part in match.groups())


def android_code(version: str) -> int:
    major, minor, patch = release_triplet(version)
    return major * 10000 + minor * 100 + patch


def replace_once(path: Path, pattern: str, replacement: str) -> None:
    text = path.read_text("utf-8")
    updated, count = re.subn(pattern, replacement, text, count=1, flags=re.MULTILINE)
    if count != 1:
        raise RuntimeError(f"could not find unique version field in {path.relative_to(ROOT)}")
    path.write_text(updated, "utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Set all Chiasm application-version surfaces together."
    )
    parser.add_argument("version", help="X.Y.Z or X.Y.Z.devN")
    args = parser.parse_args()
    version = str(args.version).strip()
    code = android_code(version)

    (ROOT / "VERSION").write_text(version + "\n", "utf-8")

    replace_once(
        ROOT / "desktop/melodex/__init__.py",
        r'__version__\s*=\s*"[^"]+"',
        f'__version__ = "{version}"',
    )
    replace_once(
        ROOT / "desktop/pyproject.toml",
        r'(?m)^version\s*=\s*"[^"]+"',
        f'version = "{version}"',
    )
    replace_once(
        ROOT / "desktop/installer.iss",
        r'(?m)^#define\s+MyAppVersion\s+"[^"]+"',
        f'#define MyAppVersion "{version}"',
    )
    replace_once(
        ROOT / "android/app/build.gradle.kts",
        r'versionCode\s*=\s*\d+',
        f"versionCode = {code}",
    )
    replace_once(
        ROOT / "android/app/build.gradle.kts",
        r'versionName\s*=\s*"[^"]+"',
        f'versionName = "{version}"',
    )

    print(f"Set Chiasm app version to {version} (Android versionCode {code}).")
    print("Run: python scripts/version_check.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
