#!/usr/bin/env python3
"""Interactive launcher for sts2-cli.

The launcher selects a new game or an existing save, then delegates gameplay to
python/play.py. The default display language is English; pass --lang zh or
--lang both when that output is explicitly desired.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime

ROOT = os.path.dirname(os.path.abspath(__file__))
PLAY_PY = os.path.join(ROOT, "python", "play.py")
SAVE_DIR = os.path.join(ROOT, "saves")
LOC_CHARS = os.path.join(ROOT, "localization_zhs", "characters.json")

CLI_CHARACTERS = ["Ironclad", "Silent", "Defect", "Regent", "Necrobinder"]


def _load_character_titles() -> dict[str, str]:
    titles: dict[str, str] = {}
    if not os.path.isfile(LOC_CHARS):
        return titles
    with open(LOC_CHARS, encoding="utf-8") as handle:
        data = json.load(handle)
    for key in ("IRONCLAD", "SILENT", "DEFECT", "REGENT", "NECROBINDER"):
        titles[key] = data.get(f"{key}.title", key)
    return titles


def _character_display(titles: dict[str, str], cli_name: str, lang: str) -> str:
    if lang == "en":
        return cli_name

    localized = titles.get(cli_name.upper(), cli_name)
    if lang == "both" and localized != cli_name:
        return f"{cli_name} / {localized}"
    return localized


def _prompt_line(prompt: str) -> str:
    try:
        return input(prompt).strip()
    except (EOFError, KeyboardInterrupt):
        print()
        raise SystemExit(0) from None


def _pick_int(prompt: str, lo: int, hi: int, default: int | None = None) -> int:
    while True:
        raw = _prompt_line(prompt)
        if not raw and default is not None:
            return default
        try:
            value = int(raw)
        except ValueError:
            print(f"  Enter an integer from {lo} to {hi}.")
            continue
        if lo <= value <= hi:
            return value
        print(f"  Enter an integer from {lo} to {hi}.")


def _collect_save_entries() -> list[dict]:
    if not os.path.isdir(SAVE_DIR):
        return []

    entries: list[dict] = []
    for name in os.listdir(SAVE_DIR):
        path = os.path.join(SAVE_DIR, name)
        if not os.path.isfile(path):
            continue

        stat = os.stat(path)
        if name.endswith(".json"):
            try:
                with open(path, encoding="utf-8") as handle:
                    data = json.load(handle)
                entries.append(
                    {
                        "kind": "replay",
                        "path": path,
                        "name": name,
                        "mtime": stat.st_mtime,
                        "character": data.get("character", "?"),
                        "seed": data.get("seed", "?"),
                        "actions": len(data.get("actions", [])),
                    }
                )
            except (json.JSONDecodeError, OSError):
                pass
        elif name.endswith(".save"):
            try:
                with open(path, encoding="utf-8") as handle:
                    data = json.load(handle)
                players = data.get("players", [])
                entries.append(
                    {
                        "kind": "native",
                        "path": path,
                        "name": name,
                        "mtime": stat.st_mtime,
                        "seed": data.get("rng", {}).get("seed", "?"),
                        "ascension": data.get("ascension", 0),
                        "character_id": players[0].get("character_id", "?") if players else "?",
                    }
                )
            except (json.JSONDecodeError, OSError):
                entries.append(
                    {
                        "kind": "native",
                        "path": path,
                        "name": name,
                        "mtime": stat.st_mtime,
                        "broken": True,
                    }
                )

    entries.sort(key=lambda entry: -entry["mtime"])
    return entries


def _format_entry(titles: dict[str, str], entry: dict, lang: str) -> str:
    timestamp = datetime.fromtimestamp(entry["mtime"]).strftime("%Y-%m-%d %H:%M")
    if entry["kind"] == "replay":
        character = str(entry.get("character", "?"))
        display_name = _character_display(titles, character, lang)
        return f"{entry['name']}  |  {display_name}  |  seed {entry['seed']}  |  {entry['actions']} actions  |  {timestamp}"

    if entry.get("broken"):
        return f"{entry['name']}  |  unreadable save file  |  {timestamp}"

    character_id = str(entry.get("character_id", "?"))
    display_name = _character_display(titles, character_id.title(), lang) if character_id != "?" else "?"
    return f"{entry['name']}  |  {display_name}  |  ascension {entry['ascension']}  |  seed {entry['seed']}  |  {timestamp}"


def _run_play(args: list[str], lang: str) -> int:
    cmd = [sys.executable, PLAY_PY, "--lang", lang, *args]
    result = subprocess.run(cmd, cwd=ROOT, check=False)
    return result.returncode


def _menu_new_game(titles: dict[str, str], lang: str) -> None:
    print("\n-- Select Character --")
    for index, cli_name in enumerate(CLI_CHARACTERS):
        print(f"  {index}  {_character_display(titles, cli_name, lang)}  ({cli_name})")

    index = _pick_int("\nEnter number (0-4): ", 0, 4)
    character = CLI_CHARACTERS[index]
    ascension = _pick_int(
        "\nAscension level 0-10. Press Enter for standard mode (0): ",
        0,
        10,
        default=0,
    )
    print(f"\nStarting: {_character_display(titles, character, lang)}  |  Ascension {ascension}\n")
    _run_play(["--character", character, "--ascension", str(ascension)], lang)


def _menu_load_save(titles: dict[str, str], lang: str) -> None:
    entries = _collect_save_entries()
    if not entries:
        print("\n  No .save or .json files found under saves/.\n")
        return

    print("\n-- Load Save --")
    print("  [continue] = native game .save")
    print("  [replay]   = .json command replay\n")
    for index, entry in enumerate(entries, 1):
        tag = "continue" if entry["kind"] == "native" else "replay"
        print(f"  {index:2}  [{tag}]  {_format_entry(titles, entry, lang)}")

    print("\n  0  Back")
    choice = _pick_int("\nEnter number: ", 0, len(entries))
    if choice == 0:
        return

    selected = entries[choice - 1]
    rel_path = os.path.relpath(selected["path"], ROOT)
    if selected["kind"] == "native":
        print(f"\nLoading native save: {rel_path}\n")
        _run_play(["--continue", rel_path], lang)
    else:
        print(f"\nLoading replay file: {rel_path}\n")
        _run_play(["--load", rel_path], lang)


def _main_interactive(lang: str) -> None:
    sys.path.insert(0, os.path.join(ROOT, "python"))
    import play as play_mod  # noqa: PLC0415

    play_mod.ensure_setup()
    titles = _load_character_titles()

    while True:
        print(
            """
=============================
      Slay the Spire 2 CLI
=============================

  1  New game
  2  Load save
  0  Exit
"""
        )
        choice = _prompt_line("Choose (0-2): ").lower()
        if choice in ("0", "q", "quit", "exit", ""):
            print("Goodbye.")
            break
        if choice == "1":
            _menu_new_game(titles, lang)
        elif choice == "2":
            _menu_load_save(titles, lang)
        else:
            print("  Invalid input; enter 0, 1, or 2.")


def main() -> None:
    parser = argparse.ArgumentParser(description="sts2-cli interactive launcher")
    parser.add_argument(
        "--lang",
        choices=["en", "zh", "both"],
        default="en",
        help="Display language passed to play.py",
    )
    args = parser.parse_args()
    _main_interactive(args.lang)


if __name__ == "__main__":
    main()
