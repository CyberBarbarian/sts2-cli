from __future__ import annotations

import importlib.util
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("game_log_for_tests", ROOT / "python" / "game_log.py")
game_log = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(game_log)


def test_game_logger_can_write_to_explicit_artifact_path(tmp_path):
    path = tmp_path / "run" / "engine_trace.jsonl"
    logger = game_log.GameLogger("Ironclad", "fixed_seed", path=path)

    logger.log_state({"type": "ready"})
    logger.log_action({"cmd": "start_run", "seed": "fixed_seed"})
    logger.close()

    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert [row["type"] for row in rows] == ["state", "action"]
    assert rows[0]["data"] == {"type": "ready"}
    assert rows[1]["data"]["seed"] == "fixed_seed"


def test_default_log_paths_are_collision_safe_under_concurrency(tmp_path, monkeypatch):
    monkeypatch.setattr(game_log, "LOG_DIR", str(tmp_path))

    def create_log(_index):
        logger = game_log.GameLogger("Ironclad", "same_seed")
        path = logger.path
        logger.close()
        return path

    with ThreadPoolExecutor(max_workers=12) as executor:
        paths = list(executor.map(create_log, range(48)))

    assert len(paths) == len(set(paths)) == 48
    assert all(Path(path).is_file() for path in paths)


def test_concurrent_cleanup_tolerates_a_log_removed_by_another_worker(tmp_path, monkeypatch):
    old_log = tmp_path / "old.jsonl"
    old_log.write_text("{}\n", encoding="utf-8")
    monkeypatch.setattr(game_log, "LOG_DIR", str(tmp_path))
    monkeypatch.setattr(game_log.os.path, "getmtime", lambda _path: 0)

    def removed_concurrently(_path):
        raise FileNotFoundError("removed concurrently")

    monkeypatch.setattr(game_log.os, "remove", removed_concurrently)

    game_log.cleanup_old_logs()
