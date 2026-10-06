from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text("utf-8")


def main() -> int:
    errors: list[str] = []
    root_readme = read("README.md")
    docs_home = read("docs/README.md")
    start = read("docs/START_HERE.md")
    complete_index = read("docs/ALL_DOCUMENTATION.md")
    first_contribution = read("docs/FIRST_CONTRIBUTION.md").casefold()
    gateway = read("docs/DEVELOPERS.md")
    developer_index = read("docs/developers/README.md")
    app = read("desktop/melodex/app.py")
    mode = read("desktop/melodex/chiasm_feature.py")
    field = read("desktop/chiasm/field_view.py")

    if '<a href="docs/README.md">Docs</a>' not in root_readme:
        errors.append("README must link to the Chiasm documentation map")
    if "docs/FIRST_CONTRIBUTION.md" not in root_readme:
        errors.append("README must link to Chiasm contribution onboarding")
    for link in ("START_HERE.md", "DEVELOPERS.md", "ALL_DOCUMENTATION.md", "FIRST_CONTRIBUTION.md"):
        if link not in docs_home:
            errors.append(f"docs/README.md must link to {link}")
    if "friendly documentation map" not in docs_home.casefold():
        errors.append("docs/README.md must identify itself as the friendly documentation map")
    if "complete documentation index" not in complete_index.casefold():
        errors.append("docs/ALL_DOCUMENTATION.md must identify itself as the complete documentation index")
    if "to the chiasm repository" not in first_contribution:
        errors.append("docs/FIRST_CONTRIBUTION.md must identify Chiasm repository contribution onboarding")
    if "Developer Gateway" not in gateway or "developers/README.md" not in gateway:
        errors.append("docs/DEVELOPERS.md must link to its developer reference index")
    if "Developer Reference Index" not in developer_index or "../DEVELOPERS.md" not in developer_index:
        errors.append("developer reference index must link back to the Developer Gateway")

    # First use stays inside Chiasm: add a collection and follow progress in the field.
    for phrase in ("**Add folder**", "indexing", "spatial field"):
        if phrase.casefold() not in start.casefold():
            errors.append(f"docs/START_HERE.md must explain {phrase!r}")
    if 'QPushButton("＋  Add folder")' not in mode:
        errors.append("Chiasm field must expose the Add folder action")
    if '"Add a music folder to begin exploring"' not in field:
        errors.append("Chiasm field must explain its empty state")
    for phrase in ("enter_chiasm_mode", "menuBar().hide()", "action.setEnabled(False)", "shortcut.setEnabled(False)"):
        if phrase not in mode:
            errors.append(f"Chiasm launch mode must enforce {phrase!r}")
    if "enter_chiasm_mode(win)" not in app:
        errors.append("desktop app must launch directly into Chiasm mode")

    if errors:
        print("Chiasm navigation check failed:")
        for error in errors:
            print(f"  - {error}")
        return 1
    print("Chiasm navigation check passed: docs route, first-use folder flow, and field-only launch agree")
    return 0


if __name__ == "__main__":
    sys.exit(main())
