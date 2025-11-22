#!/usr/bin/env bash
set -euo pipefail

# Imports data/nodes.json and data/edges.json into the 'codelens' database
# Usage (from repo root): ./scripts/import_collections.sh

DB=codelens
HOST=localhost
PORT=27017
REPLICASET=rs0

# If your mongo isn't a replica set, remove the replicaSet query param
URI="mongodb://${HOST}:${PORT}/?replicaSet=${REPLICASET}"

if ! command -v mongoimport >/dev/null 2>&1; then
  echo "mongoimport not found locally. You can either install mongo-tools or use the mongo container approach (see README)."
fi

echo "Importing nodes..."
mongoimport --uri "$URI" --db "$DB" --collection nodes --jsonArray --file ./data/nodes.json --drop || true

echo "Importing edges..."
mongoimport --uri "$URI" --db "$DB" --collection edges --jsonArray --file ./data/edges.json --drop || true

echo "Import finished."
