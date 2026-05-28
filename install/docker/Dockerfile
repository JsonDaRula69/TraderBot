FROM debian:bookworm-slim

LABEL org.openclaw.sandbox="traderbot" \
      description="TraderBot sandbox image for OpenClaw category agents"

# Install Python 3.12 and essential tools
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    python3-venv \
    git \
    curl \
    jq \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Create user matching host UID/GID (overridden at runtime by OpenClaw)
RUN groupadd -r traderbot --gid 1000 && \
    useradd -rm -g traderbot -u 1000 traderbot && \
    mkdir -p /workspace /home/traderbot/.traderbot && \
    chown -R traderbot:traderbot /workspace /home/traderbot

# Traderbot source is bind-mounted at /traderbot (read-only)
ENV PYTHONPATH=/traderbot/src
ENV PATH="/traderbot/src/traderbot:${PATH}"

WORKDIR /workspace
USER traderbot
