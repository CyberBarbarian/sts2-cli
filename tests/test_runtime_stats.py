def test_runtime_stats_can_force_collection_without_replacing_run(game):
    started = game.start(seed="runtime-stats")

    stats = game.send({"cmd": "runtime_stats", "collect": True})
    second_stats = game.send({"cmd": "runtime_stats", "collect": False})

    assert started["type"] == "decision"
    assert stats["type"] == "runtime_stats"
    assert stats["collection_forced"] is True
    assert stats["managed_heap_bytes"] > 0
    assert stats["working_set_bytes"] > 0
    assert second_stats["type"] == "runtime_stats"
