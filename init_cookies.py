#!/usr/bin/env python
"""Initialize cookie files with proper permissions."""
import os
from pathlib import Path

# Cookie files need to be in deploy/ directory for docker-compose volume mounts
DEPLOY_DIR = Path(__file__).parent / "deploy"

cookie_files = [
    "cookies.txt",
    "cookies_youtube.txt",
    "cookies_facebook.txt",
    "cookies_instagram.txt",
    "cookies_tiktok.txt",
]

DEPLOY_DIR.mkdir(exist_ok=True)

for cookie_file in cookie_files:
    filepath = DEPLOY_DIR / cookie_file
    if not filepath.exists():
        filepath.write_text("# Netscape HTTP Cookie File\n", encoding="utf-8")
        print(f"Created {filepath}")
    else:
        print(f"Already exists: {filepath}")

print("Cookie files initialized in deploy/ directory.")