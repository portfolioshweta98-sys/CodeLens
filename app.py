#!/usr/bin/env python3
"""
Step 6 & 7: Graph Visualization & Code Chat
Streamlit app for interactive code graph visualization and semantic code search.
"""

import streamlit as st
import pymongo
from streamlit_agraph import agraph, Node, Edge, Config
from typing import List, Dict, Any, Optional
import os
import re
import json

# Try importing google-genai
try:
    from google.genai import Client as GenAIClient
    USE_CLIENT_API = True
except ImportError:
    try:
        import google.generativeai as genai
        USE_CLIENT_API = False
    except ImportError:
        USE_CLIENT_API = None


# Page configuration
st.set_page_config(
    page_title="CodeLens - Code Graph Visualization",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded"
)

# MongoDB connection
@st.cache_resource
def get_mongodb_client(connection_string: str = "mongodb://localhost:27017/"):
    """Get MongoDB client connection (cached)."""
    try:
        client = pymongo.MongoClient(connection_string)
        # Test connection
        client.admin.command('ping')
        return client
    except Exception as e:
        st.error(f"Failed to connect to MongoDB: {e}")
        return None


def get_node_color(file_data: Dict[str, Any]) -> str:
    """
    Determine node color based on file characteristics.
    
    Color coding:
    - Red → risky files (has risks)
    - Yellow → API or DB logic (tags include "api" or "database")
    - Green → simple utility code (default)
    """
    tags = file_data.get('tags', [])
    risks = file_data.get('risks', [])
    
    # Red: Has risks
    if risks and len(risks) > 0:
        return "#FF4444"  # Red
    
    # Yellow: API or Database logic
    if any(tag.lower() in ['api', 'database', 'db'] for tag in tags):
        return "#FFD700"  # Gold/Yellow
    
    # Green: Simple utility code (default)
    return "#44FF44"  # Green


def load_graph_data(db_name: str = "codelens"):
    """
    Load graph data from MongoDB.
    
    Returns:
        Tuple of (nodes_data, edges_data) dictionaries
    """
    client = get_mongodb_client()
    if not client:
        return {}, {}
    
    try:
        db = client[db_name]
        
        # Load nodes (files) from ast_data collection
        ast_collection = db["ast_data"]
        nodes_data = {}
        for doc in ast_collection.find({}):
            filename = doc.get('filename', doc.get('filepath', 'unknown'))
            if not filename:
                continue
            # Use basename as key for consistency
            key = os.path.basename(filename) if filename else filename
            nodes_data[key] = {
                'filename': key,
                'filepath': doc.get('filepath', filename),
                'summary': doc.get('summary', ''),
                'tags': doc.get('tags', []),
                'risks': doc.get('risks', []),
                'functions': doc.get('functions', []),
                'classes': doc.get('classes', [])
            }
        
        # Load edges (imports) from edges collection
        edges_collection = db["edges"]
        edges_data = []
        for doc in edges_collection.find({}):
            edges_data.append({
                'source': doc.get('source', ''),
                'target': doc.get('target', '')
            })
        
        return nodes_data, edges_data
        
    except Exception as e:
        st.error(f"Error loading graph data: {e}")
        return {}, {}


def create_graph_nodes_and_edges(nodes_data: Dict, edges_data: List[Dict]) -> tuple:
    """
    Create agraph Node and Edge objects from data.
    
    Returns:
        Tuple of (nodes_list, edges_list)
    """
    nodes = []
    edges = []
    
    # Create nodes with color coding
    for filename, file_data in nodes_data.items():
        color = get_node_color(file_data)
        
        # Create label with filename
        label = filename
        
        # Create node
        node = Node(
            id=filename,
            label=label,
            color=color,
            size=20,
            font={"size": 12}
        )
        nodes.append(node)
    
    # Create edges
    seen_edges = set()
    for edge_data in edges_data:
        source = edge_data.get('source', '')
        target = edge_data.get('target', '')
        
        # Only create edge if both nodes exist
        if source in nodes_data and target in nodes_data:
            edge_key = (source, target)
            if edge_key not in seen_edges:
                edge = Edge(
                    source=source,
                    target=target,
                    type="CURVE_SMOOTH",
                    animated=False,
                    arrowStrikethrough=True
                )
                edges.append(edge)
                seen_edges.add(edge_key)
    
    return nodes, edges


def search_mongodb_summaries(query: str, db_name: str = "codelens", limit: int = 10) -> List[Dict[str, Any]]:
    """
    Search MongoDB summaries for keywords matching the user query.
    
    Args:
        query: User's search query
        db_name: MongoDB database name
        limit: Maximum number of results to return
        
    Returns:
        List of matching file documents with relevance scores
    """
    client = get_mongodb_client()
    if not client:
        return []
    
    try:
        db = client[db_name]
        collection = db["ast_data"]
        
        # Extract keywords from query (simple approach - split on spaces)
        keywords = [word.lower().strip() for word in re.split(r'\s+', query) if len(word) > 2]
        
        if not keywords:
            return []
        
        # Build search query - search in summaries, tags, filename, functions
        search_results = []
        
        # Get all documents with summaries
        all_docs = list(collection.find({"summary": {"$exists": True, "$ne": ""}}))
        
        # Score documents based on keyword matches
        scored_docs = []
        for doc in all_docs:
            score = 0
            summary = doc.get('summary', '').lower()
            tags = [tag.lower() for tag in doc.get('tags', [])]
            filename = doc.get('filename', '').lower()
            functions = [func.lower() for func in doc.get('functions', [])]
            classes = [cls.lower() for cls in doc.get('classes', [])]
            
            # Check each keyword
            for keyword in keywords:
                # Higher weight for exact matches in filename
                if keyword in filename:
                    score += 10
                # Medium weight for matches in summary
                if keyword in summary:
                    score += 5
                # Medium weight for matches in tags
                if any(keyword in tag for tag in tags):
                    score += 5
                # Lower weight for matches in function/class names
                if any(keyword in func for func in functions):
                    score += 2
                if any(keyword in cls for cls in classes):
                    score += 2
            
            if score > 0:
                scored_docs.append((score, doc))
        
        # Sort by score and return top results
        scored_docs.sort(key=lambda x: x[0], reverse=True)
        return [doc for _, doc in scored_docs[:limit]]
        
    except Exception as e:
        st.error(f"Error searching MongoDB: {e}")
        return []


def query_gemini_with_context(user_question: str, relevant_files: List[Dict[str, Any]], api_key: str) -> str:
    """
    Send user question and relevant file summaries to Gemini for context-aware answer.
    
    Args:
        user_question: User's question
        relevant_files: List of relevant file documents
        api_key: Gemini API key
        
    Returns:
        Gemini's response
    """
    if USE_CLIENT_API is None:
        return "Error: google-genai package not installed. Please install it: pip install google-genai"
    
    # Build context from relevant files
    context_parts = []
    for i, file_doc in enumerate(relevant_files, 1):
        filename = file_doc.get('filename', file_doc.get('filepath', 'unknown'))
        summary = file_doc.get('summary', '')
        tags = file_doc.get('tags', [])
        functions = file_doc.get('functions', [])
        classes = file_doc.get('classes', [])
        risks = file_doc.get('risks', [])
        
        file_info = f"""
File {i}: {filename}
Summary: {summary}
Tags: {', '.join(tags) if tags else 'None'}
Functions: {', '.join(functions[:5]) if functions else 'None'}""" + (f"... ({len(functions)} total)" if len(functions) > 5 else "")
        
        if classes:
            file_info += f"\nClasses: {', '.join(classes)}"
        
        if risks:
            file_info += f"\nRisks: {', '.join(risks)}"
        
        context_parts.append(file_info)
    
    context = "\n---\n".join(context_parts)
    
    # Build prompt
    prompt = f"""You are a helpful code assistant analyzing a codebase.

The user asked: "{user_question}"

Here are relevant files and their summaries from the codebase:

{context}

Based on the summaries above, answer the user's question. Be specific and reference exact file names and function/class names when possible. If a file contains the answer, mention the file name and relevant function/class.

Answer:"""
    
    try:
        if USE_CLIENT_API:
            # New google-genai Client API
            client = GenAIClient(api_key=api_key)
            try:
                response = client.models.generate_content(
                    model='models/gemini-pro',
                    contents=[{'role': 'user', 'parts': [{'text': prompt}]}]
                )
            except Exception:
                response = client.models.generate_content(
                    model='gemini-pro',
                    contents=prompt
                )
            
            # Extract text from response
            if hasattr(response, 'text'):
                return response.text.strip()
            elif hasattr(response, 'candidates') and response.candidates:
                return response.candidates[0].content.parts[0].text.strip()
            elif hasattr(response, 'content'):
                return response.content.strip()
            else:
                return str(response).strip()
        else:
            # Standard google.generativeai API
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel('gemini-pro')
            response = model.generate_content(prompt)
            return response.text.strip()
            
    except Exception as e:
        return f"Error querying Gemini API: {str(e)}"


def show_code_chat_page(db_name: str):
    """Display the Code Chat page."""
    st.header("💬 Ask the Repo")
    st.markdown("**Semantic search across your codebase using AI**")
    st.markdown("Ask questions about your codebase and get answers based on actual code summaries, not hallucinations!")
    
    st.markdown("---")
    
    # Check for API key
    api_key = os.getenv('GEMINI_API_KEY') or os.getenv('GOOGLE_API_KEY')
    if not api_key:
        st.warning("⚠️ **GEMINI_API_KEY not set.** Please set it in your environment or in the sidebar.")
        api_key = st.sidebar.text_input("Gemini API Key", type="password", help="Enter your Google Gemini API key")
    
    if not api_key:
        st.info("Please set your Gemini API key to use the Code Chat feature.")
        st.code("export GEMINI_API_KEY='your_api_key'")
        return
    
    # Chat interface
    st.markdown("### Ask a Question")
    
    # Initialize chat history
    if 'chat_history' not in st.session_state:
        st.session_state.chat_history = []
    
    # User input
    user_question = st.text_input(
        "Enter your question:",
        placeholder="e.g., Where is user login implemented?",
        key="user_question_input"
    )
    
    col1, col2 = st.columns([1, 5])
    with col1:
        ask_button = st.button("🔍 Ask", type="primary")
    
    with col2:
        if st.button("🗑️ Clear History"):
            st.session_state.chat_history = []
            st.rerun()
    
    # Process question
    if ask_button and user_question:
        with st.spinner("Searching codebase and generating answer..."):
            # Search MongoDB for relevant files
            relevant_files = search_mongodb_summaries(user_question, db_name, limit=5)
            
            if not relevant_files:
                st.warning("No relevant files found. Try rephrasing your question.")
                return
            
            # Show relevant files found
            with st.expander(f"📁 Found {len(relevant_files)} relevant file(s)", expanded=False):
                for file_doc in relevant_files:
                    filename = file_doc.get('filename', file_doc.get('filepath', 'unknown'))
                    summary = file_doc.get('summary', 'No summary available')
                    st.markdown(f"**{filename}**")
                    st.caption(summary[:200] + "..." if len(summary) > 200 else summary)
                    st.markdown("---")
            
            # Query Gemini with context
            answer = query_gemini_with_context(user_question, relevant_files, api_key)
            
            # Add to chat history
            st.session_state.chat_history.append({
                'question': user_question,
                'answer': answer,
                'relevant_files': [file_doc.get('filename', file_doc.get('filepath', 'unknown')) for file_doc in relevant_files]
            })
    
    # Display chat history
    if st.session_state.chat_history:
        st.markdown("---")
        st.markdown("### 💬 Chat History")
        
        # Display in reverse order (newest first)
        for idx, chat in enumerate(reversed(st.session_state.chat_history)):
            with st.container():
                st.markdown(f"**❓ Question:** {chat['question']}")
                st.markdown(f"**🤖 Answer:**")
                st.markdown(chat['answer'])
                
                if chat.get('relevant_files'):
                    st.caption(f"📁 Based on: {', '.join(chat['relevant_files'][:3])}")
                    if len(chat['relevant_files']) > 3:
                        st.caption(f"... and {len(chat['relevant_files']) - 3} more")
                
                if idx < len(st.session_state.chat_history) - 1:
                    st.markdown("---")
    
    # Example questions
    st.markdown("---")
    st.markdown("### 💡 Example Questions")
    example_cols = st.columns(3)
    example_questions = [
        "Where is user authentication implemented?",
        "What files handle database connections?",
        "Are there any SQL injection risks?",
        "Which files contain API endpoints?",
        "What functions are related to file uploads?",
        "Where is configuration management handled?"
    ]
    
    for i, example in enumerate(example_questions):
        with example_cols[i % 3]:
            if st.button(f"💬 {example[:30]}...", key=f"example_{i}"):
                st.session_state.example_question = example
                st.rerun()
    
    # Handle example question click
    if 'example_question' in st.session_state:
        user_question = st.session_state.example_question
        del st.session_state.example_question
        # Trigger the search
        with st.spinner("Searching codebase and generating answer..."):
            relevant_files = search_mongodb_summaries(user_question, db_name, limit=5)
            if relevant_files:
                answer = query_gemini_with_context(user_question, relevant_files, api_key)
                st.session_state.chat_history.append({
                    'question': user_question,
                    'answer': answer,
                    'relevant_files': [file_doc.get('filename', file_doc.get('filepath', 'unknown')) for file_doc in relevant_files]
                })
                st.rerun()


def main():
    """Main Streamlit app."""
    
    # Title and header
    st.title("🔍 CodeLens")
    st.markdown("**Interactive codebase analysis and visualization**")
    
    # Sidebar configuration
    st.sidebar.header("⚙️ Configuration")
    
    # MongoDB connection status
    st.sidebar.markdown("### 🔌 MongoDB Status")
    client = get_mongodb_client()
    if client:
        try:
            # Test connection
            client.admin.command('ping')
            db_name = st.sidebar.text_input("Database Name", value="codelens")
            
            # Show database info
            db = client[db_name]
            collections = db.list_collection_names()
            collection_counts = {name: db[name].count_documents({}) for name in collections}
            
            st.sidebar.success("✓ Connected to MongoDB")
            with st.sidebar.expander("📊 Database Info", expanded=True):
                if collections:
                    st.markdown(f"**Collections:** {len(collections)}")
                    for coll_name, count in collection_counts.items():
                        st.markdown(f"- `{coll_name}`: {count} docs")
                else:
                    st.info("No collections found")
                    st.markdown("---")
                    st.markdown("### 📝 Next Steps:")
                    st.markdown("""
                    1. **Parse a repository:**
                       ```bash
                       python ast_parser.py <repo_url>
                       ```
                    
                    2. **Build the graph:**
                       ```bash
                       python graph_constructor.py --repo-path ./repos/<repo_name>
                       ```
                    
                    3. **Generate summaries:**
                       ```bash
                       export GEMINI_API_KEY='your_key'
                       python gemini_summarizer.py
                       ```
                    """)
        except Exception as e:
            st.sidebar.error(f"✗ Connection error: {str(e)}")
            db_name = st.sidebar.text_input("Database Name", value="codelens")
    else:
        st.sidebar.error("✗ Not connected to MongoDB")
        st.sidebar.info("Make sure MongoDB is running:")
        st.sidebar.code("docker compose up -d")
        db_name = st.sidebar.text_input("Database Name", value="codelens")
    
    st.sidebar.markdown("---")
    
    # Tabs for different features
    tab1, tab2 = st.tabs(["📊 Graph Visualization", "💬 Ask the Repo"])
    
    with tab1:
        # Load data button
        if st.sidebar.button("🔄 Refresh Graph Data", type="primary"):
            st.cache_data.clear()
            st.rerun()
        
        st.sidebar.markdown("---")
        
        # Load graph data
        with st.spinner("Loading graph data from MongoDB..."):
            nodes_data, edges_data = load_graph_data(db_name)
        
        if not nodes_data:
            st.warning("⚠️ No graph data found. Please run the ingestion pipeline first:")
            st.code("""
            1. python ast_parser.py <repo_url>
            2. python graph_constructor.py --repo-path <repo_path>
            3. python gemini_summarizer.py
            """)
        else:
            # Statistics
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Total Files", len(nodes_data))
            with col2:
                st.metric("Total Edges", len(edges_data))
            with col3:
                risky_files = sum(1 for n in nodes_data.values() if n.get('risks'))
                st.metric("Risky Files", risky_files, delta=None)
            with col4:
                api_db_files = sum(1 for n in nodes_data.values() 
                                  if any(tag.lower() in ['api', 'database', 'db'] 
                                        for tag in n.get('tags', [])))
                st.metric("API/DB Files", api_db_files)
            
            st.markdown("---")
            
            # Color legend
            st.markdown("### 🎨 Color Legend")
            col1, col2, col3 = st.columns(3)
            with col1:
                st.markdown('<div style="background-color: #FF4444; padding: 10px; border-radius: 5px; text-align: center; color: white; font-weight: bold;">🔴 Risky Files</div>', unsafe_allow_html=True)
            with col2:
                st.markdown('<div style="background-color: #FFD700; padding: 10px; border-radius: 5px; text-align: center; color: black; font-weight: bold;">🟡 API/DB Logic</div>', unsafe_allow_html=True)
            with col3:
                st.markdown('<div style="background-color: #44FF44; padding: 10px; border-radius: 5px; text-align: center; color: black; font-weight: bold;">🟢 Utility Code</div>', unsafe_allow_html=True)
            
            st.markdown("---")
            
            # Create graph visualization
            st.markdown("### 📊 Code Graph")
            
            # Graph configuration
            config = Config(
                width=1200,
                height=800,
                directed=True,
                nodeHighlightBehavior=True,
                highlightColor="#F7A7A6",
                collapsible=True,
                node={'labelProperty': 'label', 'renderLabel': True},
                link={'highlightColor': '#F7A7A6'},
                physics={
                    "barnesHut": {
                        "gravitationalConstant": -8000,
                        "centralGravity": 0.3,
                        "springLength": 95,
                        "springConstant": 0.04,
                        "damping": 0.09,
                        "avoidOverlap": 0.1
                    },
                    "maxVelocity": 50,
                    "minVelocity": 0.75,
                    "solver": "barnesHut",
                    "timestep": 0.35
                }
            )
            
            # Create nodes and edges
            nodes, edges = create_graph_nodes_and_edges(nodes_data, edges_data)
            
            # Display graph
            if nodes:
                # Initialize session state for selected node
                if 'selected_node' not in st.session_state:
                    st.session_state.selected_node = None
                
                # Render graph and handle node clicks
                return_value = agraph(
                    nodes=nodes,
                    edges=edges,
                    config=config
                )
                
                # Handle node click - agraph returns a dict with 'nodes' key when clicked
                if return_value:
                    try:
                        if isinstance(return_value, dict):
                            clicked_nodes = return_value.get('nodes', [])
                            if clicked_nodes:
                                node_id = clicked_nodes[0] if isinstance(clicked_nodes, list) else clicked_nodes
                                if node_id and node_id != st.session_state.get('selected_node'):
                                    st.session_state.selected_node = node_id
                                    st.rerun()
                    except Exception as e:
                        # Silently handle any parsing errors
                        pass
                
                # Add a dropdown selector as alternative to clicking
                st.markdown("---")
                st.markdown("**Or select a file from the dropdown:**")
                all_filenames = sorted(list(nodes_data.keys()))
                selected_file = st.selectbox(
                    "Select a file:",
                    options=[""] + all_filenames,
                    index=0 if st.session_state.get('selected_node') not in all_filenames 
                          else all_filenames.index(st.session_state.get('selected_node')) + 1,
                    key="node_selector"
                )
                if selected_file and selected_file != st.session_state.get('selected_node'):
                    st.session_state.selected_node = selected_file
                    st.rerun()
                
                # Sidebar: Show selected node details
                st.sidebar.markdown("---")
                st.sidebar.header("📄 File Details")
                
                selected_node = st.session_state.get('selected_node')
                if selected_node and selected_node in nodes_data:
                    file_data = nodes_data[selected_node]
                    
                    st.sidebar.markdown(f"### {selected_node}")
                    
                    # File path
                    if file_data.get('filepath'):
                        st.sidebar.markdown(f"**Path:** `{file_data.get('filepath')}`")
                    
                    # Tags
                    tags = file_data.get('tags', [])
                    if tags:
                        st.sidebar.markdown("**Tags:**")
                        tag_str = " ".join([f"`{tag}`" for tag in tags])
                        st.sidebar.markdown(tag_str)
                    
                    # Summary
                    summary = file_data.get('summary', '')
                    if summary:
                        st.sidebar.markdown("---")
                        st.sidebar.markdown("### 📝 Summary")
                        st.sidebar.markdown(summary)
                    
                    # Risks
                    risks = file_data.get('risks', [])
                    if risks:
                        st.sidebar.markdown("---")
                        st.sidebar.markdown("### ⚠️ Risks")
                        for risk in risks:
                            st.sidebar.error(f"• {risk}")
                    else:
                        st.sidebar.markdown("---")
                        st.sidebar.markdown("### ✅ No Risks Detected")
                        st.sidebar.success("This file has no identified security risks.")
                    
                    # Functions
                    functions = file_data.get('functions', [])
                    if functions:
                        st.sidebar.markdown("---")
                        st.sidebar.markdown(f"### 🔧 Functions ({len(functions)})")
                        for func in functions[:10]:  # Show first 10
                            st.sidebar.code(func)
                        if len(functions) > 10:
                            st.sidebar.caption(f"... and {len(functions) - 10} more")
                    
                    # Classes
                    classes = file_data.get('classes', [])
                    if classes:
                        st.sidebar.markdown("---")
                        st.sidebar.markdown(f"### 📦 Classes ({len(classes)})")
                        for cls in classes:
                            st.sidebar.code(cls)
                    
                else:
                    st.sidebar.info("👆 Click on a node to view details")
                
                # Instructions
                st.sidebar.markdown("---")
                st.sidebar.markdown("### 💡 Instructions")
                st.sidebar.markdown("""
                1. **Click** on any node to view file details
                2. **Drag** nodes to rearrange the graph
                3. **Zoom** using mouse wheel or pinch
                4. **Pan** by clicking and dragging empty space
                """)
                
            else:
                st.warning("No nodes found in graph data.")
            
            # Footer for Graph tab
            st.markdown("---")
            st.markdown(
                """
                <div style='text-align: center; color: #666; padding: 20px;'>
                <p>CodeLens - Code Graph Visualization | Built with Streamlit & streamlit-agraph</p>
                </div>
                """,
                unsafe_allow_html=True
            )
    
    with tab2:
        show_code_chat_page(db_name)


if __name__ == "__main__":
    main()

