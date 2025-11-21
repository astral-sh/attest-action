import subprocess
import uuid
from pathlib import Path

import pytest
import requests
from sigstore import oidc

import action


@pytest.fixture(scope="session")
def id_token() -> oidc.IdentityToken:
    resp = requests.get(
        "https://raw.githubusercontent.com/sigstore-conformance/extremely-dangerous-public-oidc-beacon/refs/heads/current-token/oidc-token.txt",
        params={"cachebuster": uuid.uuid4().hex},
    )
    resp.raise_for_status()
    id_token = resp.text.strip()
    return oidc.IdentityToken(id_token)


@pytest.fixture
def sampleproject(tmp_path: Path) -> Path:
    """
    Create a sample Python project with a distribution file.
    """

    project_dir = tmp_path / "sampleproject"
    project_dir.mkdir()

    pyproject = project_dir / "pyproject.toml"
    pyproject.write_text("""
name = "astral-sh-attest-action-test-sampleproject"
version = "0.1.0"
description = "Who's wants to know?"
requires-python = ">=3.10"
""")

    hello_py = project_dir / "hello.py"
    hello_py.write_text("""
def main():
    print("Hello, world!")
""")

    return project_dir


def test_get_input(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ATTEST_ACTION_INPUT_FOO", "expected")

    assert action._get_input("foo") == "expected"


def test_get_path_patterns(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ATTEST_ACTION_INPUT_PATHS", "dist/* another/** third/")

    patterns = action._get_path_patterns()
    assert patterns == {"dist/*", "another/**", "third/*"}

    # Deduplicates patterns / files.
    monkeypatch.setenv("ATTEST_ACTION_INPUT_PATHS", "dist/* dist/* another/")
    patterns = action._get_path_patterns()
    assert patterns == {"dist/*", "another/*"}

    monkeypatch.setenv("ATTEST_ACTION_INPUT_PATHS", "a a b b c")
    patterns = action._get_path_patterns()
    assert patterns == {"a", "b", "c"}


def test_attest(sampleproject: Path, id_token: oidc.IdentityToken) -> None:
    subprocess.run(["uv", "build"], cwd=sampleproject, check=True)
    dist_dir = sampleproject / "dist"

    patterns = {str(dist_dir / "*")}

    dists = action._collect_dists(patterns)
    assert len(dists) == 2  # sdist and wheel

    action._attest(
        dists,
        id_token,
        overwrite=False,
    )

    for dist_path, _ in dists:
        attestation_path = dist_path.with_name(f"{dist_path.name}.publish.attestation")
        assert attestation_path.exists()
