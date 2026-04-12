#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo "Building frontend..."
cd "$PROJECT_ROOT/frontend"
npm ci
npm run build

echo "Copying to static directory..."
rm -rf "$PROJECT_ROOT/src/flowgate/static/"*
cp -r out/* "$PROJECT_ROOT/src/flowgate/static/"
touch "$PROJECT_ROOT/src/flowgate/static/.gitkeep"

echo "Done! Frontend built and copied to src/flowgate/static/"
