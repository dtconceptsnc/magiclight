"""Tests for MagicLight blueprint automation manager file reconciliation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import AsyncMock

import pytest
import yaml

import ha_blueprint_manager as hbm
from ha_blueprint_manager import (
    ALIAS_PREFIX,
    BlueprintAutomationManager,
    MANAGED_BLOCK_START,
)


MINIMAL_BLUEPRINT = """\
blueprint:
  name: MagicLight Hue Dimmer Switch
  description: Test blueprint
  domain: automation
  input:
    switch_device:
      selector:
        device:
          filter:
            - integration: zha
              manufacturer: Signify Netherlands B.V.
              model: RWL022
            - integration: hue
              manufacturer: Signify Netherlands B.V.
              model: RWL022
    target_areas:
      selector:
        area:
          multiple: true
mode: restart
"""


class DummyWSClient:
    """Minimal async client stub for blueprint reconciliation tests."""

    def __init__(
        self,
        *,
        areas: List[Dict[str, Any]],
        devices: List[Dict[str, Any]],
        entities: List[Dict[str, Any]],
        states: List[Dict[str, Any]],
    ) -> None:
        self._areas = areas
        self._devices = devices
        self._entities = entities
        self._states = states
        self.call_service = AsyncMock()

    async def get_states(self) -> List[Dict[str, Any]]:
        return self._states

    async def send_message_wait_response(self, message: Dict[str, Any]) -> Any:
        msg_type = message.get("type")
        if msg_type == "config/area_registry/list":
            return self._areas
        if msg_type == "config/device_registry/list":
            return self._devices
        if msg_type == "config/entity_registry/list":
            return self._entities
        raise AssertionError(f"Unexpected message type: {msg_type}")


def _prepare_blueprint_env(tmp_path: Path, monkeypatch, include_mode: str) -> Dict[str, Path]:
    """Create a temporary Home Assistant-style config layout for tests."""

    config_dir = tmp_path / "config"
    config_dir.mkdir()

    config_path = config_dir / "configuration.yaml"

    automations_file = config_dir / "automations.yaml"
    automations_dir = config_dir / "automations"

    source_base = tmp_path / "blueprint_source"
    automation_source = source_base / "automation" / "magiclight"
    automation_source.mkdir(parents=True)
    (automation_source / "hue_dimmer_switch.yaml").write_text(MINIMAL_BLUEPRINT, encoding="utf-8")

    script_source = source_base / "script" / "magiclight"
    script_source.mkdir(parents=True)
    (script_source / "dummy.yaml").write_text("{}\n", encoding="utf-8")

    config_blueprint_root = config_dir / "blueprints"
    config_blueprint_aut = config_blueprint_root / "automation"
    config_blueprint_scr = config_blueprint_root / "script"

    if include_mode == "file":
        include_line = f'automation: !include "{automations_file}"\n'
    elif include_mode == "dir":
        automations_dir.mkdir(parents=True, exist_ok=True)
        include_line = f'automation: !include_dir_merge_list "{automations_dir}"\n'
    else:
        include_line = include_mode

    config_path.write_text(include_line, encoding="utf-8")

    monkeypatch.setattr(hbm, "CONFIG_PATH", config_path)
    monkeypatch.setattr(hbm, "AUTOMATIONS_FILE", automations_file)
    monkeypatch.setattr(hbm, "AUTOMATIONS_DIR", automations_dir)
    monkeypatch.setattr(hbm, "CONFIG_BLUEPRINT_AUT_ROOT", config_blueprint_aut)
    monkeypatch.setattr(hbm, "CONFIG_BLUEPRINT_SCR_ROOT", config_blueprint_scr)
    monkeypatch.setattr(hbm, "BLUEPRINT_PATH_VARIANTS", (config_blueprint_aut,))
    monkeypatch.setenv("MAGICLIGHT_BLUEPRINT_SOURCE_BASE", str(source_base))

    return {
        "config_dir": config_dir,
        "automations_file": automations_file,
        "automations_dir": automations_dir,
        "blueprint_aut_dest": config_blueprint_aut / "magiclight",
        "blueprint_scr_dest": config_blueprint_scr / "magiclight",
        "blueprint_marker": (config_blueprint_aut / "magiclight") / hbm.BLUEPRINT_MARKER_FILENAME,
    }


def _build_fixtures(*, integration: str = "zha") -> Dict[str, List[Dict[str, Any]]]:
    area_id = "area-1"
    device_id = "device-1"

    areas = [{"area_id": area_id, "name": "Living Room"}]
    devices = [
        {
            "id": device_id,
            "manufacturer": "Signify Netherlands B.V.",
            "model": "RWL022",
            "area_id": area_id,
        }
    ]
    entities = [
        {
            "entity_id": "sensor.dummy_button",
            "device_id": device_id,
            "area_id": area_id,
            "platform": integration,
        }
    ]
    states = [
        {
            "entity_id": "light.magic_living_room",
            "attributes": {
                "area_id": area_id,
                "friendly_name": "Magic_Living Room",
            },
        }
    ]

    return {
        "areas": areas,
        "devices": devices,
        "entities": entities,
        "states": states,
    }


@pytest.mark.asyncio
async def test_reconcile_writes_block_to_automations_yaml(tmp_path, monkeypatch):
    helpers = _prepare_blueprint_env(tmp_path, monkeypatch, "file")

    payloads = _build_fixtures()
    ws_client = DummyWSClient(**payloads)

    manager = BlueprintAutomationManager(ws_client, enabled=True)
    await manager.reconcile_now("startup")

    automations_file = helpers["automations_file"]
    content = automations_file.read_text(encoding="utf-8")

    assert MANAGED_BLOCK_START in content

    blueprint_dest = helpers["blueprint_aut_dest"]
    assert (blueprint_dest / "hue_dimmer_switch.yaml").is_file()
    marker_path = helpers["blueprint_marker"]
    assert marker_path.is_file()
    marker_data = json.loads(marker_path.read_text(encoding="utf-8"))
    assert marker_data["automation_files"] == ["hue_dimmer_switch.yaml"]

    block = manager._extract_managed_block(content)
    parsed = yaml.safe_load(block)
    assert isinstance(parsed, list) and len(parsed) == 1

    entry = parsed[0]
    assert entry["id"] == "magiclight_area_1"
    assert entry["alias"] == f"{ALIAS_PREFIX}Living Room"
    assert entry["use_blueprint"]["path"] == "magiclight/hue_dimmer_switch.yaml"
    assert entry["use_blueprint"]["input"]["switch_device"] == ["device-1"]
    assert entry["use_blueprint"]["input"]["target_areas"] == ["area-1"]

    ws_client.call_service.assert_awaited_once_with("automation", "reload", {})

    previous = content
    ws_client.call_service.reset_mock()

    await manager.reconcile_now("startup-repeat")

    ws_client.call_service.assert_not_called()
    assert automations_file.read_text(encoding="utf-8") == previous


@pytest.mark.asyncio
async def test_hue_switch_automation_disabled_by_default(tmp_path, monkeypatch):
    helpers = _prepare_blueprint_env(tmp_path, monkeypatch, "file")

    payloads = _build_fixtures(integration="hue")
    ws_client = DummyWSClient(**payloads)

    manager = BlueprintAutomationManager(ws_client, enabled=True)
    await manager.reconcile_now("startup")

    automations_file = helpers["automations_file"]
    content = automations_file.read_text(encoding="utf-8")
    block = manager._extract_managed_block(content)
    parsed = yaml.safe_load(block)

    assert isinstance(parsed, list) and len(parsed) == 1
    entry = parsed[0]
    assert entry.get("initial_state") is False

    ws_client.call_service.assert_awaited_once_with("automation", "reload", {})


@pytest.mark.asyncio
async def test_reconcile_writes_include_dir_file(tmp_path, monkeypatch):
    helpers = _prepare_blueprint_env(tmp_path, monkeypatch, "dir")

    payloads = _build_fixtures()
    ws_client = DummyWSClient(**payloads)

    manager = BlueprintAutomationManager(ws_client, enabled=True)
    await manager.reconcile_now("startup")

    managed_path = helpers["automations_dir"] / "magiclight_managed.yaml"
    assert managed_path.is_file()

    blueprint_dest = helpers["blueprint_aut_dest"]
    assert (blueprint_dest / "hue_dimmer_switch.yaml").is_file()

    data = yaml.safe_load(managed_path.read_text(encoding="utf-8"))
    assert isinstance(data, list) and len(data) == 1

    entry = data[0]
    assert entry["id"] == "magiclight_area_1"
    assert entry["alias"] == f"{ALIAS_PREFIX}Living Room"

    ws_client.call_service.assert_awaited_once_with("automation", "reload", {})


@pytest.mark.asyncio
async def test_purge_managed_automations_removes_block(tmp_path, monkeypatch):
    helpers = _prepare_blueprint_env(tmp_path, monkeypatch, "file")

    payloads = _build_fixtures()
    ws_client = DummyWSClient(**payloads)

    manager = BlueprintAutomationManager(ws_client, enabled=False)

    existing = [
        {
            "id": "magiclight_area_1",
            "alias": f"{ALIAS_PREFIX}Living Room",
            "description": "Managed automatically by the MagicLight add-on.",
            "use_blueprint": {
                "path": "magiclight/hue_dimmer_switch.yaml",
                "input": {
                    "switch_device": ["device-1"],
                    "target_areas": ["area-1"],
                },
            },
        }
    ]

    automations_file = helpers["automations_file"]
    automations_file.write_text(
        manager._render_managed_block(existing),
        encoding="utf-8",
    )

    await manager.purge_managed_automations("test-disabled")

    contents = automations_file.read_text(encoding="utf-8")
    assert MANAGED_BLOCK_START not in contents
    assert contents.strip() == ""
    ws_client.call_service.assert_awaited_once_with("automation", "reload", {})

    ws_client.call_service.reset_mock()
    await manager.purge_managed_automations("test-disabled-repeat")
    ws_client.call_service.assert_not_called()


@pytest.mark.asyncio
async def test_purge_managed_automations_removes_include_dir_file(tmp_path, monkeypatch):
    helpers = _prepare_blueprint_env(tmp_path, monkeypatch, "dir")

    payloads = _build_fixtures()
    ws_client = DummyWSClient(**payloads)

    manager = BlueprintAutomationManager(ws_client, enabled=False)

    existing = [
        {
            "id": "magiclight_area_1",
            "alias": f"{ALIAS_PREFIX}Living Room",
            "description": "Managed automatically by the MagicLight add-on.",
            "use_blueprint": {
                "path": "magiclight/hue_dimmer_switch.yaml",
                "input": {
                    "switch_device": ["device-1"],
                    "target_areas": ["area-1"],
                },
            },
        }
    ]

    managed_path = helpers["automations_dir"] / "magiclight_managed.yaml"
    managed_path.write_text(
        yaml.safe_dump(existing, sort_keys=False),
        encoding="utf-8",
    )

    await manager.purge_managed_automations("test-disabled-dir")

    assert not managed_path.exists()
    ws_client.call_service.assert_awaited_once_with("automation", "reload", {})


@pytest.mark.asyncio
async def test_remove_blueprint_files_cleans_destinations(tmp_path, monkeypatch):
    helpers = _prepare_blueprint_env(tmp_path, monkeypatch, "file")
    payloads = _build_fixtures()
    ws_client = DummyWSClient(**payloads)

    manager = BlueprintAutomationManager(ws_client, enabled=True)
    await manager.reconcile_now("initial")

    aut_dest = helpers["blueprint_aut_dest"]
    scr_dest = helpers["blueprint_scr_dest"]
    marker = helpers["blueprint_marker"]

    assert aut_dest.exists()
    assert marker.exists()

    await manager.remove_blueprint_files("disabled")

    assert not aut_dest.exists()
    assert not scr_dest.exists()
    assert not marker.exists()


def test_should_refresh_marker_with_matching_checksums():
    manager = BlueprintAutomationManager(AsyncMock(), enabled=True)
    marker = {
        "source": "bundle-path",
        "automation_files": ["hue_dimmer_switch.yaml"],
        "script_files": ["dummy.yaml"],
        "automation_checksums": {"hue_dimmer_switch.yaml": "abc123"},
        "script_checksums": {"dummy.yaml": "def456"},
    }

    should_refresh = manager._should_refresh_marker(
        marker,
        "bundle-path",
        ["hue_dimmer_switch.yaml"],
        ["dummy.yaml"],
        {"hue_dimmer_switch.yaml": "abc123"},
        {"dummy.yaml": "def456"},
    )

    assert should_refresh is False


@pytest.mark.parametrize(
    "marker_overrides,expected",
    [
        ({"automation_checksums": {"hue_dimmer_switch.yaml": "different"}}, True),
        ({"script_checksums": {"dummy.yaml": "different"}}, True),
        ({"automation_checksums": None}, True),
        ({"drop_checksums": True}, True),  # legacy marker without checksum keys
    ],
)
def test_should_refresh_marker_detects_checksum_changes(marker_overrides, expected):
    manager = BlueprintAutomationManager(AsyncMock(), enabled=True)
    base_marker = {
        "source": "bundle-path",
        "automation_files": ["hue_dimmer_switch.yaml"],
        "script_files": ["dummy.yaml"],
        "automation_checksums": {"hue_dimmer_switch.yaml": "abc123"},
        "script_checksums": {"dummy.yaml": "def456"},
    }
    marker = dict(base_marker)

    if marker_overrides.get("drop_checksums"):
        marker.pop("automation_checksums", None)
        marker.pop("script_checksums", None)
    else:
        marker.update(
            {
                key: value
                for key, value in marker_overrides.items()
                if key != "drop_checksums"
            }
        )

    should_refresh = manager._should_refresh_marker(
        marker,
        "bundle-path",
        ["hue_dimmer_switch.yaml"],
        ["dummy.yaml"],
        {"hue_dimmer_switch.yaml": "abc123"},
        {"dummy.yaml": "def456"},
    )

    assert should_refresh is expected
