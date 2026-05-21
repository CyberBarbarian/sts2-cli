#!/usr/bin/env python3
"""Interactive launcher for sts2-cli.

The launcher selects a display language, a new game or an existing save, then
delegates gameplay to python/play.py. The Windows launchers only provide the
default language; players can still change it at startup.
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
LANGUAGE_CHOICES = [
    ("en", "English", "英文"),
    ("zh", "Chinese", "中文"),
    ("both", "English / Chinese", "双语"),
]


def _tr(lang: str, en: str, zh: str) -> str:
    if lang == "zh":
        return zh
    if lang == "both":
        return f"{en} / {zh}"
    return en


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


def _normalize_language(lang: str) -> str:
    valid = {code for code, _en, _zh in LANGUAGE_CHOICES}
    return lang if lang in valid else "en"


def _language_label(code: str, lang: str) -> str:
    for choice_code, en_label, zh_label in LANGUAGE_CHOICES:
        if choice_code == code:
            return zh_label if lang == "zh" else en_label
    return code


def _select_language(default_lang: str) -> str:
    default_lang = _normalize_language(default_lang)
    print(f"\n-- {_tr(default_lang, 'Choose Language', '选择语言')} --")
    for index, (code, en_label, zh_label) in enumerate(LANGUAGE_CHOICES, 1):
        label = zh_label if default_lang == "zh" else en_label
        marker = _tr(default_lang, " (default)", " (默认)") if code == default_lang else ""
        print(f"  {index}  {label}{marker}")

    default_label = _language_label(default_lang, default_lang)
    prompt = _tr(
        default_lang,
        f"Choose language / 选择语言 (1-{len(LANGUAGE_CHOICES)}, default {default_label}): ",
        f"选择语言 / Choose language (1-{len(LANGUAGE_CHOICES)}, 默认 {default_label}): ",
    )
    while True:
        raw = _prompt_line(prompt).strip()
        if not raw:
            return default_lang
        if raw.isdigit():
            index = int(raw)
            if 1 <= index <= len(LANGUAGE_CHOICES):
                return LANGUAGE_CHOICES[index - 1][0]

        lowered = raw.lower()
        for code, en_label, zh_label in LANGUAGE_CHOICES:
            if lowered in {code, en_label.lower(), zh_label.lower()}:
                return code
        print(_tr(
            default_lang,
            f"  Invalid language; enter 1-{len(LANGUAGE_CHOICES)}, en, zh, or both.",
            f"  语言无效；请输入 1-{len(LANGUAGE_CHOICES)}、en、zh 或 both。",
        ))


def _pick_int(prompt: str, lo: int, hi: int, default: int | None = None, lang: str = "en") -> int:
    while True:
        raw = _prompt_line(prompt)
        if not raw and default is not None:
            return default
        try:
            value = int(raw)
        except ValueError:
            print(f"  {_tr(lang, f'Enter an integer from {lo} to {hi}.', f'请输入 {lo} 到 {hi} 之间的整数。')}")
            continue
        if lo <= value <= hi:
            return value
        print(f"  {_tr(lang, f'Enter an integer from {lo} to {hi}.', f'请输入 {lo} 到 {hi} 之间的整数。')}")


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
    print(f"\n-- {_tr(lang, 'Select Character', '选择角色')} --")
    for index, cli_name in enumerate(CLI_CHARACTERS):
        print(f"  {index}  {_character_display(titles, cli_name, lang)}  ({cli_name})")

    index = _pick_int(_tr(lang, "\nEnter number (0-4): ", "\n输入编号 (0-4): "), 0, 4, lang=lang)
    character = CLI_CHARACTERS[index]
    ascension = _pick_int(
        _tr(
            lang,
            "\nAscension level 0-10. Press Enter for standard mode (0): ",
            "\n进阶等级 0-10。直接回车为标准模式 (0): ",
        ),
        0,
        10,
        default=0,
        lang=lang,
    )
    print(f"\n{_tr(lang, 'Starting', '开始')}: {_character_display(titles, character, lang)}  |  {_tr(lang, 'Ascension', '进阶')} {ascension}\n")
    _run_play(["--character", character, "--ascension", str(ascension)], lang)


def _menu_load_save(titles: dict[str, str], lang: str) -> None:
    entries = _collect_save_entries()
    if not entries:
        print(f"\n  {_tr(lang, 'No .save or .json files found under saves/.', 'saves/ 下没有找到 .save 或 .json 文件。')}\n")
        return

    print(f"\n-- {_tr(lang, 'Load Save', '读取存档')} --")
    print(f"  [continue] = {_tr(lang, 'native game .save', '原生游戏 .save')}")
    print(f"  [replay]   = {_tr(lang, '.json command replay', '.json 命令回放')}\n")
    for index, entry in enumerate(entries, 1):
        tag = "continue" if entry["kind"] == "native" else "replay"
        print(f"  {index:2}  [{tag}]  {_format_entry(titles, entry, lang)}")

    print(f"\n  0  {_tr(lang, 'Back', '返回')}")
    choice = _pick_int(_tr(lang, "\nEnter number: ", "\n输入编号: "), 0, len(entries), lang=lang)
    if choice == 0:
        return

    selected = entries[choice - 1]
    rel_path = os.path.relpath(selected["path"], ROOT)
    if selected["kind"] == "native":
        print(f"\n{_tr(lang, 'Loading native save', '正在读取原生存档')}: {rel_path}\n")
        _run_play(["--continue", rel_path], lang)
    else:
        print(f"\n{_tr(lang, 'Loading replay file', '正在读取回放文件')}: {rel_path}\n")
        _run_play(["--load", rel_path], lang)


def _main_interactive(lang: str) -> None:
    lang = _select_language(lang)
    sys.path.insert(0, os.path.join(ROOT, "python"))
    import play as play_mod  # noqa: PLC0415

    play_mod.ensure_setup()
    titles = _load_character_titles()

    while True:
        print(
            f"""
=============================
      Slay the Spire 2 CLI
=============================

  1  {_tr(lang, 'New game', '新游戏')}
  2  {_tr(lang, 'Load save', '读取存档')}
  3  {_tr(lang, 'Language', '语言')}: {_language_label(lang, lang)}
  0  {_tr(lang, 'Exit', '退出')}
"""
        )
        choice = _prompt_line(_tr(lang, "Choose (0-3): ", "选择 (0-3): ")).lower()
        if choice in ("0", "q", "quit", "exit", ""):
            print(_tr(lang, "Goodbye.", "再见。"))
            break
        if choice == "1":
            _menu_new_game(titles, lang)
        elif choice == "2":
            _menu_load_save(titles, lang)
        elif choice == "3":
            lang = _select_language(lang)
        else:
            print(f"  {_tr(lang, 'Invalid input; enter 0, 1, 2, or 3.', '输入无效；请输入 0、1、2 或 3。')}")


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
