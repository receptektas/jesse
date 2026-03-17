#!/bin/bash
set -e

# jesse run, cwd'de strategies/ ve storage/ arar (validate_cwd)
cd /project

echo "Starting Jesse dev server with auto-restart on file changes..."
exec watchmedo auto-restart \
  --directory=/jesse-docker/jesse \
  --pattern="*.py" \
  --recursive \
  -- jesse run
