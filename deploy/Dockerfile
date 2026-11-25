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

# Install deno for yt-dlp JavaScript runtime (YouTube signature challenge)
# yt-dlp 2026+ requires deno >= 2.3; the PO token provider needs it too.
ENV DENO_VERSION=2.9.8
ENV BGUTIL_POT_VERSION=2.0.2
RUN curl -fsSL "https://github.com/denoland/deno/releases/download/v${DENO_VERSION}/deno-x86_64-unknown-linux-gnu.zip" -o /tmp/deno.zip \
    && unzip /tmp/deno.zip -d /usr/local/bin/ \
    && chmod +x /usr/local/bin/deno \
    && rm /tmp/deno.zip \
    && deno --version

# Symlink deno to /usr/bin for broader PATH coverage
RUN ln -sf /usr/local/bin/deno /usr/bin/deno

# Install Node.js (>= 22 is required by current yt-dlp / bgutil provider)
RUN curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# Install Playwright + Chromium
# Set browser path to a location accessible by non-root user
ENV PLAYWRIGHT_BROWSERS_PATH=/app/playwright-browsers
RUN npm install -g playwright \
    && mkdir -p /app/playwright-browsers \
    && npx playwright install chromium \
    && npx playwright install-deps chromium

# Install the bgutil PO token provider server (script mode). The Python plugin
# from pyproject.toml calls it to generate YouTube PO tokens, which are needed
# to avoid "Sign in to confirm you're not a bot" from datacenter/server IPs.
RUN curl -fsSL --max-time 300 \
        "https://github.com/Brainicism/bgutil-ytdlp-pot-provider/archive/refs/tags/${BGUTIL_POT_VERSION}.zip" \
        -o /tmp/bgutil.zip \
    && unzip -q /tmp/bgutil.zip -d /tmp/bgutil \
    && mkdir -p /app/bgutil-ytdlp-pot-provider \
    && cp -a /tmp/bgutil/bgutil-ytdlp-pot-provider-${BGUTIL_POT_VERSION}/. /app/bgutil-ytdlp-pot-provider/ \
    && rm -rf /tmp/bgutil /tmp/bgutil.zip \
    && cd /app/bgutil-ytdlp-pot-provider/server \
    && DENO_DIR=/app/.deno deno install --allow-scripts=npm:canvas --frozen

# Create non-root user
RUN useradd --create-home --shell /bin/bash app \
    && chown -R app:app /app/playwright-browsers /app/bgutil-ytdlp-pot-provider /app/.deno

# Set working directory
WORKDIR /app

# Copy installed dependencies from builder
COPY --from=builder --chown=app:app /app/.venv .venv

# Copy application code
COPY --chown=app:app . .

# Create cookies directory with proper permissions for app user
RUN mkdir -p /app/cookies && chown -R app:app /app/cookies

# Set PATH BEFORE switching user so it applies to all processes including subprocesses
ENV PATH="/app/.venv/bin:/usr/local/bin:/usr/bin:${PATH}"

# Switch to non-root user
USER app

# Verify deno is available after user switch
RUN deno --version && which deno

# yt-dlp uses the deno runtime resolved by the scraper; keep its cache writable.
ENV DENO_DIR=/app/.deno

# The port is defined by BACKEND_PORT in .env; no EXPOSE on purpose.
# Shell-form HEALTHCHECK expands it at container runtime.
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f "http://localhost:${BACKEND_PORT:-8000}/health" || exit 1

CMD ["python", "main.py"]