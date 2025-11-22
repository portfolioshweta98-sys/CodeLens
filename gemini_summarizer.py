#!/usr/bin/env python3
"""
Step 4: Gemini Summarizer Bot
Uses Google Gemini API to analyze code files and generate summaries, tags, and risk assessments.
"""

import os
import sys
import json
import time
from typing import Dict, Any, List, Optional
import pymongo
from pymongo.errors import PyMongoError

# Try importing google-genai - check if it's available
try:
    import google.generativeai as genai
except ImportError:
    try:
        from google.genai import Client as GenAIClient
        USE_CLIENT_API = True
    except ImportError:
        try:
            import google.genai as genai_module
            USE_CLIENT_API = True
            GenAIClient = genai_module.Client
        except ImportError:
            print("Error: google-genai package not found. Please install it: pip install google-genai")
            sys.exit(1)
    else:
        USE_CLIENT_API = True
else:
    USE_CLIENT_API = False


def generate_summary(code: str, api_key: str) -> Dict[str, Any]:
    """
    Generate summary, tags, and risks for code using Gemini API.
    
    Args:
        code: The source code to analyze
        api_key: Google Gemini API key
        
    Returns:
        Dictionary with 'summary', 'tags', and 'risks' keys
    """
    prompt = """
You are a senior software engineer.

Analyze the following Python code and provide:

1. A summary of this file in exactly 3 bullet points.

2. Identify if it handles: authentication, database, API, or configuration. 
   Provide relevant tags from: ["auth", "database", "api", "config", "utils", "model", "view", "service", "handler"]

3. List potential security risks (e.g., eval, SQL injection, hardcoded secrets, insecure random, missing input validation).

Return your response as valid JSON in this exact format:
{
  "summary": ["bullet point 1", "bullet point 2", "bullet point 3"],
  "tags": ["tag1", "tag2"],
  "risks": ["risk1", "risk2"]
}

Code:
""" + code

    try:
        if USE_CLIENT_API:
            # New google-genai Client API (google.genai package)
            try:
                client = GenAIClient(api_key=api_key)
                # Try different API patterns
                try:
                    response = client.models.generate_content(
                        model='models/gemini-pro',
                        contents=[{'role': 'user', 'parts': [{'text': prompt}]}]
                    )
                except Exception:
                    # Alternative API pattern
                    response = client.models.generate_content(
                        model='gemini-pro',
                        contents=prompt
                    )
                
                # Extract text from response
                if hasattr(response, 'text'):
                    response_text = response.text.strip()
                elif hasattr(response, 'candidates') and response.candidates:
                    response_text = response.candidates[0].content.parts[0].text.strip()
                elif hasattr(response, 'content'):
                    response_text = response.content.strip()
                else:
                    response_text = str(response).strip()
            except Exception as e:
                raise Exception(f"Client API error: {e}")
        else:
            # Standard google.generativeai API
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel('gemini-pro')
            response = model.generate_content(prompt)
            response_text = response.text.strip()
        
        # Clean up response text (remove markdown code blocks if present)
        if response_text.startswith('```json'):
            response_text = response_text[7:]
        if response_text.startswith('```'):
            response_text = response_text[3:]
        if response_text.endswith('```'):
            response_text = response_text[:-3]
        response_text = response_text.strip()
        
        # Parse JSON response
        try:
            result = json.loads(response_text)
        except json.JSONDecodeError:
            # If JSON parsing fails, try to extract JSON from the text
            start_idx = response_text.find('{')
            end_idx = response_text.rfind('}') + 1
            if start_idx >= 0 and end_idx > start_idx:
                result = json.loads(response_text[start_idx:end_idx])
            else:
                # Fallback: create a basic structure
                print(f"Warning: Failed to parse JSON. Response: {response_text[:200]}")
                result = {
                    "summary": ["Unable to parse summary"],
                    "tags": [],
                    "risks": []
                }
        
        # Validate structure
        if not isinstance(result, dict):
            result = {"summary": [], "tags": [], "risks": []}
        
        # Ensure required keys exist
        result.setdefault("summary", [])
        result.setdefault("tags", [])
        result.setdefault("risks", [])
        
        # Convert summary to string if it's a list
        if isinstance(result["summary"], list):
            result["summary"] = "\n".join([f"• {item}" for item in result["summary"]])
        
        return result
        
    except Exception as e:
        print(f"Error generating summary: {e}")
        # Return empty structure on error
        return {
            "summary": f"Error analyzing code: {str(e)}",
            "tags": [],
            "risks": []
        }


def update_files_with_summaries(
    db_name: str = "codelens",
    collection_name: str = "ast_data",
    api_key: Optional[str] = None,
    limit: Optional[int] = None
):
    """
    Loop through files collection and update each document with summary, tags, and risks.
    
    Args:
        db_name: MongoDB database name
        collection_name: Collection name containing file data
        api_key: Google Gemini API key (if None, will try to get from environment)
        limit: Optional limit on number of files to process (for testing)
    """
    # Get API key from environment or parameter
    if not api_key:
        api_key = os.getenv('GEMINI_API_KEY') or os.getenv('GOOGLE_API_KEY')
    
    if not api_key:
        print("Error: GEMINI_API_KEY or GOOGLE_API_KEY environment variable not set.")
        print("Please set it: export GEMINI_API_KEY='your_api_key'")
        sys.exit(1)
    
    # Connect to MongoDB
    try:
        client = pymongo.MongoClient("mongodb://localhost:27017/")
        db = client[db_name]
        collection = db[collection_name]
        
        # Find all documents (optionally with limit)
        query = {}
        if limit:
            cursor = collection.find(query).limit(limit)
        else:
            cursor = collection.find(query)
        
        files = list(cursor)
        total = len(files)
        
        if total == 0:
            print(f"No files found in collection {collection_name}")
            return
        
        print(f"Found {total} files to process")
        
        # Process each file
        successful = 0
        failed = 0
        skipped = 0
        
        for idx, doc in enumerate(files, 1):
            filename = doc.get('filename', doc.get('filepath', 'unknown'))
            raw_code = doc.get('raw_code', '')
            
            # Skip if already has summary (optional - comment out to re-process)
            if 'summary' in doc and doc.get('summary'):
                print(f"[{idx}/{total}] Skipping {filename} (already has summary)")
                skipped += 1
                continue
            
            if not raw_code:
                print(f"[{idx}/{total}] Skipping {filename} (no code content)")
                skipped += 1
                continue
            
            print(f"[{idx}/{total}] Processing {filename}...")
            
            # Truncate code if too long (Gemini has token limits)
            max_code_length = 50000  # Adjust based on API limits
            code_to_analyze = raw_code[:max_code_length]
            if len(raw_code) > max_code_length:
                print(f"  Warning: Code truncated from {len(raw_code)} to {max_code_length} characters")
            
            try:
                # Generate summary
                analysis = generate_summary(code_to_analyze, api_key)
                
                # Update document
                update_result = collection.update_one(
                    {'_id': doc['_id']},
                    {
                        '$set': {
                            'summary': analysis.get('summary', ''),
                            'tags': analysis.get('tags', []),
                            'risks': analysis.get('risks', [])
                        }
                    }
                )
                
                if update_result.modified_count > 0:
                    print(f"  ✓ Updated: {len(analysis.get('tags', []))} tags, {len(analysis.get('risks', []))} risks")
                    successful += 1
                else:
                    print(f"  ✗ No update made")
                    failed += 1
                
                # Rate limiting - wait a bit between requests
                time.sleep(0.5)  # Adjust based on API rate limits
                
            except Exception as e:
                print(f"  ✗ Error processing {filename}: {e}")
                failed += 1
        
        print(f"\nCompleted:")
        print(f"  Successful: {successful}")
        print(f"  Failed: {failed}")
        print(f"  Skipped: {skipped}")
        
    except PyMongoError as e:
        print(f"MongoDB error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


def main():
    """Main function to run the Gemini summarizer."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Generate summaries for code files using Gemini API')
    parser.add_argument('--db-name', default='codelens', help='MongoDB database name (default: codelens)')
    parser.add_argument('--collection', default='ast_data', help='MongoDB collection name (default: ast_data)')
    parser.add_argument('--api-key', help='Google Gemini API key (or set GEMINI_API_KEY env var)')
    parser.add_argument('--limit', type=int, help='Limit number of files to process (for testing)')
    
    args = parser.parse_args()
    
    print("Starting Gemini Summarizer Bot...")
    print(f"Database: {args.db_name}")
    print(f"Collection: {args.collection}")
    
    update_files_with_summaries(
        db_name=args.db_name,
        collection_name=args.collection,
        api_key=args.api_key,
        limit=args.limit
    )


if __name__ == "__main__":
    main()

