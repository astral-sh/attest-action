import logging
import subprocess
import time
from pathlib import Path

import pytest
import requests
from pypi_attestations import Attestation, GitHubPublisher
from sigstore import oidc

import action

logger = logging.getLogger(__name__)


@pytest.fixture(autouse=True)
def suppress_summary_writing(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Prevent writing to the GitHub Actions job summary during tests.
    """
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)


@pytest.fixture(scope="session")
def id_token() -> oidc.IdentityToken:
    def _id_token() -> oidc.IdentityToken | None:
        # GitHub loves to cache things it has no business caching.
        result = subprocess.run(
            [
                "git",
                "ls-remote",
                "https://github.com/sigstore-conformance/extremely-dangerous-public-oidc-beacon",
                "refs/heads/current-token",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        ref = result.stdout.split()[0]

        resp = requests.get(
            f"https://raw.githubusercontent.com/sigstore-conformance/extremely-dangerous-public-oidc-beacon/{ref}/oidc-token.txt",
        )
        resp.raise_for_status()
        id_token = resp.text.strip()
        try:
            return oidc.IdentityToken(id_token)
        except Exception:
            return None

    # Try up to 10 times to get a valid token, waiting 3 seconds between attempts.
    for n in range(10):
        token = _id_token()
        if token is not None:
            return token
        else:
            logger.warning(f"Waiting for valid OIDC identity token, try {n}...")
        time.sleep(3)

    raise RuntimeError("Failed to obtain OIDC identity token for tests")


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


def test_attest_overwrite_fails(
    sampleproject: Path,
    id_token: oidc.IdentityToken,
) -> None:
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

    with pytest.raises(SystemExit):
        action._attest(
            dists,
            id_token,
            overwrite=False,
        )


def test_attest_overwrite_succeeds(
    sampleproject: Path,
    id_token: oidc.IdentityToken,
) -> None:
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

    # This should succeed without error.
    action._attest(
        dists,
        id_token,
        overwrite=True,
    )


def test_attest_verify(
    sampleproject: Path,
    id_token: oidc.IdentityToken,
) -> None:
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

    for dist_path, dist in dists:
        attestation_path = dist_path.with_name(f"{dist_path.name}.publish.attestation")
        assert attestation_path.exists()

        attestation = Attestation.model_validate_json(attestation_path.read_bytes())
        identity = GitHubPublisher(
            repository="sigstore-conformance/extremely-dangerous-public-oidc-beacon",
            workflow="extremely-dangerous-oidc-beacon.yml",
        )

        attestation.verify(
            identity=identity,
            dist=dist,
            offline=True,
        )
