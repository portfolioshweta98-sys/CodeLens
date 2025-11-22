#!/usr/bin/env python3
"""
Step 5: Brave Metadata
Parses requirements.txt and queries Brave Search API for each library's information.
"""

import os
import sys
import re
import time
from typing import List, Dict, Any, Optional
import requests
import pymongo
from pymongo.errors import PyMongoError


def parse_requirements_txt(requirements_path: str) -> List[str]:
    """
    Parse requirements.txt and extract library names.
    
    Args:
        requirements_path: Path to requirements.txt file
        
    Returns:
        List of library names (without version specifiers)
    """
    libraries = []
    
    if not os.path.exists(requirements_path):
        print(f"Warning: requirements.txt not found at {requirements_path}")
        return libraries
    
    try:
        with open(requirements_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                
                # Skip empty lines and comments
                if not line or line.startswith('#'):
                    continue
                
                # Remove inline comments
                if '#' in line:
                    line = line.split('#')[0].strip()
                
                # Handle various requirement formats:
                # package==1.0.0
                # package>=1.0.0
                # package~=1.0.0
                # package
                # git+https://...
                # -e .
                
                # Skip editable installs and git URLs
                if line.startswith('-e') or line.startswith('git+') or line.startswith('http'):
                    continue
                
                # Extract package name (before any version specifiers)
                # Common separators: ==, >=, <=, >, <, ~=, !=
                package_name = re.split(r'[><=!~]+', line)[0].strip()
                
                # Clean up package name (remove whitespace)
                package_name = package_name.strip()
                
                if package_name:
                    libraries.append(package_name.lower())
        
        # Remove duplicates while preserving order
        seen = set()
        unique_libraries = []
        for lib in libraries:
            if lib not in seen:
                seen.add(lib)
                unique_libraries.append(lib)
        
        return unique_libraries
        
    except Exception as e:
        print(f"Error parsing requirements.txt: {e}")
        return []


def query_brave_search(library_name: str, api_key: str) -> Dict[str, Any]:
    """
    Query Brave Search API for information about a Python library.
    
    Args:
        library_name: Name of the Python library
        api_key: Brave Search API key
        
    Returns:
        Dictionary with search results and metadata
    """
    query = f"What is python library {library_name}?"
    
    # Brave Search API endpoint (v1)
    url = "https://api.search.brave.com/res/v1/web/search"
    
    headers = {
        "Accept": "application/json",
        "Accept-Encoding": "gzip",
        "X-Subscription-Token": api_key
    }
    
    params = {
        "q": query,
        "count": 5,  # Number of results to return
        "search_lang": "en",
        "country": "US",
        "safesearch": "moderate"
    }
    
    try:
        response = requests.get(url, headers=headers, params=params, timeout=15)
        response.raise_for_status()
        
        data = response.json()
        
        # Extract relevant information
        web_results_list = data.get("web", {}).get("results", [])
        results = {
            "library_name": library_name,
            "query": query,
            "results_count": len(web_results_list),
            "web_results": [],
            "timestamp": time.time()
        }
        
        # Parse web results
        for result in web_results_list:
            results["web_results"].append({
                "title": result.get("title", ""),
                "url": result.get("url", ""),
                "description": result.get("description", ""),
                "age": result.get("age", "")
            })
        
        # Extract answer box if available
        answer_box = data.get("answers", {})
        if answer_box:
            results["answer_box"] = answer_box
        
        # Extract snippets if available
        snippets = data.get("web", {}).get("snippets", [])
        if snippets:
            results["snippets"] = snippets
        
        return results
        
    except requests.exceptions.HTTPError as e:
        error_msg = f"HTTP {e.response.status_code}: {e.response.text[:200]}"
        print(f"  ✗ HTTP error querying Brave Search for {library_name}: {error_msg}")
        return {
            "library_name": library_name,
            "query": query,
            "error": error_msg,
            "http_status": e.response.status_code,
            "results_count": 0,
            "web_results": [],
            "timestamp": time.time()
        }
    except requests.exceptions.RequestException as e:
        error_msg = str(e)
        print(f"  ✗ Request error querying Brave Search for {library_name}: {error_msg}")
        return {
            "library_name": library_name,
            "query": query,
            "error": error_msg,
            "results_count": 0,
            "web_results": [],
            "timestamp": time.time()
        }
    except Exception as e:
        error_msg = str(e)
        print(f"  ✗ Unexpected error querying Brave Search for {library_name}: {error_msg}")
        return {
            "library_name": library_name,
            "query": query,
            "error": error_msg,
            "results_count": 0,
            "web_results": [],
            "timestamp": time.time()
        }


def store_library_metadata(library_data: Dict[str, Any], db_name: str = "codelens", collection_name: str = "libraries"):
    """
    Store library metadata in MongoDB.
    
    Args:
        library_data: Dictionary containing library search results
        db_name: MongoDB database name
        collection_name: MongoDB collection name
    """
    try:
        client = pymongo.MongoClient("mongodb://localhost:27017/")
        db = client[db_name]
        collection = db[collection_name]
        
        # Use upsert to update if exists, insert if new
        result = collection.update_one(
            {"library_name": library_data["library_name"]},
            {
                "$set": library_data,
                "$setOnInsert": {"created_at": time.time()}
            },
            upsert=True
        )
        
        if result.upserted_id:
            print(f"  ✓ Inserted {library_data['library_name']}")
        else:
            print(f"  ✓ Updated {library_data['library_name']}")
            
    except PyMongoError as e:
        print(f"  ✗ Error storing {library_data.get('library_name', 'unknown')}: {e}")
        raise
    except Exception as e:
        print(f"  ✗ Unexpected error storing {library_data.get('library_name', 'unknown')}: {e}")
        raise


def process_requirements_file(
    requirements_path: str,
    api_key: Optional[str] = None,
    db_name: str = "codelens",
    collection_name: str = "libraries",
    skip_existing: bool = True
):
    """
    Process requirements.txt, query Brave Search for each library, and store results.
    
    Args:
        requirements_path: Path to requirements.txt file
        api_key: Brave Search API key (if None, will try to get from environment)
        db_name: MongoDB database name
        collection_name: MongoDB collection name
        skip_existing: If True, skip libraries that already exist in MongoDB
    """
    # Get API key from environment or parameter
    if not api_key:
        api_key = os.getenv('BRAVE_API_KEY') or os.getenv('BRAVE_SEARCH_API_KEY')
    
    if not api_key:
        print("Error: BRAVE_API_KEY or BRAVE_SEARCH_API_KEY environment variable not set.")
        print("Please set it: export BRAVE_API_KEY='your_api_key'")
        print("Get your API key from: https://brave.com/search/api/")
        sys.exit(1)
    
    # Parse requirements.txt
    print(f"Parsing {requirements_path}...")
    libraries = parse_requirements_txt(requirements_path)
    
    if not libraries:
        print("No libraries found in requirements.txt")
        return
    
    print(f"Found {len(libraries)} unique libraries")
    print(f"Libraries: {', '.join(libraries[:10])}" + ("..." if len(libraries) > 10 else ""))
    
    # Check existing libraries in MongoDB if skip_existing is True
    existing_libraries = set()
    if skip_existing:
        try:
            client = pymongo.MongoClient("mongodb://localhost:27017/")
            db = client[db_name]
            collection = db[collection_name]
            existing = collection.find({}, {"library_name": 1})
            existing_libraries = {doc["library_name"] for doc in existing}
            print(f"\nFound {len(existing_libraries)} existing libraries in MongoDB")
        except Exception as e:
            print(f"Warning: Could not check existing libraries: {e}")
    
    # Process each library
    print("\nQuerying Brave Search API...")
    successful = 0
    failed = 0
    skipped = 0
    
    for idx, library_name in enumerate(libraries, 1):
        # Skip if already exists
        if skip_existing and library_name in existing_libraries:
            print(f"[{idx}/{len(libraries)}] Skipping {library_name} (already exists)")
            skipped += 1
            continue
        
        print(f"[{idx}/{len(libraries)}] Querying {library_name}...")
        
        try:
            # Query Brave Search
            library_data = query_brave_search(library_name, api_key)
            
            # Store in MongoDB
            store_library_metadata(library_data, db_name, collection_name)
            successful += 1
            
            # Rate limiting - wait between requests to avoid hitting API limits
            time.sleep(1)  # Adjust based on API rate limits
            
        except Exception as e:
            print(f"  ✗ Error processing {library_name}: {e}")
            failed += 1
    
    print(f"\nCompleted:")
    print(f"  Successful: {successful}")
    print(f"  Failed: {failed}")
    print(f"  Skipped: {skipped}")
    print(f"  Total: {len(libraries)}")


def main():
    """Main function to run the Brave metadata collector."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Query Brave Search for Python library metadata')
    parser.add_argument('requirements_path', nargs='?', default='requirements.txt',
                       help='Path to requirements.txt file (default: requirements.txt)')
    parser.add_argument('--api-key', help='Brave Search API key (or set BRAVE_API_KEY env var)')
    parser.add_argument('--db-name', default='codelens', help='MongoDB database name (default: codelens)')
    parser.add_argument('--collection', default='libraries', help='MongoDB collection name (default: libraries)')
    parser.add_argument('--no-skip-existing', action='store_true',
                       help='Re-query libraries that already exist in MongoDB')
    
    args = parser.parse_args()
    
    print("Starting Brave Metadata Collector...")
    print(f"Requirements file: {args.requirements_path}")
    print(f"Database: {args.db_name}")
    print(f"Collection: {args.collection}")
    
    # Check if requirements.txt exists
    if not os.path.exists(args.requirements_path):
        print(f"\nError: requirements.txt not found at {args.requirements_path}")
        print("Please provide the path to requirements.txt or run from repository root")
        sys.exit(1)
    
    process_requirements_file(
        requirements_path=args.requirements_path,
        api_key=args.api_key,
        db_name=args.db_name,
        collection_name=args.collection,
        skip_existing=not args.no_skip_existing
    )


if __name__ == "__main__":
    main()

