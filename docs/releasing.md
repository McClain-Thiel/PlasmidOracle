# Releasing Plasmid Oracle

PyPI publication uses GitHub Actions and PyPI Trusted Publishing. No PyPI API
token is stored in GitHub.

## One-Time Configuration

1. Create a GitHub environment named `pypi`.
2. Add a pending publisher at <https://pypi.org/manage/account/publishing/>:
   - PyPI project name: `plasmid-oracle`
   - GitHub owner: `McClain-Thiel`
   - GitHub repository: `PlasmidOracle`
   - Workflow: `publish.yml`
   - Environment: `pypi`

The pending publisher creates the PyPI project during the first trusted
publication. After that succeeds, confirm the publisher under the project's
PyPI settings.

## Release Process

1. Set the same PEP 440 version in `pyproject.toml` and
   `src/plasmid_oracle/__init__.py`.
2. Run the local release checks:

   ```bash
   uv sync --locked --dev
   uv run pytest --cov=plasmid_oracle --cov-report=term-missing
   uv run ruff check .
   uv run ruff format --check .
   uv run mypy
   uv run --group docs mkdocs build --strict
   uv build --no-sources
   uvx --from twine twine check dist/*
   ```

3. Merge and push the release commit to `main`, then wait for CI.
4. Create a GitHub release whose tag is exactly `v<version>`. Mark alpha, beta,
   and release-candidate versions as prereleases.

The `Publish to PyPI` workflow checks that the tag matches the package version,
builds the wheel and source distribution once, validates both artifacts, and
publishes them from the protected `pypi` environment using OpenID Connect.
PyPI versions are immutable; publish a new version rather than replacing an
existing artifact.
