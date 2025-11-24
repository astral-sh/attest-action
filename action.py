# /// script
# requires-python = ">=3.14"
# ///

import base64
import logging
import os
import shlex
from glob import glob
from pathlib import Path

from pypi_attestations import Attestation, Distribution
from sigstore import oidc
from sigstore.models import ClientTrustConfig
from sigstore.sign import SigningContext

logger = logging.getLogger(__name__)


def _get_input(name: str) -> str | None:
    """
    Get an action input from the environment, or `None` if not set.
    """
    env = f"ATTEST_ACTION_INPUT_{name.upper().replace('-', '_')}"
    return os.getenv(env)


def _get_path_patterns() -> set[str]:
    """
    Retrieve and normalize the 'paths' input.

    Paths are split on whitespace (with shell lexing rules), and any bare directory
    paths are normalized to include all files within that directory (i.e. `foo/`
    becomes `foo/*`).
    """
    raw_paths = _get_input("paths")
    if not raw_paths:
        raise RuntimeError("Internal error: no 'paths' input provided")

    paths = shlex.split(raw_paths)
    if not paths:
        raise RuntimeError("No paths provided in 'paths' input")

    # Normalize `foo/` to `foo/*`
    paths = [str(Path(p) / "*") if p.endswith(("/", "\\")) else p for p in paths]

    return set(paths)


def _unroll_files(patterns: set[str]) -> set[Path]:
    """
    Given one or more path patterns (which may include glob patterns), unroll and
    return all matching files.
    """

    files = set()

    for pattern in patterns:
        for path in glob(pattern):
            path = Path(path)
            if path.is_file():
                files.add(path)

    return files


def _collect_dists(patterns: set[str]) -> list[tuple[Path, Distribution]]:
    """
    Given one or more path patterns (which may include glob patterns), collect and
    return all Python distributions found at those paths.

    A bare directory path like `foo/` is treated as `foo/*`, i.e.
    all distributions within that directory.

    Distributions are returned as a list of tuples, where each tuple contains
    the `Path` to the distribution file and the corresponding `Distribution`
    object.
    """

    files = _unroll_files(patterns)
    dists = []

    for file in files:
        try:
            dist = Distribution.from_file(file)
            dists.append((file, dist))

        except Exception as _:
            logger.debug(f"skipping non-distribution file: {file}")
            continue

    return dists


def _get_id_token() -> oidc.IdentityToken:
    """
    Obtain the ambient OIDC identity token.
    """
    id_token = oidc.detect_credential()

    if not id_token:
        raise RuntimeError("Failed to obtain OIDC identity token")

    return oidc.IdentityToken(raw_token=id_token)


def _attest(
    dists: list[tuple[Path, Distribution]],
    id_token: oidc.IdentityToken,
    overwrite: bool = False,
) -> None:
    """
    Generate and write PEP 740 publish attestations for the given distributions.

    If `overwrite` is `False`, existing attestation files will not be overwritten
    and an error will be raised instead.
    """

    # Before setting up any signing state, precompute the paths we intend
    # to write attestations to (and fail if any already exist and overwrite
    # is disabled).
    dists_with_dests: list[tuple[Path, Distribution, Path]] = []
    for file, dist in dists:
        parent = file.parent
        filename = file.name
        attestation_name = f"{filename}.publish.attestation"
        attestation_path = parent / attestation_name

        if attestation_path.exists() and not overwrite:
            raise RuntimeError(f"Attestation file already exists: {attestation_path}")

        dists_with_dests.append((file, dist, attestation_path))

    trust = ClientTrustConfig.production()
    context = SigningContext.from_trust_config(trust)

    with context.signer(identity_token=id_token) as signer:
        for _, dist, attestation_path in dists_with_dests:
            attestation = Attestation.sign(signer, dist)
            attestation_path.write_text(attestation.model_dump_json())


def main() -> None:
    path_patterns = _get_path_patterns()

    dists = _collect_dists(path_patterns)

    if id_token := _get_input("id-token"):
        id_token = base64.b64decode(id_token).decode("utf-8")
        id_token = oidc.IdentityToken(raw_token=id_token)
    else:
        id_token = _get_id_token()

    overwrite = _get_input("overwrite") == "true"

    _attest(dists, id_token, overwrite=overwrite)


if __name__ == "__main__":
    main()
