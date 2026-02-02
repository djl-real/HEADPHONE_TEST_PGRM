# usage_tracker.py
"""
Tracks module usage statistics and favorites for quick access functionality.
Persists data to a JSON file for cross-session persistence.
"""

import json
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional
import os


@dataclass
class ModuleUsageData:
    """Usage statistics for a single module."""
    name: str
    spawn_count: int = 0
    last_used: Optional[str] = None  # ISO format datetime
    is_favorite: bool = False
    
    def record_use(self):
        """Record a module usage."""
        self.spawn_count += 1
        self.last_used = datetime.now().isoformat()


class UsageTracker:
    """
    Tracks and persists module usage data.
    
    Features:
    - Tracks spawn counts per module
    - Tracks last used timestamp
    - Supports favorites/pinning
    - Persists to JSON file
    - Provides sorted quick access list
    """
    
    DEFAULT_CONFIG_DIR = ".config/audio_modules"
    DEFAULT_FILENAME = "module_usage.json"
    MAX_QUICK_ACCESS = 8
    
    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize the usage tracker.
        
        Args:
            config_path: Optional custom path for the config file.
                        If None, uses ~/.config/audio_modules/module_usage.json
        """
        if config_path:
            self.config_path = Path(config_path)
        else:
            home = Path.home()
            self.config_path = home / self.DEFAULT_CONFIG_DIR / self.DEFAULT_FILENAME
            
        self.usage_data: Dict[str, ModuleUsageData] = {}
        self._load()
    
    def _ensure_config_dir(self):
        """Ensure the config directory exists."""
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
    
    def _load(self):
        """Load usage data from disk."""
        if not self.config_path.exists():
            return
            
        try:
            with open(self.config_path, 'r') as f:
                data = json.load(f)
                
            for name, info in data.get('modules', {}).items():
                self.usage_data[name] = ModuleUsageData(
                    name=name,
                    spawn_count=info.get('spawn_count', 0),
                    last_used=info.get('last_used'),
                    is_favorite=info.get('is_favorite', False)
                )
        except (json.JSONDecodeError, IOError) as e:
            print(f"Warning: Could not load usage data: {e}")
    
    def _save(self):
        """Save usage data to disk."""
        try:
            self._ensure_config_dir()
            
            data = {
                'version': 1,
                'modules': {
                    name: asdict(info) 
                    for name, info in self.usage_data.items()
                }
            }
            
            with open(self.config_path, 'w') as f:
                json.dump(data, f, indent=2)
        except IOError as e:
            print(f"Warning: Could not save usage data: {e}")
    
    def record_spawn(self, module_name: str):
        """
        Record that a module was spawned.
        
        Args:
            module_name: The display name of the module
        """
        if module_name not in self.usage_data:
            self.usage_data[module_name] = ModuleUsageData(name=module_name)
            
        self.usage_data[module_name].record_use()
        self._save()
    
    def toggle_favorite(self, module_name: str) -> bool:
        """
        Toggle favorite status for a module.
        
        Args:
            module_name: The display name of the module
            
        Returns:
            New favorite status
        """
        if module_name not in self.usage_data:
            self.usage_data[module_name] = ModuleUsageData(name=module_name)
            
        self.usage_data[module_name].is_favorite = not self.usage_data[module_name].is_favorite
        self._save()
        
        return self.usage_data[module_name].is_favorite
    
    def set_favorite(self, module_name: str, is_favorite: bool):
        """
        Set favorite status for a module.
        
        Args:
            module_name: The display name of the module
            is_favorite: Whether to favorite or unfavorite
        """
        if module_name not in self.usage_data:
            self.usage_data[module_name] = ModuleUsageData(name=module_name)
            
        self.usage_data[module_name].is_favorite = is_favorite
        self._save()
    
    def is_favorite(self, module_name: str) -> bool:
        """Check if a module is favorited."""
        if module_name in self.usage_data:
            return self.usage_data[module_name].is_favorite
        return False
    
    def get_spawn_count(self, module_name: str) -> int:
        """Get the spawn count for a module."""
        if module_name in self.usage_data:
            return self.usage_data[module_name].spawn_count
        return 0
    
    def get_favorites(self) -> List[str]:
        """Get list of favorited module names."""
        return [
            name for name, data in self.usage_data.items()
            if data.is_favorite
        ]
    
    def get_quick_access_modules(self, max_count: int = None) -> List[str]:
        """
        Get the list of modules for quick access bar.
        
        Prioritizes:
        1. Favorited modules (sorted by usage)
        2. Most frequently used non-favorites
        
        Args:
            max_count: Maximum number of modules to return
            
        Returns:
            List of module names for quick access
        """
        if max_count is None:
            max_count = self.MAX_QUICK_ACCESS
            
        # Separate favorites and non-favorites
        favorites = []
        non_favorites = []
        
        for name, data in self.usage_data.items():
            if data.spawn_count > 0 or data.is_favorite:
                if data.is_favorite:
                    favorites.append((name, data.spawn_count))
                else:
                    non_favorites.append((name, data.spawn_count))
        
        # Sort each group by spawn count (descending)
        favorites.sort(key=lambda x: x[1], reverse=True)
        non_favorites.sort(key=lambda x: x[1], reverse=True)
        
        # Combine: favorites first, then fill with most used
        result = [name for name, _ in favorites]
        
        for name, _ in non_favorites:
            if len(result) >= max_count:
                break
            result.append(name)
            
        return result[:max_count]
    
    def get_recently_used(self, max_count: int = 10) -> List[str]:
        """
        Get list of recently used modules.
        
        Args:
            max_count: Maximum number to return
            
        Returns:
            List of module names sorted by last used time
        """
        with_timestamps = [
            (name, data.last_used)
            for name, data in self.usage_data.items()
            if data.last_used is not None
        ]
        
        with_timestamps.sort(key=lambda x: x[1], reverse=True)
        
        return [name for name, _ in with_timestamps[:max_count]]
    
    def clear_usage_data(self):
        """Clear all usage data (but keep favorites)."""
        for data in self.usage_data.values():
            data.spawn_count = 0
            data.last_used = None
        self._save()
    
    def clear_all(self):
        """Clear all data including favorites."""
        self.usage_data.clear()
        self._save()