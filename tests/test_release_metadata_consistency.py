from __future__ import annotations

import re
import tomllib
from pathlib import Path

import yaml

import seismicshield_rl


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_REPOSITORY = "https://github.com/FaramarzKowsari/seismicshield-rl"
EXPECTED_LICENSE = "MIT"
EXPECTED_CONCEPT_DOI = "10.5281/zenodo.22067277"
EXPECTED_FROZEN_DOI = "10.5281/zenodo.22067278"
EXPECTED_OSF_DOI = "10.17605/OSF.IO/64DTX"


def _project_metadata() -> dict:
    with (ROOT / "pyproject.toml").open("rb") as handle:
        return tomllib.load(handle)["project"]


def _citation_metadata() -> dict:
    return yaml.safe_load((ROOT / "CITATION.cff").read_text(encoding="utf-8"))


def test_active_version_metadata_is_consistent():
    project = _project_metadata()
    citation = _citation_metadata()
    manifest = (ROOT / "PROJECT_MANIFEST.md").read_text(encoding="utf-8")

    project_version = str(project["version"])
    citation_version = str(citation["version"])
    runtime_version = str(seismicshield_rl.__version__)

    manifest_match = re.search(
        r"\*\*Current publication-package version:\*\*\s*([0-9]+\.[0-9]+\.[0-9]+)",
        manifest,
    )
    assert manifest_match is not None
    manifest_version = manifest_match.group(1)

    assert project_version == runtime_version == citation_version == manifest_version


def test_active_identity_metadata_is_consistent():
    project = _project_metadata()
    citation = _citation_metadata()
    urls = project["urls"]

    assert project["name"] == "seismicshield-rl"
    assert project["license"]["text"] == EXPECTED_LICENSE
    assert citation["license"] == EXPECTED_LICENSE
    assert citation["repository-code"] == EXPECTED_REPOSITORY
    assert urls["Repository"] == EXPECTED_REPOSITORY

    assert EXPECTED_CONCEPT_DOI in citation["message"]
    assert EXPECTED_FROZEN_DOI in citation["message"]
    assert EXPECTED_OSF_DOI in citation["message"]
    assert EXPECTED_FROZEN_DOI in urls["Archived scientific release"]
    assert EXPECTED_CONCEPT_DOI in urls["Software concept DOI"]
    assert EXPECTED_OSF_DOI in urls["OSF preregistration"]


def test_legacy_package_versions_do_not_reappear_in_active_metadata():
    active_files = [
        ROOT / "pyproject.toml",
        ROOT / "src" / "seismicshield_rl" / "__init__.py",
        ROOT / "CITATION.cff",
        ROOT / "PROJECT_MANIFEST.md",
    ]

    combined = "\n".join(path.read_text(encoding="utf-8") for path in active_files)
    assert 'version = "0.1.1"' not in combined
    assert "**Version:** 0.1.0" not in combined
