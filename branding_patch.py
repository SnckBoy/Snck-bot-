#!/usr/bin/env python3
"""Apply the canonical Snck branding to an existing installation."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent

FILES = [ROOT / "bot.py", ROOT / "launcher.py", ROOT / "snck_panel.py", ROOT / "snck_panel_v2.py", ROOT / "panel.py"]
REPLACEMENTS = {
    "PapiaGamerz VMS": "Snck Discord VPS Deploy Bot",
    "PapiaGamerz": "Clark",
    "Hopingboyz": "Snck",
    "Hoping Boy": "Snck",
    "Hopingboy": "Snck",
}

def patch(path: Path) -> bool:
    if not path.exists():
        return False
    text = path.read_text(encoding="utf-8")
    original = text
    for old, new in REPLACEMENTS.items():
        text = text.replace(old, new)
    if text != original:
        path.write_text(text, encoding="utf-8")
        return True
    return False

def main() -> None:
    changed = sum(patch(path) for path in FILES)
    env = ROOT / ".env"
    if env.exists():
        lines = env.read_text(encoding="utf-8").splitlines()
        values = {
            "BOT_NAME": "Snck Discord VPS Deploy Bot",
            "BOT_DEVELOPER": "Clark",
        }
        found = set()
        out = []
        for line in lines:
            key = line.split("=", 1)[0] if "=" in line else ""
            if key in values:
                out.append(f"{key}={values[key]}")
                found.add(key)
            else:
                out.append(line)
        for key, value in values.items():
            if key not in found:
                out.append(f"{key}={value}")
        env.write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"Snck branding applied ({changed} source files changed).")

if __name__ == "__main__":
    main()
