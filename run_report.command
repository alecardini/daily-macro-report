#!/bin/bash
cd "$(dirname "$0")"

# Use the project virtualenv when it exists, otherwise fall back to system python3.
# The fallback keeps the launcher working on a fresh clone that has no venv yet.
if [ -x ".venv/bin/python" ]; then
    ./.venv/bin/python generate_report.py
else
    python3 generate_report.py
fi
