# Build stage
FROM python:3.13-slim AS builder

# Install uv for fast dependency installation
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

# Set working directory
WORKDIR /app

# Copy dependency files
COPY pyproject.toml uv.lock ./

# Install dependencies (without --frozen to pick up new deps from pyproject.toml)
RUN uv sync --no-dev

# Runtime stage
FROM python:3.13-slim AS runtime

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    ca-certificates \
    unzip \
    && rm -rf /var/lib/apt/lists/*

# Install Node.js for Playwright
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# Install Playwright + Chromium
RUN npm install -g playwright \
    && npx playwright install chromium \
    && npx playwright install-deps chromium

# Create non-root user
RUN useradd --create-home --shell /bin/bash app

# Set working directory
WORKDIR /app

# Copy installed dependencies from builder
COPY --from=builder --chown=app:app /app/.venv .venv

# Copy application code
COPY --chown=app:app . .

# Create cookies directory with proper permissions for app user
# Also create symlinks at /app/cookies_*.txt pointing to /app/cookies/cookies_*.txt
# so that providers can find them at the expected paths
RUN mkdir -p /app/cookies && \
    touch /app/cookies/cookies.txt /app/cookies/cookies_youtube.txt /app/cookies/cookies_facebook.txt /app/cookies/cookies_instagram.txt /app/cookies/cookies_tiktok.txt && \
    ln -sf /app/cookies/cookies.txt /app/cookies.txt && \
    ln -sf /app/cookies/cookies_youtube.txt /app/cookies_youtube.txt && \
    ln -sf /app/cookies/cookies_facebook.txt /app/cookies_facebook.txt && \
    ln -sf /app/cookies/cookies_instagram.txt /app/cookies_instagram.txt && \
    ln -sf /app/cookies/cookies_tiktok.txt /app/cookies_tiktok.txt && \
    chown -R app:app /app/cookies /app/cookies.txt /app/cookies_youtube.txt /app/cookies_facebook.txt /app/cookies_instagram.txt /app/cookies_tiktok.txt

# Switch to non-root user
USER app

# Add .venv to PATH
ENV PATH="/app/.venv/bin:${PATH}"

# yt-dlp configuration
# Use deno for JavaScript runtime (YouTube signature challenges)
ENV YTDLP_JS_RUNTIME=deno
# Cookies file path (auto-refreshed by Playwright) - points to directory
ENV YTDLP_COOKIES_FILE=/app/cookies

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:80/health || exit 1

CMD ["python", "main.py"]