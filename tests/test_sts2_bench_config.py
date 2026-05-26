import os
import sys

from sts2_bench.run_benchmark import load_benchmark_config


def test_load_benchmark_config_falls_back_to_simple_scalar_parser(tmp_path, monkeypatch):
    config = tmp_path / "benchmark.yaml"
    config.write_text(
        "\n".join(
            [
                "# Top-level scalar config only.",
                "agent: random",
                "base_url: \"\"",
                "model: ''",
                "include_json_state: false",
                "memory_window: 8",
                "max_steps: 300",
                "out: results/random_ironclad_a0.jsonl",
            ]
        ),
        encoding="utf-8",
    )
    for key in (
        "STS2_BENCH_AGENT",
        "STS2_BENCH_BASE_URL",
        "STS2_BENCH_MODEL",
        "STS2_BENCH_INCLUDE_JSON_STATE",
        "STS2_BENCH_MEMORY_WINDOW",
        "STS2_BENCH_MAX_STEPS",
        "STS2_BENCH_OUT",
    ):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setitem(sys.modules, "omegaconf", None)

    load_benchmark_config(config)

    assert os.environ["STS2_BENCH_BASE_URL"] == ""
    assert os.environ["STS2_BENCH_MODEL"] == ""
    assert os.environ["STS2_BENCH_AGENT"] == "random"
    assert os.environ["STS2_BENCH_INCLUDE_JSON_STATE"] == "false"
    assert os.environ["STS2_BENCH_MEMORY_WINDOW"] == "8"
    assert os.environ["STS2_BENCH_MAX_STEPS"] == "300"
    assert os.environ["STS2_BENCH_OUT"] == "results/random_ironclad_a0.jsonl"
