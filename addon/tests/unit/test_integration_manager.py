"""Tests for shell-based MagicLight integration management helpers."""

from __future__ import annotations

import os
import subprocess
import textwrap
from pathlib import Path

import pytest


RUN_SCRIPT = Path(__file__).resolve().parents[2] / "rootfs" / "etc" / "services.d" / "example" / "run"


def _run_shell_script(script: str, *, env: dict[str, str], cwd: Path) -> subprocess.CompletedProcess:
    runner = cwd / "runner.sh"
    runner.write_text(script, encoding="utf-8")
    runner.chmod(0o755)
    return subprocess.run(["bash", str(runner)], check=True, capture_output=True, text=True, env=env)


def _make_stubbed_script(*, bundle_path: Path, dest_base: Path, repo_info: Path, marker_path: Path, extra_body: str) -> str:
    dest_dir = marker_path.parent
    return textwrap.dedent(
        f"""
        #!/usr/bin/env bash
        set -euo pipefail

        export MAGICLIGHT_SKIP_MAIN=1

        bashio::config() {{
            case "$1" in
                'manage_integration') echo "${{MAGICLIGHT_TEST_CFG_MANAGE_INTEGRATION:-true}}" ;;
                'manage_blueprints') echo "${{MAGICLIGHT_TEST_CFG_MANAGE_BLUEPRINTS:-true}}" ;;
                'integration_download_url') echo "${{MAGICLIGHT_TEST_CFG_DOWNLOAD_URL:-}}" ;;
                *) echo "" ;;
            esac
        }}

        bashio::log.info() {{ printf 'INFO: %s\n' "$*"; }}
        bashio::log.debug() {{ printf 'DEBUG: %s\n' "$*"; }}
        bashio::log.warning() {{ printf 'WARN: %s\n' "$*"; }}
        bashio::log.error() {{ printf 'ERROR: %s\n' "$*" >&2; }}

        bashio::addon.version() {{ echo "${{MAGICLIGHT_TEST_ADDON_VERSION:-0.0.0}}"; }}
        bashio::fs.directory_exists() {{ [[ -d "$1" ]]; }}

        source "{RUN_SCRIPT}"

        MAGICLIGHT_SOURCE="{bundle_path}"
        MAGICLIGHT_DEST_BASE="{dest_base}"
        MAGICLIGHT_DEST="{dest_dir}"
        MAGICLIGHT_MARKER="{marker_path}"
        MAGICLIGHT_REPOSITORY_INFO="{repo_info}"
        MAGICLIGHT_BUNDLED_BLUEPRINT_BASE="{bundle_path.parent.parent}"  # keep lookups in temp tree

        SUPERVISOR_TOKEN=""
        MAGICLIGHT_FALLBACK_BASE=""

        {extra_body}
        """
    )


def _create_repo_info(path: Path) -> None:
    path.write_text("url: 'https://github.com/dtconceptsnc/magiclight'\n", encoding="utf-8")


@pytest.mark.parametrize("manage_blueprints", ["true", "false"])
def test_manage_integration_installs_bundled_copy(tmp_path: Path, manage_blueprints: str) -> None:
    bundle = tmp_path / "bundle" / "custom_components" / "magiclight"
    bundle.mkdir(parents=True)
    (bundle / "manifest.json").write_text('{"name": "MagicLight", "version": "1.2.3"}', encoding="utf-8")

    repo_info = tmp_path / "repository.yaml"
    _create_repo_info(repo_info)

    dest_base = tmp_path / "config" / "custom_components"
    marker = dest_base / "magiclight" / ".managed_by_magiclight_addon"

    env = os.environ.copy()
    env.update(
        {
            "MAGICLIGHT_TEST_CFG_MANAGE_INTEGRATION": "true",
            "MAGICLIGHT_TEST_CFG_MANAGE_BLUEPRINTS": manage_blueprints,
            "MAGICLIGHT_TEST_CFG_DOWNLOAD_URL": "",
            "MAGICLIGHT_TEST_ADDON_VERSION": "9.9.9",
            "PATH": os.environ["PATH"],
        }
    )

    script = _make_stubbed_script(
        bundle_path=bundle,
        dest_base=dest_base,
        repo_info=repo_info,
        marker_path=marker,
        extra_body="prepare_destination\nmanage_magiclight_integration\n",
    )

    result = _run_shell_script(script, env=env, cwd=tmp_path)
    assert result.returncode == 0

    installed_manifest = dest_base / "magiclight" / "manifest.json"
    assert installed_manifest.is_file()

    marker_content = marker.read_text(encoding="utf-8")
    assert "addon_version=9.9.9" in marker_content
    assert "integration_version=1.2.3" in marker_content
    assert "source=bundled" in marker_content


def test_manage_integration_removes_managed_copy_when_disabled(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle" / "custom_components" / "magiclight"
    bundle.mkdir(parents=True)
    (bundle / "manifest.json").write_text('{"name": "MagicLight", "version": "0.1.0"}', encoding="utf-8")

    repo_info = tmp_path / "repository.yaml"
    _create_repo_info(repo_info)

    dest_base = tmp_path / "config" / "custom_components"
    dest_dir = dest_base / "magiclight"
    dest_dir.mkdir(parents=True)
    (dest_dir / "manifest.json").write_text("{}", encoding="utf-8")
    marker = dest_dir / ".managed_by_magiclight_addon"
    marker.write_text("source=bundled\naddon_version=1.0\nintegration_version=0.0.1\n", encoding="utf-8")

    env = os.environ.copy()
    env.update(
        {
            "MAGICLIGHT_TEST_CFG_MANAGE_INTEGRATION": "false",
            "MAGICLIGHT_TEST_CFG_MANAGE_BLUEPRINTS": "false",
            "MAGICLIGHT_TEST_CFG_DOWNLOAD_URL": "",
            "MAGICLIGHT_TEST_ADDON_VERSION": "9.9.9",
            "PATH": os.environ["PATH"],
        }
    )

    script = _make_stubbed_script(
        bundle_path=bundle,
        dest_base=dest_base,
        repo_info=repo_info,
        marker_path=marker,
        extra_body="manage_magiclight_integration\n",
    )

    result = _run_shell_script(script, env=env, cwd=tmp_path)
    assert result.returncode == 0
    assert not dest_dir.exists()
