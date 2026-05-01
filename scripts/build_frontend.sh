#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo "Building frontend..."
cd "$PROJECT_ROOT/frontend"
npm ci
npm run build

echo "Copying to static directory..."
rm -rf "$PROJECT_ROOT/src/flow_llm_router/static/"*
cp -r out/* "$PROJECT_ROOT/src/flow_llm_router/static/"
touch "$PROJECT_ROOT/src/flow_llm_router/static/.gitkeep"

echo "Done! Frontend built and copied to src/flow_llm_router/static/"
