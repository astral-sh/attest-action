import logging
import subprocess
from pathlib import Path
from time import time
from unittest.mock import MagicMock, Mock, call

import jwt
import pytest
import requests
from inline_snapshot import snapshot
from pypi_attestations import Attestation, Distribution, GooglePublisher
from sigstore import oidc

import action

logger = logging.getLogger(__name__)


@pytest.fixture(autouse=True)
def capture_summary(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """
    Capture the GitHub Actions job summary to a temporary file.
    """

    summary_path = tmp_path / "GITHUB_STEP_SUMMARY"
    summary_path.touch()
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary_path))

    return summary_path


@pytest.fixture(scope="session")
def id_token() -> oidc.IdentityToken:
    url = "https://storage.googleapis.com/sigstore-conformance-testing-token/untrusted-testing-token.txt"
    resp = requests.get(url)
    resp.raise_for_status()

    return oidc.IdentityToken(resp.text.strip())


@pytest.fixture
def mock_ambient_token(
    monkeypatch: pytest.MonkeyPatch, id_token: oidc.IdentityToken
) -> None:
    monkeypatch.setattr(oidc, "detect_credential", lambda: str(id_token))


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


def test_unroll_files_recursive(tmp_path: Path) -> None:
    root = tmp_path / "dists"
    root.mkdir()
    (root / "top.tar.gz").touch()
    sub = root / "nested"
    sub.mkdir()
    (sub / "deep.whl").touch()

    # ** should match files at all depths.
    files = action._unroll_files({str(root / "**")})
    assert files == {root / "top.tar.gz", sub / "deep.whl"}

    # * should only match files at the top level.
    files = action._unroll_files({str(root / "*")})
    assert files == {root / "top.tar.gz"}


@pytest.mark.usefixtures("mock_ambient_token")
def test_attest(sampleproject: Path) -> None:
    subprocess.run(["uv", "build"], cwd=sampleproject, check=True)
    dist_dir = sampleproject / "dist"

    patterns = {str(dist_dir / "*")}

    dists = action._collect_dists(patterns)
    assert len(dists) == 2  # sdist and wheel

    action._attest(dists, overwrite=False)

    for dist_path, _ in dists:
        attestation_path = dist_path.with_name(f"{dist_path.name}.publish.attestation")
        assert attestation_path.exists()


@pytest.mark.usefixtures("mock_ambient_token")
def test_attest_overwrite_fails(sampleproject: Path) -> None:
    subprocess.run(["uv", "build"], cwd=sampleproject, check=True)
    dist_dir = sampleproject / "dist"

    patterns = {str(dist_dir / "*")}

    dists = action._collect_dists(patterns)
    assert len(dists) == 2  # sdist and wheel

    action._attest(dists, overwrite=False)

    with pytest.raises(SystemExit):
        action._attest(dists, overwrite=False)


@pytest.mark.usefixtures("mock_ambient_token")
def test_attest_overwrite_succeeds(sampleproject: Path) -> None:
    subprocess.run(["uv", "build"], cwd=sampleproject, check=True)
    dist_dir = sampleproject / "dist"

    patterns = {str(dist_dir / "*")}

    dists = action._collect_dists(patterns)
    assert len(dists) == 2  # sdist and wheel

    action._attest(dists, overwrite=False)

    # This should succeed without error.
    action._attest(dists, overwrite=True)


@pytest.mark.usefixtures("mock_ambient_token")
def test_attest_verify(sampleproject: Path) -> None:
    subprocess.run(["uv", "build"], cwd=sampleproject, check=True)
    dist_dir = sampleproject / "dist"

    patterns = {str(dist_dir / "*")}

    dists = action._collect_dists(patterns)
    assert len(dists) == 2  # sdist and wheel

    action._attest(dists, overwrite=False)

    for dist_path, dist in dists:
        attestation_path = dist_path.with_name(f"{dist_path.name}.publish.attestation")
        assert attestation_path.exists()

        attestation = Attestation.model_validate_json(attestation_path.read_bytes())
        identity = GooglePublisher(
            email="untrusted-sa@sigstore-conformance.iam.gserviceaccount.com"
        )

        attestation.verify(
            identity=identity,
            dist=dist,
            offline=True,
        )


def test_attest_no_dists(
    capture_summary: Path,
) -> None:
    with pytest.raises(SystemExit):
        action._attest([], overwrite=False)

    assert capture_summary.read_text() == snapshot("""\
### ❌ Fatal: No distributions to attest

No valid Python distributions were collected from the specified paths.

> [!TIP]
> Ensure that the `paths` input points to valid distribution files.
""")


def test_attest_refreshes_signer(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    now = int(time())
    expires_at = now + 300
    raw_tokens = [
        jwt.encode(
            {
                "aud": "sigstore",
                "sub": "test",
                "iss": "https://issuer.example",
                "iat": now,
                "exp": exp,
            },
            key="",
            algorithm="none",
        )
        for exp in (expires_at, expires_at + 300)
    ]
    monkeypatch.setattr(oidc, "detect_credential", Mock(side_effect=raw_tokens))
    monkeypatch.setattr(
        action, "time", Mock(side_effect=[expires_at - 61, expires_at - 60])
    )

    context = Mock(spec=action.SigningContext)
    initial_context, refreshed_context = MagicMock(), MagicMock()
    initial_signer = initial_context.__enter__.return_value
    refreshed_signer = refreshed_context.__enter__.return_value
    context.signer.side_effect = [initial_context, refreshed_context]
    monkeypatch.setattr(action.ClientTrustConfig, "production", Mock())
    monkeypatch.setattr(action.SigningContext, "from_trust_config", lambda _: context)

    attestation = Mock(spec=Attestation)
    attestation.model_dump_json.return_value = "{}"
    sign = Mock(return_value=attestation)
    monkeypatch.setattr(Attestation, "sign", sign)

    dists = []
    for version in range(3):
        path = tmp_path / f"sample-{version}.0.0.tar.gz"
        dists.append((path, Distribution(name=path.name, digest="0" * 64)))

    assert action._attest(dists) == [(dist, attestation) for _, dist in dists]
    assert [
        str(c.kwargs["identity_token"]) for c in context.signer.call_args_list
    ] == raw_tokens
    assert sign.call_args_list == [
        call(initial_signer, dists[0][1]),
        call(initial_signer, dists[1][1]),
        call(refreshed_signer, dists[2][1]),
    ]
    for path, _ in dists:
        assert Path(f"{path}.publish.attestation").read_text() == "{}"
