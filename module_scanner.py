# module_scanner.py
"""
Automatic module discovery system.
Scans the modules directory for AudioModule subclasses and organizes them by folder structure.
"""

import os
import sys
import importlib
import importlib.util
from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict, List, Type, Optional, Any


@dataclass
class ModuleInfo:
    """Metadata about a discovered module."""
    name: str                    # Display name (class name or formatted)
    class_ref: Type             # The actual class reference
    category: str               # Category path (e.g., "Effects" or "Effects/Spatial")
    file_path: Path             # Path to the source file
    module_path: str            # Python module path for import
    
    def spawn(self) -> Any:
        """Create a new instance of this module."""
        return self.class_ref()


@dataclass 
class CategoryNode:
    """A node in the category tree structure."""
    name: str
    modules: List[ModuleInfo] = field(default_factory=list)
    children: Dict[str, "CategoryNode"] = field(default_factory=dict)
    
    def get_all_modules(self) -> List[ModuleInfo]:
        """Get all modules in this category and subcategories."""
        result = list(self.modules)
        for child in self.children.values():
            result.extend(child.get_all_modules())
        return result


class ModuleScanner:
    """
    Scans and discovers AudioModule classes from the modules directory.
    
    Features:
    - Automatic recursive scanning
    - Skips hidden directories (starting with .)
    - Uses folder structure for categorization
    - Caches discovered modules
    """
    
    def __init__(self, modules_dir: str = "modules"):
        self.modules_dir = Path(modules_dir)
        self.modules: Dict[str, ModuleInfo] = {}  # name -> ModuleInfo
        self.category_tree = CategoryNode("Root")
        self._scanned = False
        
    def scan(self, force: bool = False) -> Dict[str, ModuleInfo]:
        """
        Scan the modules directory and discover all modules.
        
        Args:
            force: If True, rescan even if already scanned
            
        Returns:
            Dictionary mapping module names to ModuleInfo objects
        """
        if self._scanned and not force:
            return self.modules
            
        self.modules.clear()
        self.category_tree = CategoryNode("Root")
        
        if not self.modules_dir.exists():
            print(f"Warning: Modules directory '{self.modules_dir}' not found")
            return self.modules
            
        # Ensure modules dir is in path for imports
        modules_parent = str(self.modules_dir.parent.absolute())
        if modules_parent not in sys.path:
            sys.path.insert(0, modules_parent)
            
        self._scan_directory(self.modules_dir)
        self._scanned = True
        
        return self.modules
    
    def _scan_directory(self, directory: Path, category_parts: List[str] = None):
        """Recursively scan a directory for module files."""
        if category_parts is None:
            category_parts = []
            
        try:
            entries = sorted(directory.iterdir())
        except PermissionError:
            return
            
        for entry in entries:
            # Skip hidden files and directories
            if entry.name.startswith('.'):
                continue
                
            # Skip __pycache__ and similar
            if entry.name.startswith('__'):
                continue
                
            if entry.is_dir():
                # Recurse into subdirectory with updated category
                new_category = category_parts + [self._format_category_name(entry.name)]
                self._scan_directory(entry, new_category)
                
            elif entry.suffix == '.py':
                self._try_load_module(entry, category_parts)
    
    def _format_category_name(self, folder_name: str) -> str:
        """Convert folder name to display category name."""
        # Convert snake_case or kebab-case to Title Case
        name = folder_name.replace('_', ' ').replace('-', ' ')
        return name.title()
    
    def _format_module_name(self, class_name: str) -> str:
        """Convert class name to display name."""
        # Add spaces before capitals (CamelCase -> Camel Case)
        result = []
        for i, char in enumerate(class_name):
            if i > 0 and char.isupper() and class_name[i-1].islower():
                result.append(' ')
            result.append(char)
        return ''.join(result)
    
    def _try_load_module(self, file_path: Path, category_parts: List[str]):
        """Attempt to load a Python file and find AudioModule subclasses."""
        try:
            # Build module path relative to modules directory
            rel_path = file_path.relative_to(self.modules_dir.parent)
            module_path = str(rel_path.with_suffix('')).replace(os.sep, '.')
            
            # Load the module spec
            spec = importlib.util.spec_from_file_location(module_path, file_path)
            if spec is None or spec.loader is None:
                return
                
            module = importlib.util.module_from_spec(spec)
            
            # Execute the module to populate it
            try:
                spec.loader.exec_module(module)
            except Exception as e:
                # Module failed to load - skip it silently in production
                # print(f"Warning: Could not load {file_path}: {e}")
                return
            
            # Find all classes that look like audio modules
            for attr_name in dir(module):
                if attr_name.startswith('_'):
                    continue
                    
                attr = getattr(module, attr_name)
                
                # Check if it's a class defined in this module
                if not isinstance(attr, type):
                    continue
                    
                # Skip if not defined in this file
                if getattr(attr, '__module__', None) != module.__name__:
                    continue
                
                # Check if it looks like an AudioModule
                if self._is_audio_module(attr):
                    self._register_module(attr, attr_name, file_path, module_path, category_parts)
                    
        except Exception as e:
            # Silently skip problematic files in production
            # print(f"Warning: Error scanning {file_path}: {e}")
            pass
    
    def _is_audio_module(self, cls: type) -> bool:
        """Check if a class appears to be an AudioModule."""
        # Check for AudioModule base class by name (avoid import dependency)
        for base in cls.__mro__:
            if base.__name__ == 'AudioModule':
                return True
        
        # Fallback: check for characteristic attributes
        has_inputs = hasattr(cls, 'input_nodes') or 'input_nodes' in getattr(cls, '__init__', lambda: None).__code__.co_varnames if hasattr(cls, '__init__') else False
        has_outputs = hasattr(cls, 'output_nodes') or 'output_nodes' in getattr(cls, '__init__', lambda: None).__code__.co_varnames if hasattr(cls, '__init__') else False
        
        # Check if init creates input_nodes or output_nodes
        try:
            init_code = cls.__init__.__code__
            init_source = init_code.co_varnames
            # This is a heuristic - not perfect but catches most cases
        except:
            pass
            
        return False
    
    def _register_module(self, cls: type, class_name: str, file_path: Path, 
                         module_path: str, category_parts: List[str]):
        """Register a discovered module."""
        display_name = self._format_module_name(class_name)
        category = "/".join(category_parts) if category_parts else "Other"
        
        info = ModuleInfo(
            name=display_name,
            class_ref=cls,
            category=category,
            file_path=file_path,
            module_path=module_path
        )
        
        # Store in flat dict
        self.modules[display_name] = info
        
        # Add to category tree
        self._add_to_category_tree(info, category_parts or ["Other"])
    
    def _add_to_category_tree(self, info: ModuleInfo, category_parts: List[str]):
        """Add a module to the category tree structure."""
        node = self.category_tree
        
        for part in category_parts:
            if part not in node.children:
                node.children[part] = CategoryNode(part)
            node = node.children[part]
            
        node.modules.append(info)
    
    def get_categories(self) -> List[str]:
        """Get list of all top-level categories."""
        return sorted(self.category_tree.children.keys())
    
    def get_modules_in_category(self, category: str) -> List[ModuleInfo]:
        """Get all modules in a category (including subcategories)."""
        parts = category.split("/")
        node = self.category_tree
        
        for part in parts:
            if part in node.children:
                node = node.children[part]
            else:
                return []
                
        return node.get_all_modules()
    
    def search(self, query: str) -> List[ModuleInfo]:
        """Search modules by name (case-insensitive)."""
        query_lower = query.lower()
        results = []
        
        for name, info in self.modules.items():
            if query_lower in name.lower():
                results.append(info)
                
        return sorted(results, key=lambda m: m.name)
    
    def get_module(self, name: str) -> Optional[ModuleInfo]:
        """Get a specific module by display name."""
        return self.modules.get(name)


# Fallback: Manual module registry for when auto-discovery isn't working
class ManualModuleRegistry:
    """
    Fallback registry that uses explicit imports.
    Use this when auto-discovery fails or for guaranteed module availability.
    """
    
    def __init__(self):
        self.modules: Dict[str, ModuleInfo] = {}
        self.category_tree = CategoryNode("Root")
        self._categories: Dict[str, List[tuple]] = {}
        
    def register(self, name: str, cls: type, category: str = "Other"):
        """Manually register a module."""
        info = ModuleInfo(
            name=name,
            class_ref=cls,
            category=category,
            file_path=Path(""),
            module_path=""
        )
        
        self.modules[name] = info
        
        # Add to category tree
        parts = category.split("/")
        self._add_to_category_tree(info, parts)
        
    def _add_to_category_tree(self, info: ModuleInfo, category_parts: List[str]):
        """Add a module to the category tree structure."""
        node = self.category_tree
        
        for part in category_parts:
            if part not in node.children:
                node.children[part] = CategoryNode(part)
            node = node.children[part]
            
        node.modules.append(info)
    
    def register_from_dict(self, module_folders: Dict[str, List[tuple]]):
        """
        Register modules from a dictionary in the old toolbar format.
        
        Args:
            module_folders: Dict mapping category names to list of (name, class) tuples
        """
        for category, modules in module_folders.items():
            for name, cls in modules:
                self.register(name, cls, category)
                
    def get_categories(self) -> List[str]:
        """Get list of all top-level categories."""
        return sorted(self.category_tree.children.keys())
    
    def get_modules_in_category(self, category: str) -> List[ModuleInfo]:
        """Get all modules in a category."""
        parts = category.split("/")
        node = self.category_tree
        
        for part in parts:
            if part in node.children:
                node = node.children[part]
            else:
                return []
                
        return sorted(node.get_all_modules(), key=lambda m: m.name)
    
    def search(self, query: str) -> List[ModuleInfo]:
        """Search modules by name."""
        query_lower = query.lower()
        results = []
        
        for name, info in self.modules.items():
            if query_lower in name.lower():
                results.append(info)
                
        return sorted(results, key=lambda m: m.name)
    
    def get_module(self, name: str) -> Optional[ModuleInfo]:
        """Get a specific module by name."""
        return self.modules.get(name)