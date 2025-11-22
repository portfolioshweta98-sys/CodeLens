#!/usr/bin/env python3
"""
Step 2: AST Parser
Clones a repository, parses Python files, and stores AST information in MongoDB.
"""

import ast
import os
import sys
from pathlib import Path
from typing import List, Dict, Any
import pymongo
from git import Repo
from git.exc import GitCommandError


def clone_repository(repo_url: str, target_dir: str) -> str:
    """
    Clone a repository using GitPython.
    
    Args:
        repo_url: URL of the repository to clone
        target_dir: Directory to clone into
        
    Returns:
        Path to the cloned repository
    """
    repo_path = os.path.join(target_dir, os.path.basename(repo_url).replace('.git', ''))
    
    # Remove directory if it already exists
    if os.path.exists(repo_path):
        print(f"Directory {repo_path} already exists. Removing...")
        import shutil
        shutil.rmtree(repo_path)
    
    try:
        print(f"Cloning {repo_url} to {repo_path}...")
        Repo.clone_from(repo_url, repo_path)
        print(f"Successfully cloned to {repo_path}")
        return repo_path
    except GitCommandError as e:
        print(f"Error cloning repository: {e}")
        sys.exit(1)


def find_python_files(directory: str) -> List[str]:
    """
    Walk directory and collect all .py files.
    
    Args:
        directory: Root directory to search
        
    Returns:
        List of paths to Python files
    """
    python_files = []
    for root, dirs, files in os.walk(directory):
        # Skip common directories that shouldn't be parsed
        dirs[:] = [d for d in dirs if d not in ['.git', '__pycache__', '.venv', 'venv', 'node_modules']]
        
        for file in files:
            if file.endswith('.py'):
                python_files.append(os.path.join(root, file))
    
    return python_files


def parse_ast_file(file_path: str) -> Dict[str, Any]:
    """
    Parse a Python file and extract AST information.
    
    Args:
        file_path: Path to the Python file
        
    Returns:
        Dictionary containing filename, functions, classes, imports, and raw_code
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            raw_code = f.read()
    except Exception as e:
        print(f"Error reading file {file_path}: {e}")
        return None
    
    try:
        tree = ast.parse(raw_code)
    except SyntaxError as e:
        print(f"Syntax error in {file_path}: {e}")
        return None
    
    # Extract functions
    functions = [n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]
    
    # Extract classes
    classes = [n.name for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]
    
    # Extract imports
    imports = []
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            # Handle multiple names in one import statement
            imports.extend([alias.name for alias in n.names])
        elif isinstance(n, ast.ImportFrom):
            # Handle "from X import Y" statements
            if n.module:
                imports.extend([f"{n.module}.{alias.name}" for alias in n.names])
    
    # Get relative filename from the repo root
    filename = os.path.basename(file_path)
    
    return {
        "filename": filename,
        "filepath": file_path,
        "functions": functions,
        "classes": classes,
        "imports": imports,
        "raw_code": raw_code
    }


def store_in_mongodb(data: Dict[str, Any], db_name: str = "codelens", collection_name: str = "ast_data"):
    """
    Store parsed AST data in MongoDB.
    
    Args:
        data: Dictionary containing AST information
        db_name: Name of the MongoDB database
        collection_name: Name of the MongoDB collection
    """
    try:
        # Connect to MongoDB (assuming local replica set)
        client = pymongo.MongoClient("mongodb://localhost:27017/")
        db = client[db_name]
        collection = db[collection_name]
        
        # Insert document
        result = collection.insert_one(data)
        print(f"Stored {data['filename']} (ID: {result.inserted_id})")
        
    except Exception as e:
        print(f"Error storing in MongoDB: {e}")
        raise


def main():
    """Main function to run the AST parser."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Parse AST from a Git repository')
    parser.add_argument('repo_url', help='URL of the repository to clone')
    parser.add_argument('--target-dir', default='./repos', help='Directory to clone repositories into (default: ./repos)')
    parser.add_argument('--db-name', default='codelens', help='MongoDB database name (default: codelens)')
    parser.add_argument('--collection', default='ast_data', help='MongoDB collection name (default: ast_data)')
    
    args = parser.parse_args()
    
    # Create target directory if it doesn't exist
    os.makedirs(args.target_dir, exist_ok=True)
    
    # Clone repository
    repo_path = clone_repository(args.repo_url, args.target_dir)
    
    # Find all Python files
    print("\nSearching for Python files...")
    python_files = find_python_files(repo_path)
    print(f"Found {len(python_files)} Python files")
    
    # Parse each file and store in MongoDB
    print("\nParsing files and storing in MongoDB...")
    successful = 0
    failed = 0
    
    for py_file in python_files:
        ast_data = parse_ast_file(py_file)
        if ast_data:
            try:
                # Update filepath to be relative to repo root
                ast_data['filepath'] = os.path.relpath(py_file, repo_path)
                store_in_mongodb(ast_data, args.db_name, args.collection)
                successful += 1
            except Exception as e:
                print(f"Failed to store {py_file}: {e}")
                failed += 1
        else:
            failed += 1
    
    print(f"\nCompleted: {successful} files processed, {failed} files failed")


if __name__ == "__main__":
    main()

