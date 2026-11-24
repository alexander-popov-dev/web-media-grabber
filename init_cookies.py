#!/usr/bin/env python
"""Initialize cookie files with proper permissions."""
import os
from pathlib import Path

cookie_files = [
    "cookies.txt",
    "cookies_youtube.txt",
    "cookies_facebook.txt",
    "cookies_instagram.txt",
    "cookies_tiktok.txt",
]

for cookie_file in cookie_files:
    filepath = Path(cookie_file)
    if not filepath.exists():
        filepath.write_text("# Netscape HTTP Cookie File\n", encoding="utf-8")
        print(f"Created {cookie_file}")
    else:
        print(f"Already exists: {cookie_file}")

print("Cookie files initialized.")