"""Regression tests for Godot presentation stubs."""

from pathlib import Path


def test_gpu_particles_2d_exposes_amount_property():
    source = Path(__file__).resolve().parents[1] / "src" / "GodotStubs" / "UI.cs"
    text = source.read_text(encoding="utf-8")

    assert "public int Amount { get; set; }" in text
