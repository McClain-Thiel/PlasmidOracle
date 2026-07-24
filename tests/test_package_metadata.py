from importlib.metadata import metadata, version

import plasmid_oracle as po


def test_runtime_version_matches_distribution_metadata() -> None:
    assert po.__version__ == version("plasmid-oracle")


def test_distribution_metadata_has_release_essentials() -> None:
    distribution = metadata("plasmid-oracle")

    assert distribution["License-Expression"] == "GPL-3.0-only"
    assert distribution["Requires-Python"] == ">=3.11"
    assert "Homepage, https://github.com/McClain-Thiel/PlasmidOracle" in distribution.get_all(
        "Project-URL"
    )
