"""Regression tests for repo-local toolchain discovery."""

from conftest import LOCAL_DOTNET_DIR, STS2_CLI_ROOT


def test_pytest_fixture_uses_sts2_cli_local_tools():
    assert LOCAL_DOTNET_DIR == STS2_CLI_ROOT / ".tools" / "dotnet"
