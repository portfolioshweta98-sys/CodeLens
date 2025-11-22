#!/usr/bin/env python3
"""
Test MongoDB connection and show connection status.
"""

import pymongo
import sys
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError


def test_mongodb_connection(connection_string: str = "mongodb://localhost:27017/"):
    """
    Test MongoDB connection and return status.
    
    Args:
        connection_string: MongoDB connection string
        
    Returns:
        Tuple of (success: bool, message: str, client or None)
    """
    try:
        print(f"Testing MongoDB connection to: {connection_string}")
        
        # Try to connect with a short timeout
        client = pymongo.MongoClient(connection_string, serverSelectionTimeoutMS=5000)
        
        # Test the connection
        client.admin.command('ping')
        
        # Get server info
        server_info = client.server_info()
        
        # Get database names
        db_names = client.list_database_names()
        
        print("✓ MongoDB connection successful!")
        print(f"  Server version: {server_info.get('version', 'unknown')}")
        print(f"  Available databases: {', '.join(db_names) if db_names else 'None'}")
        
        return True, "Connection successful", client
        
    except ServerSelectionTimeoutError as e:
        error_msg = f"✗ MongoDB connection failed: Server selection timeout"
        print(error_msg)
        print(f"  Details: {e}")
        print("\n  Troubleshooting:")
        print("  1. Make sure MongoDB is running:")
        print("     docker compose up -d")
        print("  2. Check if MongoDB is accessible on port 27017")
        return False, error_msg, None
        
    except ConnectionFailure as e:
        error_msg = f"✗ MongoDB connection failed: Connection failure"
        print(error_msg)
        print(f"  Details: {e}")
        return False, error_msg, None
        
    except Exception as e:
        error_msg = f"✗ MongoDB connection failed: {str(e)}"
        print(error_msg)
        return False, error_msg, None


def check_database_content(db_name: str = "codelens", client=None):
    """
    Check if database exists and show collection info.
    
    Args:
        db_name: Database name to check
        client: MongoDB client (if None, will create new connection)
    """
    if client is None:
        success, msg, client = test_mongodb_connection()
        if not success:
            return
    
    try:
        db = client[db_name]
        collections = db.list_collection_names()
        
        print(f"\n📊 Database '{db_name}':")
        if not collections:
            print("  No collections found")
        else:
            print(f"  Collections: {', '.join(collections)}")
            
            # Count documents in each collection
            for collection_name in collections:
                collection = db[collection_name]
                count = collection.count_documents({})
                print(f"    - {collection_name}: {count} documents")
        
    except Exception as e:
        print(f"  Error checking database: {e}")


def main():
    """Main function."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Test MongoDB connection')
    parser.add_argument('--connection-string', default='mongodb://localhost:27017/',
                       help='MongoDB connection string (default: mongodb://localhost:27017/)')
    parser.add_argument('--db-name', default='codelens',
                       help='Database name to check (default: codelens)')
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("MongoDB Connection Test")
    print("=" * 60)
    
    # Test connection
    success, msg, client = test_mongodb_connection(args.connection_string)
    
    if success:
        # Check database content
        check_database_content(args.db_name, client)
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()

