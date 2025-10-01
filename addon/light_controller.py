"""
Light controller module for managing different lighting protocols.
Provides abstraction layer for ZigBee, Z-Wave, HomeAssistant, and other protocols.
"""

import asyncio
import json
import logging
import random
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Any, Union

logger = logging.getLogger(__name__)

# Known Hue/Signify button devices that expose a faux light entity via ZHA.
ZHA_BUTTON_MODELS = {"rom001", "rdm003"}


class Protocol(Enum):
    """Supported lighting protocols."""
    ZIGBEE = "zigbee"
    ZWAVE = "zwave"
    HOMEASSISTANT = "homeassistant"
    WIFI = "wifi"
    MATTER = "matter"


@dataclass
class LightCommand:
    """Command to control lights."""
    area: Optional[str] = None
    entity_ids: Optional[List[str]] = None
    brightness: Optional[int] = None  # 0-255
    color_temp: Optional[int] = None  # Kelvin
    rgb_color: Optional[tuple[int, int, int]] = None
    xy_color: Optional[tuple[float, float]] = None
    transition: Optional[float] = None  # seconds
    on: bool = True


@dataclass
class GroupCommand:
    """Command for group operations."""
    name: str
    group_id: Optional[int] = None
    members: Optional[List[Dict[str, Any]]] = None
    operation: str = "create"  # create, add_members, remove_members, delete


class LightController(ABC):
    """Abstract base class for light controllers."""
    
    def __init__(self, websocket_client):
        """Initialize the controller with a websocket client."""
        self.ws_client = websocket_client
        self.protocol = None
    
    @abstractmethod
    async def turn_on_lights(self, command: LightCommand) -> bool:
        """Turn on lights with specified parameters."""
        pass
    
    @abstractmethod
    async def turn_off_lights(self, command: LightCommand) -> bool:
        """Turn off lights."""
        pass
    
    @abstractmethod
    async def get_light_state(self, entity_id: str) -> Dict[str, Any]:
        """Get current state of a light."""
        pass
    
    @abstractmethod
    async def list_lights(self, area: Optional[str] = None) -> List[Dict[str, Any]]:
        """List available lights, optionally filtered by area."""
        pass
    
    async def supports_groups(self) -> bool:
        """Check if this controller supports group operations."""
        return False
    
    async def create_group(self, command: GroupCommand) -> bool:
        """Create a light group (if supported)."""
        raise NotImplementedError(f"{self.protocol} does not support groups")
    
    async def manage_group(self, command: GroupCommand) -> bool:
        """Manage group members (if supported)."""
        raise NotImplementedError(f"{self.protocol} does not support groups")


class ZigBeeController(LightController):
    """Controller for ZigBee/ZHA lights."""
    
    def __init__(self, websocket_client):
        super().__init__(websocket_client)
        self.protocol = Protocol.ZIGBEE
        self.area_to_group_id = {}  # Map area names to ZHA group IDs
    
    async def turn_on_lights(self, command: LightCommand) -> bool:
        """Turn on ZigBee lights via ZHA."""
        try:
            # Build service data
            service_data = {}
            
            # Light parameters
            if command.brightness is not None:
                service_data["brightness"] = command.brightness
            
            if command.color_temp is not None:
                # Convert Kelvin to mireds
                service_data["color_temp"] = int(1000000 / command.color_temp)
            
            if command.rgb_color:
                service_data["rgb_color"] = list(command.rgb_color)
            
            if command.xy_color:
                service_data["xy_color"] = list(command.xy_color)
            
            if command.transition is not None:
                service_data["transition"] = command.transition
            
            # Build target
            target = {}
            if command.area:
                target["area_id"] = command.area
            elif command.entity_ids:
                target["entity_id"] = command.entity_ids
            else:
                logger.error("No target specified for light command")
                return False
            
            # Send command
            result = await self.ws_client.call_service(
                "light",
                "turn_on",
                service_data,
                target
            )
            
            logger.info(f"ZigBee lights turned on in {command.area or command.entity_ids}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to turn on ZigBee lights: {e}")
            return False
    
    async def turn_off_lights(self, command: LightCommand) -> bool:
        """Turn off ZigBee lights."""
        try:
            # Build service data
            service_data = {}
            
            # Add transition if specified
            if command.transition is not None:
                service_data["transition"] = command.transition
            
            # Build target
            target = {}
            if command.area:
                target["area_id"] = command.area
            elif command.entity_ids:
                target["entity_id"] = command.entity_ids
            else:
                logger.error("No target specified for light command")
                return False
            
            # Send command
            result = await self.ws_client.call_service(
                "light",
                "turn_off",
                service_data,
                target
            )
            
            logger.info(f"ZigBee lights turned off in {command.area or command.entity_ids}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to turn off ZigBee lights: {e}")
            return False
    
    async def get_light_state(self, entity_id: str) -> Dict[str, Any]:
        """Get current state of a ZigBee light."""
        try:
            states = await self.ws_client.get_states()
            for state in states:
                if state['entity_id'] == entity_id:
                    return {
                        'entity_id': entity_id,
                        'state': state['state'],
                        'brightness': state['attributes'].get('brightness'),
                        'color_temp': state['attributes'].get('color_temp'),
                        'rgb_color': state['attributes'].get('rgb_color'),
                        'xy_color': state['attributes'].get('xy_color'),
                        'is_on': state['state'] == 'on'
                    }
            return {}
        except Exception as e:
            logger.error(f"Failed to get light state: {e}")
            return {}
    
    async def list_lights(self, area: Optional[str] = None) -> List[Dict[str, Any]]:
        """List ZigBee lights, optionally filtered by area."""
        try:
            lights = []
            states = await self.ws_client.get_states()
            
            for state in states:
                if not state['entity_id'].startswith('light.'):
                    continue
                
                # Check if it's a ZHA light
                if state['attributes'].get('platform') != 'zha':
                    continue
                
                # Filter by area if specified
                if area and state['attributes'].get('area_id') != area:
                    continue
                
                lights.append({
                    'entity_id': state['entity_id'],
                    'name': state['attributes'].get('friendly_name'),
                    'area': state['attributes'].get('area_id'),
                    'state': state['state'],
                    'brightness': state['attributes'].get('brightness'),
                    'color_temp': state['attributes'].get('color_temp')
                })
            
            return lights
            
        except Exception as e:
            logger.error(f"Failed to list ZigBee lights: {e}")
            return []
    
    async def supports_groups(self) -> bool:
        """ZigBee supports group operations via ZHA."""
        return True
    
    async def list_zha_groups(self) -> List[Dict[str, Any]]:
        """List all ZHA groups."""
        try:
            result = await self.ws_client.send_message_wait_response({"type": "zha/groups"})
            return result if result else []
        except Exception as e:
            logger.error(f"Failed to list ZHA groups: {e}")
            return []
    
    async def list_zha_devices(self) -> List[Dict[str, Any]]:
        """List all ZHA devices."""
        try:
            result = await self.ws_client.send_message_wait_response({"type": "zha/devices"})
            return result if result else []
        except Exception as e:
            logger.error(f"Failed to list ZHA devices: {e}")
            return []
    
    async def get_zha_device_endpoints(self, ieee: str) -> Dict[int, List[int]]:
        """Get endpoint information for a specific ZHA device by IEEE.
        
        Returns a dict mapping endpoint IDs to their output clusters.
        """
        try:
            devices = await self.list_zha_devices()
            for device in devices:
                if device.get('ieee', '').lower() == ieee.lower():
                    endpoints = {}
                    for ep_id, ep_data in device.get('endpoints', {}).items():
                        if isinstance(ep_data, dict):
                            endpoints[int(ep_id)] = ep_data.get('output_clusters', [])
                    return endpoints
            return {}
        except Exception as e:
            logger.error(f"Failed to get device endpoints: {e}")
            return {}
    
    def determine_light_endpoint(self, zha_device: Optional[Dict] = None, manufacturer: str = '', model: str = '') -> int:
        """Determine the best endpoint for a light device.
        
        Args:
            zha_device: Optional ZHA device data with endpoints information
            manufacturer: Device manufacturer (used for fallback detection)
            model: Device model (used for fallback detection)
            
        Returns:
            The endpoint ID to use for light control
        """
        manufacturer = manufacturer.lower()
        model = model.lower()
        
        # Hue/Signify bulbs typically use endpoint 11
        if 'signify' in manufacturer or 'philips' in manufacturer or 'hue' in model or 'signify' in model:
            return 11
        # IKEA bulbs typically use endpoint 1
        elif 'ikea' in manufacturer:
            return 1
        # Default to endpoint 11
        else:
            return 11
    
    async def get_areas(self) -> Dict[str, Dict[str, Any]]:
        """Get all areas and their associated entities."""
        try:
            logger.debug("Getting areas and their associated entities...")
            
            # Get all areas
            areas_result = await self.ws_client.send_message_wait_response({"type": "config/area_registry/list"})
            if not areas_result:
                return {}
            
            areas = {}
            for area in areas_result:
                area_id = area.get('area_id')
                area_name = area.get('name')
                if area_id and area_name:
                    areas[area_id] = {
                        'name': area_name,
                        'area_id': area_id,
                        'lights': [],
                        'zha_lights': [],
                        'non_zha_lights': []  # Track non-ZHA lights
                    }
            
            # Get device registry to map devices to entities
            device_registry = await self.ws_client.send_message_wait_response({"type": "config/device_registry/list"})
            device_by_id = {}
            if device_registry:
                for device in device_registry:
                    device_id = device.get('id')
                    if device_id:
                        device_by_id[device_id] = device
            
            # Get entity registry to find device associations
            entity_registry = await self.ws_client.send_message_wait_response({"type": "config/entity_registry/list"})
            entity_to_device = {}
            if entity_registry:
                for entity in entity_registry:
                    entity_id = entity.get('entity_id')
                    device_id = entity.get('device_id')
                    if entity_id and device_id:
                        entity_to_device[entity_id] = device_id
            
            # Get all ZHA devices for IEEE lookup
            zha_devices = await self.list_zha_devices()
            logger.info(f"Found {len(zha_devices)} ZHA devices")
            zha_device_by_id = {}
            zha_device_by_ieee = {}
            for zha_dev in zha_devices:
                # Match ZHA device to HA device by name or ID
                dev_id = zha_dev.get('device_id')
                ieee = zha_dev.get('ieee')
                if dev_id:
                    zha_device_by_id[dev_id] = zha_dev
                if ieee:
                    # Store IEEE addresses as lowercase for consistency
                    zha_device_by_ieee[ieee.lower()] = zha_dev
                    logger.debug(f"ZHA device: IEEE={ieee.lower()}, name={zha_dev.get('name')}")
            
            # Get all states to find lights in each area
            states = await self.ws_client.get_states()
            for state in states:
                entity_id = state.get('entity_id', '')
                if entity_id.startswith('light.'):
                    attributes = state.get('attributes', {})
                    device_id = entity_to_device.get(entity_id)

                    manufacturer_attr = (attributes.get('manufacturer') or '').lower()
                    model_attr = (attributes.get('model') or '').lower()

                    # Fall back to device registry info if attributes are missing
                    if (not manufacturer_attr or not model_attr) and device_id and device_id in device_by_id:
                        ha_device = device_by_id[device_id]
                        if not manufacturer_attr:
                            manufacturer_attr = (ha_device.get('manufacturer') or '').lower()
                        if not model_attr:
                            model_attr = (ha_device.get('model') or '').lower()

                    if model_attr in ZHA_BUTTON_MODELS:
                        logger.info(
                            "Skipping non-light ZHA button entity %s (manufacturer=%s, model=%s)",
                            entity_id,
                            manufacturer_attr or "unknown",
                            model_attr or "unknown",
                        )
                        continue

                    # Try to get area_id from attributes first
                    area_id = attributes.get('area_id')

                    # If not in attributes, try to get from device
                    if not area_id and device_id and device_id in device_by_id:
                        area_id = device_by_id[device_id].get('area_id')

                    if area_id and area_id in areas:
                        area_name = areas[area_id]['name']
                        skip_entity = False
                        pending_zha_entry = None
                        is_zha = False

                        if device_id and device_id in device_by_id:
                            ha_device = device_by_id[device_id]

                            # Check if this is a ZHA device by looking at identifiers
                            ha_identifiers = ha_device.get('identifiers', [])
                            for identifier in ha_identifiers:
                                if isinstance(identifier, list) and len(identifier) >= 2 and identifier[0] == 'zha':
                                    is_zha = True
                                    # This is a ZHA device - identifier[1] is the IEEE
                                    zha_ieee = identifier[1].lower()  # Convert to lowercase

                                    # Try to find this device in our ZHA devices list
                                    zha_dev = zha_device_by_ieee.get(zha_ieee)

                                    if zha_dev:
                                        zha_model = (zha_dev.get('model') or '').lower()
                                        if zha_model in ZHA_BUTTON_MODELS:
                                            logger.info(
                                                "Skipping ZHA button device %s (IEEE: %s, model: %s)",
                                                entity_id,
                                                zha_ieee,
                                                zha_model,
                                            )
                                            skip_entity = True
                                            break

                                        endpoint_id = self.determine_light_endpoint(
                                            zha_device=zha_dev,
                                            manufacturer=attributes.get('manufacturer', ''),
                                            model=attributes.get('model', '')
                                        )
                                        logger.debug(f"Selected endpoint {endpoint_id} for {entity_id} (IEEE: {zha_ieee})")

                                        pending_zha_entry = {
                                            'entity_id': entity_id,
                                            'ieee': zha_ieee,
                                            'endpoint_id': endpoint_id
                                        }
                                        logger.debug(
                                            "Found ZHA light in area %s: %s (IEEE: %s)",
                                            area_name,
                                            entity_id,
                                            zha_ieee,
                                        )
                                    else:
                                        if model_attr in ZHA_BUTTON_MODELS:
                                            logger.info(
                                                "Skipping ZHA button entity without device info %s (model: %s)",
                                                entity_id,
                                                model_attr,
                                            )
                                            skip_entity = True
                                            break
                                        # Even if we don't have full ZHA device info, we have the IEEE
                                        # Use centralized endpoint detection with manufacturer/model fallback
                                        manufacturer = attributes.get('manufacturer', '')
                                        model = attributes.get('model', '')

                                        logger.info(
                                            "Light %s: manufacturer='%s', model='%s'",
                                            entity_id,
                                            manufacturer,
                                            model,
                                        )

                                        endpoint_id = self.determine_light_endpoint(
                                            zha_device=None,
                                            manufacturer=manufacturer,
                                            model=model
                                        )

                                        pending_zha_entry = {
                                            'entity_id': entity_id,
                                            'ieee': zha_ieee,
                                            'endpoint_id': endpoint_id
                                        }
                                        logger.info(
                                            "Found ZHA light by identifier in area %s: %s (IEEE: %s, endpoint: %s, manufacturer: '%s', model: '%s')",
                                            area_name,
                                            entity_id,
                                            zha_ieee,
                                            endpoint_id,
                                            manufacturer,
                                            model,
                                        )
                                    break

                            if skip_entity:
                                continue

                        areas[area_id]['lights'].append(entity_id)

                        if pending_zha_entry:
                            areas[area_id]['zha_lights'].append(pending_zha_entry)

                        # If not a ZHA light, add to non-ZHA lights list
                        if not is_zha:
                            areas[area_id]['non_zha_lights'].append(entity_id)
                            logger.debug(f"Found non-ZHA light in area {area_name}: {entity_id}")
            
            return areas
            
        except Exception as e:
            logger.error(f"Failed to get areas: {e}")
            return {}
    
    async def check_area_zha_parity(self, area_id: str) -> bool:
        """Check if an area has Zigbee group parity (all lights are ZHA).
        
        NOTE: This method should only be called during initialization or when
        refreshing the cache. During normal operation, use the cached value
        in ws_client.area_parity_cache to avoid concurrent WebSocket calls.
        
        Args:
            area_id: The area ID to check
            
        Returns:
            True if all lights in the area are ZHA lights (can use ZHA group),
            False if there are any non-ZHA lights (should use area-based control)
        """
        # First check if we have a cached value (preferred during runtime)
        if hasattr(self.ws_client, 'area_parity_cache') and area_id in self.ws_client.area_parity_cache:
            return self.ws_client.area_parity_cache[area_id]
        
        # Otherwise do the full check (only during initialization)
        try:
            areas = await self.get_areas()
            area_info = areas.get(area_id)
            
            if not area_info:
                logger.warning(f"Area {area_id} not found")
                return False
            
            zha_lights = area_info.get('zha_lights', [])
            non_zha_lights = area_info.get('non_zha_lights', [])
            
            # Log the parity check
            logger.info(f"Area '{area_info['name']}' parity check: {len(zha_lights)} ZHA lights, {len(non_zha_lights)} non-ZHA lights")
            
            # If there are no lights at all, return False (use area-based as fallback)
            if not zha_lights and not non_zha_lights:
                logger.info(f"Area '{area_info['name']}' has no lights, using area-based control")
                return False
            
            # If there are any non-ZHA lights, we don't have parity
            if non_zha_lights:
                logger.info(f"Area '{area_info['name']}' has non-ZHA lights, using area-based control for full coverage")
                return False
            
            # All lights are ZHA
            logger.info(f"Area '{area_info['name']}' has ZHA parity, can use ZHA group control")
            return True
            
        except Exception as e:
            logger.error(f"Failed to check ZHA parity for area {area_id}: {e}")
            return False
    
    async def ensure_magic_area_exists(self) -> str:
        """Ensure the 'Magic_Zigbee_Groups' area exists for storing ZHA group entities.
        
        Returns:
            The area_id of the Magic_Zigbee_Groups area
        """
        try:
            # Get current areas
            areas_result = await self.ws_client.send_message_wait_response({"type": "config/area_registry/list"})
            
            # Check if Magic_Zigbee_Groups area exists
            magic_area_id = None
            if areas_result:
                for area in areas_result:
                    if area.get("name") == "Magic_Zigbee_Groups":
                        magic_area_id = area.get("area_id")
                        logger.info(f"Found existing Magic_Zigbee_Groups area with ID: {magic_area_id}")
                        break
            
            # Create Magic_Zigbee_Groups area if it doesn't exist
            if not magic_area_id:
                logger.info("Creating Magic_Zigbee_Groups area for ZHA groups...")
                result = await self.ws_client.send_message_wait_response({
                    "type": "config/area_registry/create",
                    "name": "Magic_Zigbee_Groups"
                })
                if result and "area_id" in result:
                    magic_area_id = result["area_id"]
                    logger.info(f"Created Magic_Zigbee_Groups area with ID: {magic_area_id}")
                else:
                    logger.error("Failed to create Magic_Zigbee_Groups area")
            
            return magic_area_id
            
        except Exception as e:
            logger.error(f"Failed to ensure Magic_Zigbee_Groups area exists: {e}")
            return None
    
    async def move_group_entity_to_magic_area(self, group_name: str, magic_area_id: str) -> bool:
        """Find the entity_id for a ZHA group and move it to the Magic_Zigbee_Groups area.
        
        Args:
            group_name: The name of the ZHA group (e.g., "Magic_Living_Room")
            magic_area_id: The area_id of the Magic_Zigbee_Groups area
            
        Returns:
            True if successful
        """
        try:
            # Get entity registry to find the group entity
            entity_registry = await self.ws_client.send_message_wait_response({"type": "config/entity_registry/list"})
            
            if entity_registry:
                for entity in entity_registry:
                    entity_id = entity.get("entity_id", "")
                    # ZHA group entities typically have the group name in their entity_id
                    # They're usually like light.glo_living_room or similar
                    if entity_id.startswith("light.") and group_name.lower().replace("_", "") in entity_id.lower().replace("_", ""):
                        # Found the group entity, move it to Glo area
                        logger.info(f"Found group entity {entity_id} for group {group_name}")
                        
                        # Check current area
                        current_area = entity.get("area_id")
                        if current_area != magic_area_id:
                            success = await self.move_entity_to_area(entity_id, magic_area_id)
                            if success:
                                logger.info(f"Moved ZHA group entity {entity_id} to Magic_Zigbee_Groups area")
                            return success
                        else:
                            logger.info(f"Group entity {entity_id} already in Magic_Zigbee_Groups area")
                            return True
            
            logger.warning(f"Could not find entity for ZHA group {group_name}")
            return False
            
        except Exception as e:
            logger.error(f"Failed to move group entity to Glo_Zigbee_Groups area: {e}")
            return False
    
    async def move_entity_to_area(self, entity_id: str, area_id: str) -> bool:
        """Move an entity to a specific area.
        
        Args:
            entity_id: The entity to move
            area_id: The target area ID
            
        Returns:
            True if successful
        """
        try:
            result = await self.ws_client.send_message_wait_response({
                "type": "config/entity_registry/update",
                "entity_id": entity_id,
                "area_id": area_id
            })
            
            if result:
                logger.info(f"Moved entity {entity_id} to area {area_id}")
                return True
            else:
                logger.warning(f"Failed to move entity {entity_id} to area {area_id}")
                return False
                
        except Exception as e:
            logger.error(f"Error moving entity {entity_id} to area: {e}")
            return False
    
    async def sync_zha_groups_with_areas(self, areas_with_switches: set = None) -> tuple[bool, dict]:
        """Synchronize ZHA groups to match Home Assistant areas that have switches.
        
        Creates a ZHA group for each area that has both ZHA lights and switches,
        updates membership as needed, and deletes groups for areas that no longer exist.
        
        Args:
            areas_with_switches: Set of area IDs that have switches. If None, creates groups for all areas.
            
        Returns:
            Tuple of (success, areas_dict) where areas_dict is the areas data for reuse
        """
        try:
            logger.info("Starting ZHA group synchronization with areas...")
            
            # Ensure Magic_Zigbee_Groups area exists for our groups
            magic_area_id = await self.ensure_magic_area_exists()
            if not magic_area_id:
                logger.warning("Could not ensure Magic_Zigbee_Groups area exists, groups may be placed in random areas")
            
            # Get current ZHA groups
            existing_groups = await self.list_zha_groups()
            logger.info(f"Retrieved {len(existing_groups)} existing ZHA groups")
            for group in existing_groups:
                members = group.get('members', [])
                logger.info(f"Group '{group.get('name')}' (ID={group.get('group_id')}): {len(members)} members")
            existing_groups_by_name = {g.get('name'): g for g in existing_groups}
            
            # Get all areas with their lights
            areas = await self.get_areas()
            
            # Get ZHA devices for IEEE lookup
            zha_devices = await self.list_zha_devices()
            device_by_ieee = {d.get('ieee'): d for d in zha_devices}
            
            # Track which groups should exist
            expected_group_names = set()
            
            # Process each area
            for area_id, area_info in areas.items():
                # Skip areas without switches (if areas_with_switches is provided)
                if areas_with_switches is not None and area_id not in areas_with_switches:
                    logger.debug(f"Area '{area_info['name']}' has no switches, skipping group creation")
                    continue
                
                area_name = area_info['name']
                zha_lights = area_info.get('zha_lights', [])
                non_zha_lights = area_info.get('non_zha_lights', [])
                
                if not zha_lights:
                    logger.debug(f"Area '{area_name}' has no ZHA lights, skipping group creation")
                    continue
                
                # Skip areas that don't have ZHA parity (have non-ZHA lights)
                if non_zha_lights:
                    logger.info(f"Area '{area_name}' has {len(non_zha_lights)} non-ZHA lights, skipping ZHA group creation (will use area-based control)")
                    continue
                
                # Group name format: "Magic_<area_name>"
                group_name = f"Magic_{area_name.replace(' ', '_')}"
                expected_group_names.add(group_name)
                
                # Prepare members list
                members = []
                logger.debug(f"Area '{area_name}' has {len(zha_lights)} ZHA lights to add")
                for light in zha_lights:
                    ieee = light.get('ieee')
                    endpoint_id = light.get('endpoint_id', 11)
                    logger.debug(f"  - Light {light.get('entity_id')}: IEEE={ieee}, endpoint={endpoint_id}")
                    
                    if ieee:
                        # Don't require the device to be in device_by_ieee - just use the IEEE we found
                        # Ensure IEEE is lowercase for ZHA compatibility
                        members.append({
                            'ieee': ieee.lower(),
                            'endpoint_id': endpoint_id
                        })
                        logger.debug(f"    Added to members list with IEEE={ieee.lower()}")
                    else:
                        logger.warning(f"    No IEEE address for light {light.get('entity_id')}")
                
                if not members:
                    logger.warning(f"No valid ZHA devices found for area '{area_name}' - {len(zha_lights)} lights had no IEEE")
                    continue
                
                logger.info(f"Prepared {len(members)} members for group '{group_name}'")
                
                # Check if group exists
                existing_group = existing_groups_by_name.get(group_name)
                
                if existing_group:
                    # Group exists - check if membership needs updating
                    existing_members = existing_group.get('members', [])
                    
                    # Handle empty groups or groups with None members
                    if not existing_members or (len(existing_members) == 1 and existing_members[0] is None):
                        # Group is empty, just add all members
                        logger.info(f"Group '{group_name}' is empty, adding all {len(members)} members")
                        await self.manage_group(GroupCommand(
                            name=group_name,
                            group_id=existing_group['group_id'],
                            members=members,
                            operation='add_members'
                        ))
                    else:
                        # Compare existing and new members (ensure lowercase comparison)
                        # Handle nested structure where IEEE is in device.ieee
                        existing_member_set = set()
                        for m in existing_members:
                            if m:
                                # Check if IEEE is directly on member or nested in device
                                ieee = m.get('ieee') or (m.get('device', {}).get('ieee') if m.get('device') else None)
                                endpoint_id = m.get('endpoint_id')
                                if ieee and endpoint_id is not None:
                                    existing_member_set.add((ieee.lower(), endpoint_id))
                        
                        new_member_set = {(m['ieee'].lower(), m['endpoint_id']) for m in members}
                        
                        if existing_member_set != new_member_set:
                            logger.info(f"Updating members for group '{group_name}'")
                            logger.info(f"  Existing members: {existing_member_set}")
                            logger.info(f"  New members: {new_member_set}")
                            
                            # Remove members that shouldn't be in the group
                            to_remove = [{'ieee': ieee, 'endpoint_id': ep} 
                                       for ieee, ep in existing_member_set - new_member_set]
                            if to_remove:
                                logger.info(f"Removing {len(to_remove)} members from group {group_name}")
                                for member in to_remove:
                                    logger.info(f"  Remove: IEEE={member['ieee']}, endpoint={member['endpoint_id']}")
                                result = await self.manage_group(GroupCommand(
                                    name=group_name,
                                    group_id=existing_group['group_id'],
                                    members=to_remove,
                                    operation='remove_members'
                                ))
                                if not result:
                                    logger.error(f"Failed to remove members from group {group_name}")
                            
                            # Add new members
                            to_add = [{'ieee': ieee, 'endpoint_id': ep} 
                                    for ieee, ep in new_member_set - existing_member_set]
                            if to_add:
                                logger.info(f"Adding {len(to_add)} members to group {group_name}")
                                for member in to_add:
                                    logger.info(f"  Add: IEEE={member['ieee']}, endpoint={member['endpoint_id']}")
                                result = await self.manage_group(GroupCommand(
                                    name=group_name,
                                    group_id=existing_group['group_id'],
                                    members=to_add,
                                    operation='add_members'
                                ))
                                if not result:
                                    logger.error(f"Failed to add members to group {group_name}")
                        else:
                            logger.debug(f"Group '{group_name}' already has correct members")
                    
                    # Store mapping
                    self.area_to_group_id[area_name] = existing_group['group_id']
                    
                    # Move existing group entity to Magic area if needed
                    if magic_area_id:
                        await self.move_group_entity_to_magic_area(group_name, magic_area_id)
                else:
                    # Create new group with random 16-bit group ID
                    # Generate random 16-bit integer (0-65535)
                    random_group_id = random.randint(1, 65535)
                    logger.info(f"Creating new ZHA group '{group_name}' for area '{area_name}' with ID {random_group_id}")
                    success = await self.create_group(GroupCommand(
                        name=group_name,
                        group_id=random_group_id,
                        members=members
                    ))
                    
                    if success:
                        # Get the newly created group to store its ID
                        updated_groups = await self.list_zha_groups()
                        for g in updated_groups:
                            if g.get('name') == group_name:
                                self.area_to_group_id[area_name] = g['group_id']
                                
                                # Find the entity_id for this group and move it to Magic area
                                if magic_area_id:
                                    await self.move_group_entity_to_magic_area(group_name, magic_area_id)
                                
                                break
            
            # Delete groups for areas that no longer exist (only our Magic_ groups)
            for group_name, group in existing_groups_by_name.items():
                if group_name.startswith('Magic_') and group_name not in expected_group_names:
                    logger.info(f"Removing obsolete ZHA group '{group_name}'")
                    await self.manage_group(GroupCommand(
                        name=group_name,
                        group_id=group['group_id'],
                        operation='delete'
                    ))
            
            logger.info("ZHA group synchronization completed")
            return True, areas
            
        except Exception as e:
            logger.error(f"Failed to sync ZHA groups: {e}")
            return False, {}
    
    async def create_group(self, command: GroupCommand) -> bool:
        """Create a ZHA group."""
        try:
            message = {
                "type": "zha/group/add",
                "group_name": command.name
            }
            
            if command.group_id is not None:
                message["group_id"] = command.group_id
            
            if command.members:
                message["members"] = command.members
            
            result = await self.ws_client.send_message_wait_response(message)
            logger.info(f"Created ZHA group: {command.name}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to create ZHA group: {e}")
            return False
    
    async def manage_group(self, command: GroupCommand) -> bool:
        """Manage ZHA group members."""
        try:
            if command.operation == "add_members":
                message = {
                    "type": "zha/group/members/add",
                    "group_id": command.group_id,
                    "members": command.members
                }
            elif command.operation == "remove_members":
                message = {
                    "type": "zha/group/members/remove",
                    "group_id": command.group_id,
                    "members": command.members
                }
            elif command.operation == "delete":
                message = {
                    "type": "zha/group/remove",
                    "group_id": command.group_id
                }
            else:
                logger.error(f"Unknown group operation: {command.operation}")
                return False
            
            logger.debug(f"Sending group management message: {json.dumps(message, indent=2)}")
            result = await self.ws_client.send_message_wait_response(message)
            logger.info(f"Group operation {command.operation} completed for group {command.group_id}")
            logger.debug(f"Result: {result}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to manage ZHA group: {e}")
            logger.error(f"Error details: {str(e)}")
            return False


class HomeAssistantController(LightController):
    """Controller for native HomeAssistant lights (non-protocol specific)."""
    
    def __init__(self, websocket_client):
        super().__init__(websocket_client)
        self.protocol = Protocol.HOMEASSISTANT
    
    async def turn_on_lights(self, command: LightCommand) -> bool:
        """Turn on lights via HomeAssistant service calls."""
        try:
            service_data = {}
            
            # Build service data
            if command.brightness is not None:
                service_data["brightness"] = command.brightness
            
            if command.color_temp is not None:
                # Convert Kelvin to mireds
                service_data["color_temp"] = int(1000000 / command.color_temp)
            
            if command.rgb_color:
                service_data["rgb_color"] = list(command.rgb_color)
            
            if command.xy_color:
                service_data["xy_color"] = list(command.xy_color)
            
            if command.transition is not None:
                service_data["transition"] = command.transition
            
            # Determine target
            target = {}
            if command.area:
                target["area_id"] = command.area
            elif command.entity_ids:
                target["entity_id"] = command.entity_ids
            
            # Call service
            result = await self.ws_client.call_service(
                "light",
                "turn_on",
                service_data,
                target
            )
            
            logger.info(f"HomeAssistant lights turned on")
            return True
            
        except Exception as e:
            logger.error(f"Failed to turn on HomeAssistant lights: {e}")
            return False
    
    async def turn_off_lights(self, command: LightCommand) -> bool:
        """Turn off lights via HomeAssistant."""
        try:
            service_data = {}
            if command.transition is not None:
                service_data["transition"] = command.transition
            
            target = {}
            if command.area:
                target["area_id"] = command.area
            elif command.entity_ids:
                target["entity_id"] = command.entity_ids
            
            result = await self.ws_client.call_service(
                "light",
                "turn_off",
                service_data,
                target
            )
            
            logger.info(f"HomeAssistant lights turned off")
            return True
            
        except Exception as e:
            logger.error(f"Failed to turn off HomeAssistant lights: {e}")
            return False
    
    async def get_light_state(self, entity_id: str) -> Dict[str, Any]:
        """Get current state of any light via HomeAssistant."""
        try:
            states = await self.ws_client.get_states()
            for state in states:
                if state['entity_id'] == entity_id:
                    return {
                        'entity_id': entity_id,
                        'state': state['state'],
                        'brightness': state['attributes'].get('brightness'),
                        'color_temp': state['attributes'].get('color_temp'),
                        'rgb_color': state['attributes'].get('rgb_color'),
                        'xy_color': state['attributes'].get('xy_color'),
                        'is_on': state['state'] == 'on'
                    }
            return {}
        except Exception as e:
            logger.error(f"Failed to get light state: {e}")
            return {}
    
    async def list_lights(self, area: Optional[str] = None) -> List[Dict[str, Any]]:
        """List all lights via HomeAssistant."""
        try:
            lights = []
            states = await self.ws_client.get_states()
            
            for state in states:
                if not state['entity_id'].startswith('light.'):
                    continue
                
                # Filter by area if specified
                if area and state['attributes'].get('area_id') != area:
                    continue
                
                lights.append({
                    'entity_id': state['entity_id'],
                    'name': state['attributes'].get('friendly_name'),
                    'area': state['attributes'].get('area_id'),
                    'state': state['state'],
                    'brightness': state['attributes'].get('brightness'),
                    'color_temp': state['attributes'].get('color_temp'),
                    'platform': state['attributes'].get('platform', 'unknown')
                })
            
            return lights
            
        except Exception as e:
            logger.error(f"Failed to list lights: {e}")
            return []


class LightControllerFactory:
    """Factory for creating appropriate light controllers."""
    
    @staticmethod
    def create_controller(protocol: Protocol, websocket_client) -> LightController:
        """Create a light controller for the specified protocol."""
        if protocol == Protocol.ZIGBEE:
            return ZigBeeController(websocket_client)
        elif protocol == Protocol.HOMEASSISTANT:
            return HomeAssistantController(websocket_client)
        else:
            raise NotImplementedError(f"Protocol {protocol} not yet implemented")
    
    @staticmethod
    def create_multi_protocol_controller(websocket_client) -> 'MultiProtocolController':
        """Create a controller that can handle multiple protocols."""
        return MultiProtocolController(websocket_client)


class MultiProtocolController:
    """Controller that manages multiple protocol controllers."""
    
    def __init__(self, websocket_client):
        self.ws_client = websocket_client
        self.controllers: Dict[Protocol, LightController] = {}
        self.default_protocol = Protocol.HOMEASSISTANT
    
    def add_controller(self, protocol: Protocol) -> None:
        """Add a controller for a specific protocol."""
        controller = LightControllerFactory.create_controller(protocol, self.ws_client)
        self.controllers[protocol] = controller
    
    def set_default_protocol(self, protocol: Protocol) -> None:
        """Set the default protocol to use."""
        self.default_protocol = protocol
    
    async def turn_on_lights(self, command: LightCommand, protocol: Optional[Protocol] = None) -> bool:
        """Turn on lights using specified or default protocol."""
        protocol = protocol or self.default_protocol
        
        if protocol not in self.controllers:
            self.add_controller(protocol)
        
        return await self.controllers[protocol].turn_on_lights(command)
    
    async def turn_off_lights(self, command: LightCommand, protocol: Optional[Protocol] = None) -> bool:
        """Turn off lights using specified or default protocol."""
        protocol = protocol or self.default_protocol
        
        if protocol not in self.controllers:
            self.add_controller(protocol)
        
        return await self.controllers[protocol].turn_off_lights(command)
    
    async def auto_detect_protocol(self, entity_id: str) -> Optional[Protocol]:
        """Auto-detect the protocol for a given entity."""
        try:
            states = await self.ws_client.get_states()
            for state in states:
                if state['entity_id'] == entity_id:
                    platform = state['attributes'].get('platform', '')
                    
                    if platform == 'zha':
                        return Protocol.ZIGBEE
                    elif platform == 'zwave_js':
                        return Protocol.ZWAVE
                    elif platform in ['hue', 'lifx', 'tuya', 'wiz']:
                        return Protocol.WIFI
                    else:
                        return Protocol.HOMEASSISTANT
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to auto-detect protocol: {e}")
            return None
