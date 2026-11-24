# Build stage
FROM python:3.13-slim AS builder

# Install uv for fast dependency installation
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

# Set working directory
WORKDIR /app

# Copy dependency files
COPY pyproject.toml uv.lock ./

# Install dependencies
RUN uv sync --frozen --no-dev

# Runtime stage
FROM python:3.13-slim AS runtime

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    ca-certificates \
    unzip \
    && rm -rf /var/lib/apt/lists/*

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

# Install Playwright Python package (fallback if not in uv.lock)
RUN pip install playwright==1.40.0

# Create non-root user
RUN useradd --create-home --shell /bin/bash app

# Set working directory
WORKDIR /app

# Copy installed dependencies from builder
COPY --from=builder --chown=app:app /app/.venv .venv

# Copy application code
COPY --chown=app:app . .

# Switch to non-root user
USER app

# Add .venv to PATH
ENV PATH="/app/.venv/bin:${PATH}"

# yt-dlp configuration
# Use deno for JavaScript runtime (YouTube signature challenges)
ENV YTDLP_JS_RUNTIME=deno
# Cookies file path (auto-refreshed by Playwright)
ENV YTDLP_COOKIES_FILE=/app/cookies.txt

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:80/health || exit 1

CMD ["python", "main.py"]