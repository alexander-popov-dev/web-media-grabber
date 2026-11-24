"""Cookie extraction utilities using Playwright."""

import os
from pathlib import Path
from typing import Optional

from playwright.async_api import async_playwright


def cookies_to_netscape(cookies: list[dict], domain_filter: Optional[str] = None) -> str:
    """Convert Playwright cookies to Netscape format."""
    lines = ["# Netscape HTTP Cookie File"]
    for c in cookies:
        if domain_filter and domain_filter not in c.get("domain", ""):
            continue
        # Netscape format: domain, flag, path, secure, expires, name, value
        domain = c.get("domain", "")
        flag = "TRUE" if domain.startswith(".") else "FALSE"
        path = c.get("path", "/")
        secure = "TRUE" if c.get("secure") else "FALSE"
        expires = str(int(c.get("expires", 0))) if c.get("expires") else "0"
        name = c.get("name", "")
        value = c.get("value", "")
        lines.append("\t".join([domain, flag, path, secure, expires, name, value]))
    return "\n".join(lines)


async def extract_cookies(
    url: str,
    domain_filter: Optional[str] = None,
    wait_for: Optional[str] = None,
    timeout: int = 30000,
) -> str:
    """Extract cookies from a URL using headless Playwright (no login).

    Args:
        url: URL to visit for cookie extraction
        domain_filter: Only include cookies for this domain (e.g., 'youtube.com')
        wait_for: CSS selector to wait for before extracting cookies
        timeout: Timeout in milliseconds

    Returns:
        Netscape format cookie string
    """
    async with async_playwright() as p:
        # Launch with stealth options to avoid detection
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
                "--disable-web-security",
            ],
        )
        try:
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                viewport={"width": 1920, "height": 1080},
                locale="en-US",
                timezone_id="UTC",
            )

            # Add stealth scripts
            await context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
                window.chrome = { runtime: {} };
            """)

            page = await context.new_page()

            # Navigate to URL
            await page.goto(url, wait_until="networkidle", timeout=timeout)

            if wait_for:
                await page.wait_for_selector(wait_for, timeout=timeout)

            # Small wait for any dynamic cookies
            await page.wait_for_timeout(2000)

            # Extract cookies
            cookies = await context.cookies()

            return cookies_to_netscape(cookies, domain_filter)
        finally:
            await browser.close()


def save_cookies(cookies_str: str, filepath: str) -> None:
    """Save cookies to file."""
    Path(filepath).write_text(cookies_str, encoding="utf-8")


def load_cookies(filepath: str) -> str:
    """Load cookies from file."""
    return Path(filepath).read_text(encoding="utf-8")


def is_cookies_fresh(filepath: str, max_age_hours: int = 24) -> bool:
    """Check if cookies file exists and is fresh."""
    path = Path(filepath)
    if not path.exists():
        return False
    import time
    age_hours = (time.time() - path.stat().st_mtime) / 3600
    return age_hours < max_age_hours


async def ensure_fresh_cookies(
    filepath: str,
    url: str,
    domain_filter: str,
    max_age_hours: int = 24,
    force_refresh: bool = False,
) -> str:
    """Ensure cookies file exists and is fresh, extracting new ones if needed."""
    if not force_refresh and is_cookies_fresh(filepath):
        return load_cookies(filepath)

    print(f"Extracting fresh cookies for {domain_filter}...")
    cookies = await extract_cookies(url, domain_filter=domain_filter)
    save_cookies(cookies, filepath)
    return cookies