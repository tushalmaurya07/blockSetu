#!/usr/bin/env bash
python3 -m pip install -r requirements.txt
python3 -m uvicorn main:app --reload --host 127.0.0.1 --port 8000
