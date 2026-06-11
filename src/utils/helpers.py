import yaml
import os
import discord
from typing import Dict, Any, Optional
from src.utils.logger import setup_logger

logger = setup_logger("helpers")

def load_yaml_config(file_path: str) -> Dict[str, Any]:
    """Load and parse a YAML configuration file."""
    if not os.path.exists(file_path):
        logger.error(f"Configuration file not found: {file_path}")
        raise FileNotFoundError(f"Configuration file not found: {file_path}")
    
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception as e:
        logger.error(f"Failed to parse YAML file {file_path}: {e}")
        raise e

def parse_color(color_hex: Optional[str]) -> discord.Color:
    """Parse hex string to discord.Color."""
    if not color_hex:
        return discord.Color.default()
    
    # Strip # if present
    color_hex = color_hex.lstrip("#")
    try:
        return discord.Color(int(color_hex, 16))
    except ValueError:
        logger.warning(f"Invalid hex color '{color_hex}', defaulting to default color.")
        return discord.Color.default()

def parse_permissions(perm_list: list) -> discord.Permissions:
    """Convert list of permission dicts or names to discord.Permissions."""
    perms = discord.Permissions.none()
    
    # Handle single string like "administrator" or a dictionary format
    for item in perm_list:
        if isinstance(item, str):
            if hasattr(perms, item):
                setattr(perms, item, True)
        elif isinstance(item, dict):
            for key, val in item.items():
                if hasattr(perms, key):
                    setattr(perms, key, bool(val))
                    
    return perms

def to_bold_unicode(text: str) -> str:
    bold_map = {}
    for i in range(26):
        bold_map[chr(ord('a') + i)] = chr(0x1D41A + i)
    for i in range(10):
        bold_map[chr(ord('0') + i)] = chr(0x1D7CE + i)
    res = []
    for char in text.lower():
        res.append(bold_map.get(char, char))
    return "".join(res)

def from_bold_unicode(text: str) -> str:
    res = []
    for char in text:
        val = ord(char)
        # Mathematical Bold Small a-z: U+1D41A to U+1D433
        if 0x1D41A <= val <= 0x1D433:
            res.append(chr(ord('a') + (val - 0x1D41A)))
        # Mathematical Bold Digit 0-9: U+1D7CE to U+1D7D7
        elif 0x1D7CE <= val <= 0x1D7D7:
            res.append(chr(ord('0') + (val - 0x1D7CE)))
        else:
            res.append(char)
    return "".join(res)

def normalize_name(text: str) -> str:
    # Import re locally to be safe
    import re
    # 1. Un-bold mathematical letters/digits
    text = from_bold_unicode(text)
    # 2. Convert to lowercase
    text = text.lower()
    # 3. Keep only alphanumeric characters
    text = re.sub(r'[^a-z0-9]', '', text)
    return text
