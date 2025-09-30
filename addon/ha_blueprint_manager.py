"""Home Assistant blueprint automation manager for MagicLight."""

from __future__ import annotations

import asyncio
import logging
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

import yaml
from yaml.constructor import ConstructorError

class BlueprintLoader(yaml.SafeLoader):
    """SafeLoader that tolerates Home Assistant-specific YAML tags."""


def _blueprint_tag_constructor(loader, tag_suffix, node):
    """Handle custom tags like !input by returning plain data."""
    if isinstance(node, yaml.ScalarNode):
        return loader.construct_scalar(node)
    if isinstance(node, yaml.SequenceNode):
        return loader.construct_sequence(node)
    if isinstance(node, yaml.MappingNode):
        return loader.construct_mapping(node)
    return None


BlueprintLoader.add_multi_constructor('!', _blueprint_tag_constructor)

ALIAS_PREFIX = "MagicLight Hue Dimmer – "
BLUEPRINT_DESCRIPTION = "Managed automatically by the MagicLight add-on."
BLUEPRINT_PATH_VARIANTS = (
    Path("/config/blueprints/automation"),
    Path("/config/blueprints/automations"),
)
LOCAL_BLUEPRINT_VARIANTS = (
    Path(__file__).resolve().parent.parent / "blueprints" / "automation",
    Path(__file__).resolve().parent.parent / "blueprints" / "automations",
)

AUTOMATIONS_FILE = Path("/config/automations.yaml")
AUTOMATIONS_DIR = Path("/config/automations")
CONFIG_PATH = Path("/config/configuration.yaml")
MANAGED_BLOCK_START = "# --- MagicLight managed automations (auto-generated) ---"
MANAGED_BLOCK_END = "# --- MagicLight managed automations end ---"


class BlueprintAutomationManager:
    """Orchestrates automatic creation/updating of blueprint automations."""

    def __init__(
        self,
        ws_client,
        *,
        enabled: bool,
        namespace: str = "magiclight",
        blueprint_filename: str = "hue_dimmer_switch.yaml",
    ) -> None:
        self.ws_client = ws_client
        self.enabled = enabled
        self.namespace = namespace
        self.blueprint_filename = blueprint_filename
        self.logger = logging.getLogger(__name__ + ".BlueprintAutomationManager")

        self._lock = asyncio.Lock()
        self._storage_warning_emitted = False

    def set_enabled(self, enabled: bool) -> None:
        """Enable or disable automatic blueprint management."""
        if self.enabled == enabled:
            return
        self.enabled = enabled
        if not enabled:
            self.logger.info("Blueprint management disabled; future ensure requests will be ignored.")

    async def reconcile_now(self, reason: str) -> None:
        """Run a reconciliation immediately (no queue)."""
        if not self.enabled:
            self.logger.debug("Skipping immediate reconcile (%s); disabled", reason)
            return
        await self._reconcile(reason)

    async def shutdown(self) -> None:
        """Compatibility hook; no background work to cancel."""
        return None

    async def _reconcile(self, reason: str) -> None:
        async with self._lock:
            if not self.enabled:
                return

            blueprint_path = self._locate_blueprint_file()
            if not blueprint_path:
                self.logger.warning(
                    "MagicLight blueprint %s/%s not found; skipping automation sync.",
                    self.namespace,
                    self.blueprint_filename,
                )
                return

            filters = self._extract_filters(blueprint_path)
            if not filters:
                self.logger.warning("Blueprint at %s does not define switch filters; skipping.", blueprint_path)
                return

            targeted_path = f"{self.namespace}/{self.blueprint_filename}"

            areas = await self._fetch_area_registry()
            devices = await self._fetch_device_registry()
            entities = await self._fetch_entity_registry()
            states = await self.ws_client.get_states()

            area_light_counts = self._calculate_area_light_counts(states, entities, devices)
            area_candidates = self._find_matching_devices(filters, devices, entities, area_light_counts)

            storage_path, storage_mode = self._determine_automation_storage()
            existing_managed = self._load_managed_automations(storage_path, storage_mode)

            desired_automations: List[Dict[str, Any]] = []
            sorted_candidates = sorted(
                area_candidates.items(),
                key=lambda item: (areas.get(item[0], {}).get("name") or item[0]).lower(),
            )

            for area_id, switch_devices in sorted_candidates:
                if not switch_devices:
                    continue

                area_name = areas.get(area_id, {}).get("name", area_id)
                desired_devices = sorted(set(switch_devices))
                alias = f"{ALIAS_PREFIX}{area_name}"

                desired_automations.append(
                    {
                        "id": self._automation_id_for_area(area_id),
                        "alias": alias,
                        "description": BLUEPRINT_DESCRIPTION,
                        "use_blueprint": {
                            "path": targeted_path,
                            "input": self._build_blueprint_inputs(desired_devices, [area_id]),
                        },
                    }
                )

            changes_made = self._persist_managed_automations(
                storage_path,
                storage_mode,
                desired_automations,
            )

            if changes_made:
                await self.ws_client.call_service("automation", "reload", {})
                self.logger.info(
                    "Reloaded automations after MagicLight blueprint sync (%s).",
                    reason,
                )
            else:
                if desired_automations or existing_managed:
                    self.logger.info(
                        "MagicLight blueprint automations already synchronized (%s).",
                        reason,
                    )
                else:
                    self.logger.info(
                        "No MagicLight-compatible switches discovered; skipping automation creation (%s).",
                        reason,
                    )

    # ---------- Data fetch helpers ----------

    async def _fetch_area_registry(self) -> Dict[str, Dict[str, Any]]:
        result = await self.ws_client.send_message_wait_response({"type": "config/area_registry/list"})
        areas: Dict[str, Dict[str, Any]] = {}
        if isinstance(result, Sequence):
            for item in result:
                area_id = item.get("area_id")
                if isinstance(area_id, str):
                    areas[area_id] = item
        return areas

    async def _fetch_device_registry(self) -> List[Dict[str, Any]]:
        result = await self.ws_client.send_message_wait_response({"type": "config/device_registry/list"})
        return result if isinstance(result, list) else []

    async def _fetch_entity_registry(self) -> List[Dict[str, Any]]:
        result = await self.ws_client.send_message_wait_response({"type": "config/entity_registry/list"})
        return result if isinstance(result, list) else []

    # ---------- Automation storage helpers ----------

    def _determine_automation_storage(self) -> Tuple[Path, str]:
        include_file_pattern = re.compile(r"^\s*automation:\s*!include\s+(?P<path>[^#\s]+)", re.MULTILINE)
        include_dir_pattern = re.compile(
            r"^\s*automation:\s*!include_dir_merge_list\s+(?P<path>[^#\s]+)",
            re.MULTILINE,
        )

        config_text: Optional[str] = None
        if CONFIG_PATH.is_file():
            try:
                config_text = CONFIG_PATH.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as err:
                self.logger.debug("Unable to read %s: %s", CONFIG_PATH, err)

        dir_match = file_match = None
        if config_text:
            dir_match = include_dir_pattern.search(config_text)
            if dir_match:
                include_dir = self._resolve_include_path(dir_match.group("path"))
                if include_dir:
                    return include_dir / "magiclight_managed.yaml", "dir"

            file_match = include_file_pattern.search(config_text)
            if file_match:
                include_file = self._resolve_include_path(file_match.group("path"))
                if include_file:
                    return include_file, "file"

        if (
            config_text
            and "automation:" in config_text
            and not dir_match
            and not file_match
            and not self._storage_warning_emitted
        ):
            self.logger.warning(
                "Unable to detect an automation include in configuration.yaml; assuming 'automations.yaml' is loaded. If you use storage mode, please add an include for MagicLight to manage automations."
            )
            self._storage_warning_emitted = True

        if AUTOMATIONS_FILE.exists() or not AUTOMATIONS_DIR.is_dir():
            return AUTOMATIONS_FILE, "file"

        return AUTOMATIONS_DIR / "magiclight_managed.yaml", "dir"

    def _resolve_include_path(self, raw_path: str) -> Optional[Path]:
        if not raw_path:
            return None
        cleaned = raw_path.strip()
        if not cleaned:
            return None
        if cleaned[0] in {'"', "'"} and cleaned[-1] == cleaned[0]:
            cleaned = cleaned[1:-1]

        candidate = Path(cleaned)
        if not candidate.is_absolute():
            candidate = Path("/config") / candidate
        try:
            return candidate.resolve()
        except OSError as err:
            self.logger.debug("Unable to resolve include path %s: %s", cleaned, err)
            return candidate

    def _load_managed_automations(self, storage_path: Path, storage_mode: str) -> List[Dict[str, Any]]:
        if storage_mode == "dir":
            if not storage_path.is_file():
                return []
            try:
                content = storage_path.read_text(encoding="utf-8")
                data = yaml.load(content, Loader=BlueprintLoader) or []
            except (OSError, yaml.YAMLError) as err:
                self.logger.error("Failed to read managed automations from %s: %s", storage_path, err)
                return []
            return data if isinstance(data, list) else []

        # storage_mode == "file"
        if not storage_path.is_file():
            return []
        try:
            text = storage_path.read_text(encoding="utf-8")
        except OSError as err:
            self.logger.error("Failed to read %s: %s", storage_path, err)
            return []

        block = self._extract_managed_block(text)
        if not block:
            return []
        try:
            data = yaml.load(block, Loader=BlueprintLoader) or []
        except yaml.YAMLError as err:
            self.logger.error(
                "Failed to parse MagicLight automation block in %s: %s",
                storage_path,
                err,
            )
            return []
        return data if isinstance(data, list) else []

    def _persist_managed_automations(
        self,
        storage_path: Path,
        storage_mode: str,
        automations: Sequence[Dict[str, Any]],
    ) -> bool:
        if storage_mode == "dir":
            storage_path.parent.mkdir(parents=True, exist_ok=True)
            if not automations:
                if storage_path.exists():
                    try:
                        storage_path.unlink()
                    except OSError as err:
                        self.logger.error("Failed to remove %s: %s", storage_path, err)
                        return False
                    return True
                return False

            rendered = yaml.safe_dump(
                list(automations),
                sort_keys=False,
                default_flow_style=False,
                allow_unicode=True,
            )
            existing = ""
            if storage_path.exists():
                try:
                    existing = storage_path.read_text(encoding="utf-8")
                except OSError as err:
                    self.logger.error("Failed to read %s: %s", storage_path, err)
                    existing = ""

            if existing.strip() == rendered.strip():
                return False

            try:
                storage_path.write_text(rendered, encoding="utf-8")
            except OSError as err:
                self.logger.error("Failed to write %s: %s", storage_path, err)
                return False
            return True

        # storage_mode == "file"
        existing_text = ""
        if storage_path.exists():
            try:
                existing_text = storage_path.read_text(encoding="utf-8")
            except OSError as err:
                self.logger.error("Failed to read %s: %s", storage_path, err)
                existing_text = ""

        new_block = self._render_managed_block(automations)
        updated_text = self._replace_managed_block(existing_text, new_block)

        if updated_text == existing_text:
            return False

        storage_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            storage_path.write_text(updated_text, encoding="utf-8")
        except OSError as err:
            self.logger.error("Failed to write %s: %s", storage_path, err)
            return False
        return True

    def _render_managed_block(self, automations: Sequence[Dict[str, Any]]) -> str:
        if not automations:
            return ""
        body = yaml.safe_dump(
            list(automations),
            sort_keys=False,
            default_flow_style=False,
            allow_unicode=True,
        ).rstrip()
        return f"{MANAGED_BLOCK_START}\n{body}\n{MANAGED_BLOCK_END}\n"

    def _replace_managed_block(self, existing_text: str, new_block: str) -> str:
        pattern = re.compile(
            rf"{re.escape(MANAGED_BLOCK_START)}\n.*?{re.escape(MANAGED_BLOCK_END)}\n?",
            re.DOTALL,
        )

        if pattern.search(existing_text):
            if new_block:
                replacement = new_block if new_block.endswith("\n") else new_block + "\n"
                updated = pattern.sub(replacement, existing_text)
            else:
                updated = pattern.sub("", existing_text)
                updated = updated.rstrip() + ("\n" if updated and not updated.endswith("\n") else "")
        else:
            if not new_block:
                return existing_text
            prefix = existing_text.rstrip()
            separator = "\n\n" if prefix else ""
            updated = f"{prefix}{separator}{new_block}"

        if updated and not updated.endswith("\n"):
            updated += "\n"
        return updated

    def _extract_managed_block(self, text: str) -> str:
        pattern = re.compile(
            rf"{re.escape(MANAGED_BLOCK_START)}\n(.*?){re.escape(MANAGED_BLOCK_END)}",
            re.DOTALL,
        )
        match = pattern.search(text)
        return match.group(1) if match else ""

    def _automation_id_for_area(self, area_id: str) -> str:
        sanitized = re.sub(r"[^a-zA-Z0-9_]+", "_", area_id or "").strip("_")
        if not sanitized:
            sanitized = "area"
        return f"magiclight_{sanitized.lower()}"

    # ---------- Blueprint parsing ----------

    def _locate_blueprint_file(self) -> Optional[Path]:
        candidates: List[Path] = []
        for base in (*BLUEPRINT_PATH_VARIANTS,):
            candidates.append(base / self.namespace / self.blueprint_filename)
        for base in (*LOCAL_BLUEPRINT_VARIANTS,):
            candidates.append(base / self.namespace / self.blueprint_filename)

        for path in candidates:
            if path.is_file():
                return path
        return None

    def _extract_filters(self, path: Path) -> List[Dict[str, Any]]:
        try:
            content = path.read_text(encoding="utf-8")
            data = yaml.load(content, Loader=BlueprintLoader) or {}
        except yaml.constructor.ConstructorError as err:
            self.logger.debug("Blueprint %s has YAML constructor tags not supported by safe_load (%s); skipping detailed parse.", path, err)
            return []
        except (OSError, yaml.YAMLError) as err:
            self.logger.error("Failed to parse blueprint %s: %s", path, err)
            return []

        try:
            selector = (
                data["blueprint"]["input"]["switch_device"]["selector"]["device"]
            )
            filters = selector.get("filter") if isinstance(selector, dict) else None
        except (KeyError, TypeError):
            filters = None

        return filters if isinstance(filters, list) else []

    # ---------- Matching logic ----------

    def _calculate_area_light_counts(
        self,
        states: Sequence[Dict[str, Any]],
        entities: Sequence[Dict[str, Any]],
        devices: Sequence[Dict[str, Any]],
    ) -> Dict[str, int]:
        device_area_map = {dev.get("id"): dev.get("area_id") for dev in devices if isinstance(dev, dict)}

        entity_area_map: Dict[str, Optional[str]] = {}
        for entity in entities:
            if not isinstance(entity, dict):
                continue
            entity_id = entity.get("entity_id")
            if not entity_id:
                continue
            area_id = entity.get("area_id")
            device_id = entity.get("device_id")
            if not area_id and device_id:
                area_id = device_area_map.get(device_id)
            entity_area_map[entity_id] = area_id

        counts: Dict[str, int] = defaultdict(int)
        for state in states or []:
            if not isinstance(state, dict):
                continue
            entity_id = state.get("entity_id")
            if not isinstance(entity_id, str) or not entity_id.startswith("light."):
                continue
            area_id = state.get("attributes", {}).get("area_id")
            if not area_id:
                area_id = entity_area_map.get(entity_id)
            if area_id:
                counts[area_id] += 1
        return counts

    def _find_matching_devices(
        self,
        filters: Sequence[Dict[str, Any]],
        devices: Sequence[Dict[str, Any]],
        entities: Sequence[Dict[str, Any]],
        area_light_counts: Dict[str, int],
    ) -> Dict[str, Set[str]]:
        if not filters:
            return {}

        filters_normalized = [self._normalize_filter(filt) for filt in filters if isinstance(filt, dict)]

        device_entities: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for entity in entities:
            if not isinstance(entity, dict):
                continue
            device_id = entity.get("device_id")
            if device_id:
                device_entities[device_id].append(entity)

        area_candidates: Dict[str, Set[str]] = defaultdict(set)

        for device in devices:
            if not isinstance(device, dict):
                continue
            device_id = device.get("id")
            if not isinstance(device_id, str):
                continue

            manufacturer = self._normalize_text(device.get("manufacturer"))
            model = self._normalize_text(device.get("model"))
            area_id = device.get("area_id")

            entity_list = device_entities.get(device_id, [])
            integrations = {self._normalize_text(entity.get("platform")) for entity in entity_list if entity.get("platform")}

            if not area_id:
                for entity in entity_list:
                    entity_area = entity.get("area_id")
                    if entity_area:
                        area_id = entity_area
                        break

            if not area_id or area_light_counts.get(area_id, 0) < 1:
                continue

            if self._device_matches_filters(manufacturer, model, integrations, filters_normalized):
                area_candidates[area_id].add(device_id)

        return area_candidates

    # ---------- Utility helpers ----------

    def _normalize_filter(self, filt: Dict[str, Any]) -> Dict[str, Any]:
        normalized = {}
        for key, value in filt.items():
            if isinstance(value, str):
                normalized[key] = self._normalize_text(value)
            else:
                normalized[key] = value
        return normalized

    def _device_matches_filters(
        self,
        manufacturer: str,
        model: str,
        integrations: Set[str],
        filters: Sequence[Dict[str, Any]],
    ) -> bool:
        for filt in filters:
            if not filt:
                continue
            match = True
            for key, expected in filt.items():
                if key == "integration":
                    if expected not in integrations:
                        match = False
                        break
                elif key == "manufacturer":
                    if manufacturer != expected:
                        match = False
                        break
                elif key == "model":
                    if model != expected:
                        match = False
                        break
                else:
                    # Ignore unsupported keys for now
                    continue
            if match:
                return True
        return False

    def _normalize_text(self, value: Any) -> str:
        if isinstance(value, str):
            return value.strip().lower()
        return ""

    def _build_blueprint_inputs(
        self,
        device_ids: Sequence[str],
        target_areas: Sequence[str],
    ) -> Dict[str, Any]:
        return {
            "switch_device": list(device_ids),
            "target_areas": list(target_areas),
        }
