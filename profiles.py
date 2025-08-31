from __future__ import annotations

"""Profile management for channel configurations.

This module defines the ChannelProfile dataclass and a simple ProfileStore
for CRUD operations persisted to a JSON file.  JSON is used to avoid external
dependencies while still providing a human readable format that can be edited
manually if required.
"""

from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

import json


@dataclass
class ChannelProfile:
    """Configuration for processing a set of channels.

    Attributes:
        id: Unique identifier for the profile.
        name: Human readable name.
        parse_options: Options controlling how messages are parsed.
        member_channels: List of channel identifiers this profile reads from.
        templates: Mapping of source channel identifiers to template file names
            or raw Jinja2 template strings.
        destinations: List of destinations where parsed messages are sent.
        routes: Optional mapping of ``"SYMBOL:POSITION"`` keys to destination
            channel lists.  When provided, these override ``destinations`` for
        matching signals.
    """

    id: str
    name: str
    parse_options: Dict[str, Any]
    member_channels: List[str]
    templates: Dict[str, str]
    destinations: List[str]
    routes: Optional[Dict[str, List[str]]] = None


class ProfileStore:
    """Persist ChannelProfile objects to a JSON file."""

    def __init__(self, path: Path | str):
        self.path = Path(path)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _load_raw(self) -> Dict[str, Dict[str, Any]]:
        if not self.path.exists():
            return {}
        text = self.path.read_text() or ""
        if not text.strip():
            return {}
        return json.loads(text)

    def _dump_raw(self, data: Dict[str, Dict[str, Any]]) -> None:
        self.path.write_text(json.dumps(data, indent=2, sort_keys=True))

    # ------------------------------------------------------------------
    # CRUD API
    # ------------------------------------------------------------------
    def list_profiles(self) -> Dict[str, ChannelProfile]:
        return {pid: ChannelProfile(**pdata) for pid, pdata in self._load_raw().items()}

    def get_profile(self, profile_id: str) -> Optional[ChannelProfile]:
        return self.list_profiles().get(profile_id)

    def create_profile(self, profile: ChannelProfile) -> None:
        profiles = self._load_raw()
        if profile.id in profiles:
            raise ValueError(f"Profile {profile.id} already exists")
        profiles[profile.id] = asdict(profile)
        self._dump_raw(profiles)

    def update_profile(self, profile_id: str, **updates: Any) -> ChannelProfile:
        profiles = self._load_raw()
        if profile_id not in profiles:
            raise KeyError(profile_id)
        profile_data = profiles[profile_id]
        profile_data.update(updates)
        profiles[profile_id] = profile_data
        self._dump_raw(profiles)
        return ChannelProfile(**profile_data)

    def delete_profile(self, profile_id: str) -> bool:
        profiles = self._load_raw()
        if profile_id in profiles:
            del profiles[profile_id]
            self._dump_raw(profiles)
            return True
        return False
