#!/usr/bin/env bash
cd "$(dirname "$0")"
source .venv/bin/activate
cd app/backend/src
uvicorn main:app --reload
