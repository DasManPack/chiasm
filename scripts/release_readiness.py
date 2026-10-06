from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
errors: list[str] = []

required_files = [
    "VERSION",
    "README.md",
    "docs/releases/next.md",
    "docs/INSTALL_LINUX.md",
    "docs/INSTALL_MACOS.md",
    "docs/INSTALL_WINDOWS.md",
    "docs/INSTALL_ANDROID.md",
    ".github/workflows/release.yml",
    ".github/workflows/test.yml",
    ".github/workflows/desktop.yml",
    ".github/workflows/linux.yml",
    ".github/workflows/android.yml",
    "desktop/build_linux.sh",
    "desktop/build_macos.sh",
    "desktop/build_windows.ps1",
    "desktop/linux/build_packages.py",
    "scripts/fluid_ci_gate.py",
    "scripts/fluid_gate_check.py",
    "docs/RESPONSIVENESS.md",
    "android/app/build.gradle.kts",
]
for rel in required_files:
    if not (ROOT / rel).is_file():
        errors.append(f"missing release surface: {rel}")

version = (ROOT / "VERSION").read_text("utf-8").strip()
match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)(?:\.dev(\d+))?", version)
if not match:
    errors.append(f"VERSION is not a supported app version: {version!r}")
elif match.group(4) is None:
    release_notes = ROOT / "docs" / "releases" / f"v{version}.md"
    if not release_notes.is_file():
        errors.append(
            f"stable VERSION {version} requires release notes: "
            f"docs/releases/v{version}.md"
        )

readme = (ROOT / "README.md").read_text("utf-8")
for label, target in [
    ("Linux", "docs/INSTALL_LINUX.md"),
    ("macOS", "docs/INSTALL_MACOS.md"),
    ("Windows", "docs/INSTALL_WINDOWS.md"),
    ("Android", "docs/INSTALL_ANDROID.md"),
]:
    if target not in readme:
        errors.append(f"README download/install section is missing {label}: {target}")

next_notes = (ROOT / "docs/releases/next.md").read_text("utf-8")
base_version = ".".join(version.split(".")[:3])
if base_version not in next_notes:
    errors.append(
        f"docs/releases/next.md does not mention the current target {base_version}"
    )

stale_release_phrases = [
    "advances one artist at a time",
    "progress is visible on the action button and advances after each album",
    "Find lyrics plugin…",
]
for phrase in stale_release_phrases:
    if phrase.casefold() in next_notes.casefold():
        errors.append(f"stale release-note wording remains: {phrase!r}")

for workflow in ("desktop.yml", "linux.yml", "android.yml"):
    text = (ROOT / ".github" / "workflows" / workflow).read_text("utf-8")
    if "pull_request:" not in text:
        errors.append(f"{workflow} must verify packaging on pull requests")
    if "version_check.py" not in text:
        errors.append(f"{workflow} does not verify application version")

test_workflow = (ROOT / ".github" / "workflows" / "test.yml").read_text("utf-8")
if "Fluid Chiasm release gates" not in test_workflow:
    errors.append("test.yml is missing the dedicated Chiasm release-gate job")
if "python scripts/fluid_ci_gate.py" not in test_workflow:
    errors.append("test.yml does not execute scripts/fluid_ci_gate.py")

release_workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text("utf-8")
if release_workflow.count("python scripts/fluid_ci_gate.py") < 2:
    errors.append(
        "release.yml must run the Chiasm responsiveness gates for both release paths"
    )

bundled = ROOT / "desktop" / "melodex" / "bundled_providers"
required_bundled = {
    "LibriVox-0.1.5.mdxprovider",
    "NicheDB-Radio-0.1.2.mdxprovider",
    "Internet-Archive-Audio-0.1.2.mdxprovider",
}
for name in required_bundled:
    if not (bundled / name).is_file():
        errors.append(f"required bundled provider missing: {name}")
if (bundled / "LibriVox-0.1.2.mdxprovider").exists():
    errors.append("obsolete LibriVox-0.1.2.mdxprovider is still bundled")
if (bundled / "LibriVox-0.1.4.mdxprovider").exists():
    errors.append("obsolete LibriVox-0.1.4.mdxprovider is still bundled")
if (bundled / "NicheDB-Radio-0.1.0.mdxprovider").exists():
    errors.append("obsolete NicheDB-Radio-0.1.0.mdxprovider is still bundled")
if (bundled / "Internet-Archive-Audio-0.1.0.mdxprovider").exists():
    errors.append("obsolete Internet-Archive-Audio-0.1.0.mdxprovider is still bundled")
if (bundled / "Internet-Archive-Audio-0.1.1.mdxprovider").exists():
    errors.append("obsolete Internet-Archive-Audio-0.1.1.mdxprovider is still bundled")

live_smoke = ROOT / "scripts" / "live_bundled_provider_smoke.py"
if not live_smoke.is_file():
    errors.append("live bundled-provider smoke runner is missing")
if not (ROOT / ".github" / "workflows" / "live-bundled-providers.yml").is_file():
    errors.append("manual live bundled-provider verification workflow is missing")

if errors:
    print("Release readiness check failed:\n" + "\n".join(f"- {e}" for e in errors))
    sys.exit(1)

print(
    "Release readiness check passed "
    f"for Chiasm {version}: desktop, Linux, Android, docs and inherited bundled providers."
)
