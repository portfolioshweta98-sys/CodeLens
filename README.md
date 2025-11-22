# CodeLens

## MongoDB Replica Set (Local)

This repository includes a simple Docker Compose setup to run a 3-node MongoDB replica set locally for development and testing.

Files added:
- `docker-compose.yml` — defines `mongo1`, `mongo2`, `mongo3`, and `mongo-init` services.
- `scripts/init-replica.js` — JS script that initiates the replica set.
- `scripts/wait-and-init.sh` — helper script that waits for MongoDB to be available then runs the init script.

Quick start:

1. Ensure Docker and Docker Compose are installed.
2. Start the cluster:

```
docker compose up -d
```

3. Monitor the init logs (optional):

```
docker compose logs -f mongo-init
```

4. Verify the replica set status:

```
docker exec -it mongo1 mongo --eval "rs.status()"
```

Stop and remove the cluster and volumes:

```
docker compose down -v
```

Notes:
- The init container runs once and attempts to initiate the replica set. Re-running `docker compose up` after an initial setup will keep the replica set as-is.
- Exposed ports: `27017` (mongo1), `27018` (mongo2 -> container 27017), `27019` (mongo3 -> container 27017).

## CodeLens - Code Graph Visualization

CodeLens is a comprehensive codebase analysis and visualization tool that extracts structural information, enriches it with AI-powered summaries, and visualizes the code graph interactively.

### Pipeline Overview

1. **Step 2: AST Parser** - Parse Python files and extract functions, classes, imports
2. **Step 3: Graph Construction** - Build import relationships between files
3. **Step 4: Gemini Summarizer** - Generate AI-powered summaries, tags, and risk assessments
4. **Step 5: Brave Metadata** - Enrich library information from Brave Search
5. **Step 6: Graph Visualization** - Interactive Streamlit visualization

### Quick Start

#### 1. Setup MongoDB

```bash
docker compose up -d
```

#### 2. Run the Pipeline

```bash
# Step 2: Parse repository
python ast_parser.py <repo_url>

# Step 3: Build graph (use the cloned repo path)
python graph_constructor.py --repo-path ./repos/<repo_name>

# Step 4: Generate summaries (requires GEMINI_API_KEY)
export GEMINI_API_KEY='your_api_key'
python gemini_summarizer.py

# Step 5: Enrich library metadata (requires BRAVE_API_KEY)
export BRAVE_API_KEY='your_api_key'
python brave_metadata.py ./repos/<repo_name>/requirements.txt
```

#### 3. Launch Visualization

```bash
streamlit run app.py
```

Then open your browser to `http://localhost:8501`

### Graph Visualization Features

- **Color-Coded Nodes:**
  - 🔴 **Red** → Risky files (contains security risks)
  - 🟡 **Yellow** → API or Database logic files
  - 🟢 **Green** → Simple utility code

- **Interactive Features:**
  - Click nodes to view file details in sidebar
  - Drag nodes to rearrange the graph
  - Zoom and pan the visualization
  - Search/filter files using dropdown

- **Sidebar Information:**
  - File summary (from Gemini AI)
  - Tags (auth, api, database, etc.)
  - Security risks
  - Functions and classes

### Environment Variables

- `GEMINI_API_KEY` - Google Gemini API key (for Step 4)
- `BRAVE_API_KEY` - Brave Search API key (for Step 5)

### Requirements

See `requirements.txt` or install:
```bash
pip install pymongo gitpython streamlit google-genai requests streamlit-agraph
```
