#!/usr/bin/env python3
"""
Step 3: Graph Construction
Builds import relationships between files and bulk inserts edges into MongoDB.
"""

import os
import sys
from typing import List, Dict, Set, Tuple
from pathlib import Path
import pymongo
from pymongo.errors import BulkWriteError


def resolve_import_to_file(import_name: str, current_file_path: str, repo_path: str, all_files: Set[str]) -> str:
    """
    Resolve an import statement to an actual file path.
    
    Args:
        import_name: The import name (e.g., "utils", "src.auth", ".utils")
        current_file_path: Path of the file making the import (relative to repo root)
        repo_path: Absolute path to the repository root
        all_files: Set of all Python file paths (relative to repo root) for lookup
        
    Returns:
        Resolved file path relative to repo root, or None if not found
    """
    # Handle relative imports (e.g., ".utils", "..parent")
    if import_name.startswith('.'):
        # Relative import
        current_dir = os.path.dirname(current_file_path) if current_file_path else ""
        parts = import_name.split('.')
        
        # Count leading dots for relative level
        dot_count = 0
        for part in parts:
            if not part:
                dot_count += 1
            else:
                break
        
        module_name = parts[-1] if parts[-1] else parts[-2] if len(parts) > 1 else ""
        
        # Navigate up directories
        dir_parts = current_dir.split(os.sep) if current_dir else []
        if dot_count > len(dir_parts):
            return None
        
        target_dir_parts = dir_parts[:-(dot_count-1)] if dot_count > 1 else dir_parts
        
        # Try to find the file
        possible_rel_paths = [
            os.path.join(*target_dir_parts, f"{module_name}.py") if target_dir_parts else f"{module_name}.py",
            os.path.join(*target_dir_parts, module_name, "__init__.py") if target_dir_parts else os.path.join(module_name, "__init__.py"),
        ]
        
        for rel_path in possible_rel_paths:
            if rel_path in all_files:
                return rel_path
    else:
        # Absolute import
        parts = import_name.split('.')
        
        # Try exact match first (e.g., "src.auth" -> "src/auth.py")
        dotted_path = import_name.replace('.', os.sep)
        possible_rel_paths = [
            f"{dotted_path}.py",
            os.path.join(dotted_path, "__init__.py"),
        ]
        
        for rel_path in possible_rel_paths:
            if rel_path in all_files:
                return rel_path
        
        # Try module name only (e.g., "utils" -> "utils.py")
        module_name = parts[0]
        for file_path in all_files:
            filename = os.path.basename(file_path)
            if filename == f"{module_name}.py" or os.path.splitext(filename)[0] == module_name:
                return file_path
        
        # Try last part of import (e.g., "src.auth" -> find "auth.py")
        if len(parts) > 1:
            last_part = parts[-1]
            for file_path in all_files:
                filename = os.path.basename(file_path)
                if filename == f"{last_part}.py" or os.path.splitext(filename)[0] == last_part:
                    return file_path
        
        # Try matching path components (e.g., "src.auth" -> "src/auth.py")
        if len(parts) > 1:
            for file_path in all_files:
                # Normalize paths for comparison
                normalized_import = os.sep.join(parts)
                normalized_file = os.path.splitext(file_path)[0].replace(os.sep, os.sep)
                
                if normalized_file.endswith(normalized_import) or normalized_import in normalized_file:
                    return file_path
    
    return None


def build_graph_edges(ast_data_list: List[Dict], repo_path: str) -> List[Dict]:
    """
    Build graph edges from AST data.
    
    Args:
        ast_data_list: List of AST documents from MongoDB
        repo_path: Absolute path to the repository root
        
    Returns:
        List of edge documents: [{"source": "file1.py", "target": "file2.py"}, ...]
    """
    edges = []
    seen_edges = set()  # To avoid duplicates
    
    # Create a set of all file paths for fast lookup
    all_files = set()
    for doc in ast_data_list:
        filepath = doc.get('filepath', doc.get('filename', ''))
        if filepath:
            all_files.add(filepath)
    
    # Standard library modules to skip
    stdlib_modules = {
        'sys', 'os', 'json', 'datetime', 'collections', 'itertools', 'functools',
        'typing', 'abc', 'pathlib', 'hashlib', 'uuid', 'random', 'math',
        're', 'string', 'io', 'pickle', 'copy', 'enum', 'dataclasses'
    }
    
    # Third-party modules to skip (common ones)
    third_party_modules = {
        'numpy', 'pandas', 'requests', 'flask', 'django', 'pymongo', 'sqlalchemy',
        'pytest', 'unittest', 'setuptools', 'wheel', 'pip', 'conda'
    }
    
    for doc in ast_data_list:
        source_file = doc.get('filepath', doc.get('filename', ''))
        imports = doc.get('imports', [])
        
        if not source_file:
            continue
        
        for import_name in imports:
            # Skip standard library and third-party imports
            module_base = import_name.split('.')[0]
            if module_base in stdlib_modules or module_base in third_party_modules:
                continue
            
            # Try to resolve import to a file
            target_file = resolve_import_to_file(import_name, source_file, repo_path, all_files)
            
            if target_file and target_file != source_file:
                # Extract just the filename (basename) for edge representation
                source_filename = os.path.basename(source_file)
                target_filename = os.path.basename(target_file)
                
                # Create edge
                edge_key = (source_filename, target_filename)
                if edge_key not in seen_edges:
                    edges.append({
                        "source": source_filename,
                        "target": target_filename
                    })
                    seen_edges.add(edge_key)
    
    return edges


def bulk_insert_edges(edges: List[Dict], db_name: str = "codelens", collection_name: str = "edges"):
    """
    Bulk insert edges into MongoDB.
    
    Args:
        edges: List of edge documents to insert
        db_name: Name of the MongoDB database
        collection_name: Name of the MongoDB collection
    """
    if not edges:
        print("No edges to insert.")
        return
    
    try:
        client = pymongo.MongoClient("mongodb://localhost:27017/")
        db = client[db_name]
        collection = db[collection_name]
        
        # Clear existing edges (optional - comment out if you want to keep old data)
        result = collection.delete_many({})
        print(f"Cleared {result.deleted_count} existing edges")
        
        # Bulk insert
        result = collection.insert_many(edges)
        print(f"Successfully inserted {len(result.inserted_ids)} edges")
        
    except BulkWriteError as e:
        print(f"Bulk write error: {e.details}")
        raise
    except Exception as e:
        print(f"Error inserting edges: {e}")
        raise


def main():
    """Main function to construct the graph."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Build import graph from AST data')
    parser.add_argument('--repo-path', required=True, help='Path to the repository root')
    parser.add_argument('--db-name', default='codelens', help='MongoDB database name (default: codelens)')
    parser.add_argument('--ast-collection', default='ast_data', help='MongoDB collection name for AST data (default: ast_data)')
    parser.add_argument('--edges-collection', default='edges', help='MongoDB collection name for edges (default: edges)')
    
    args = parser.parse_args()
    
    # Validate repo path
    repo_path = os.path.abspath(args.repo_path)
    if not os.path.exists(repo_path):
        print(f"Error: Repository path does not exist: {repo_path}")
        sys.exit(1)
    
    # Fetch AST data from MongoDB
    print("Fetching AST data from MongoDB...")
    try:
        client = pymongo.MongoClient("mongodb://localhost:27017/")
        db = client[args.db_name]
        ast_collection = db[args.ast_collection]
        
        ast_data_list = list(ast_collection.find({}))
        print(f"Found {len(ast_data_list)} files in AST data")
        
        if not ast_data_list:
            print("No AST data found. Please run ast_parser.py first.")
            sys.exit(1)
            
    except Exception as e:
        print(f"Error fetching AST data: {e}")
        sys.exit(1)
    
    # Build graph edges
    print("\nBuilding graph edges...")
    edges = build_graph_edges(ast_data_list, repo_path)
    print(f"Generated {len(edges)} edges")
    
    # Display some sample edges
    if edges:
        print("\nSample edges:")
        for edge in edges[:10]:
            print(f"  {edge['source']} → {edge['target']}")
        if len(edges) > 10:
            print(f"  ... and {len(edges) - 10} more")
    
    # Bulk insert edges
    print("\nInserting edges into MongoDB...")
    bulk_insert_edges(edges, args.db_name, args.edges_collection)
    
    print("\nGraph construction completed!")


if __name__ == "__main__":
    main()

