# attest-action

[![Actions status](https://github.com/astral-sh/pyx-auth-action/actions/workflows/test.yml/badge.svg)](https://github.com/astral-sh/pyx-auth-action/actions)
[![Discord](https://img.shields.io/badge/Discord-%235865F2.svg?logo=discord&logoColor=white)](https://discord.gg/astral-sh)

A GitHub Action that generates [PEP 740] publish attestations for your Python
packages.

[PEP 740]: https://peps.python.org/pep-0740/

To use this action, you should be using [Trusted Publishing] to publish your
packages (to [pyx], [PyPI], or another compatible index).

[Trusted Publishing]: https://docs.pypi.org/trusted-publishers/

[pyx]: https://pyx.dev

[PyPI]: https://pypi.org

> [!IMPORTANT]
> This action is primarily useful for directly publishing with [`uv publish`]
> and other upload tools that support PEP 740 attestations directly.
> You **do not need** this action if you're using [pypa/gh-action-pypi-publish],
> as that action has built-in support for PEP 740 attestations.

[`uv publish`]: https://docs.astral.sh/uv/guides/package/

[pypa/gh-action-pypi-publish]: https://github.com/pypa/gh-action-pypi-publish

## Contents

- [Usage](#usage)
  - [Prerequisites](#prerequisites)
  - [Quickstart](#quickstart)
- [Inputs](#inputs)
    - [`paths`](#paths)
    - [`overwrite`](#overwrite)
- [Outputs](#outputs)

## Usage

### Prerequisites

To use this action, you must have a Trusted Publisher configured for your
project on your target index (or indices). Refer to your index's documentation
for more information on Trusted Publishing:

- [pyx - Trusted Publishing](https://docs.pyx.dev/publishing#trusted-publishing)
- [PyPI - Trusted Publishing](https://docs.pypi.org/trusted-publishers/)

As with Trusted Publishing itself, this action requires the `id-token: write`
permission on your publishing job. For example:

```yaml
permissions:
  id-token: write # for Trusted Publishing + attest-action
  contents: read # for actions/checkout, if you're in a private repo
```

In order to upload the resulting attestations to an index, you must use
a publishing tool that supports PEP 740 attestations. Such tools include:

* uv (`uv publish`) versions 0.9.12 and later
* twine (`twine upload`) versions 5.1.0 and later

> [!TIP]
> We recommend using `uv publish` with this action, as it does not require
> any additional installation or configuration.

### Quickstart

Add `astral-sh/attest-action` directly above your publishing step in your
publishing job.

For example:

```yaml
jobs:
  publish:
    runs-on: ubuntu-latest
    permissions:
      id-token: write
      contents: read

    needs: [build]
    steps:
      - uses: actions/checkout@1af3b93b6815bc44a9784bd300feb67ff0d1eeb3 # v6.0.0

      - uses: actions/download-artifact@018cc2cf5baa6db3ef3c5f8a56943fffe632ef53 # v6.0.0
        with:
          name: dist

      - uses: astral-sh/attest-action@c6ac02fbfa88e5521aca175a15fc2482b70e360c # v0.0.1

      - run: uv publish
```

> [!IMPORTANT]
> Performing builds in a separate job is **strongly encouraged** as a way
> to improve both security and reproducibility.

If you have a custom path (or paths) to your distributions, you can specify them
via the `paths` input as whitespace-separated values.

```yaml
- uses: astral-sh/attest-action@c6ac02fbfa88e5521aca175a15fc2482b70e360c # v0.0.1
  with:
  paths: |
    custom-dist-dir/*
    wheelhouse/*
```

## Inputs

### `paths`

**Default:** `dist/*`

One or more whitespace-separated directories or glob patterns to search for
Python distributions to generate attestations for.

Recursive globs may be used, e.g. `dist/**` to find all distributions within
`dist/` and its subdirectories.

> [!NOTE]
> A bare directory path like `dist/` is treated as `dist/*`.

### `overwrite`

**Default:** `false`

If `false` (the default), any existing publish attestations that *would* have
been overwritten will instead cause the action to fail.

If `true`, existing attestations will be overwritten.

## Outputs

This action currently has no outputs.

## Licence

pyx-auth-action is licensed under either of

- Apache License, Version 2.0, ([LICENSE-APACHE](LICENSE-APACHE) or <https://www.apache.org/licenses/LICENSE-2.0>)
- MIT license ([LICENSE-MIT](LICENSE-MIT) or <https://opensource.org/licenses/MIT>)

at your option.

Unless you explicitly state otherwise, any contribution intentionally submitted
for inclusion in pyx-auth-action by you, as defined in the Apache-2.0 license, shall be
dually licensed as above, without any additional terms or conditions.

<div align="center">
  <a target="_blank" href="https://astral.sh" style="background:none">
    <img src="https://raw.githubusercontent.com/astral-sh/ruff/main/assets/svg/Astral.svg">
  </a>
</div>
