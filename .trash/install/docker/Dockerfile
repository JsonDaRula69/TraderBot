FROM python:3.12-slim-bookworm

LABEL org.openclaw.sandbox="traderbot" \
      description="TraderBot sandbox image for OpenClaw category agents"

# Install runtime tools (git, curl, jq)
RUN apt-get update && apt-get install -y \
    git \
    curl \
    jq \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd -r traderbot --gid 1000 && \
    useradd -rm -g traderbot -u 1000 traderbot && \
    mkdir -p /workspace /home/traderbot/.traderbot && \
    chown -R traderbot:traderbot /workspace /home/traderbot

# The host's .venv/bin/traderbot has a hardcoded shebang to the host Python.
# Use the container's python3 with PYTHONPATH pointing to the venv's site-packages
# so all traderbot dependencies are available.
ENV PYTHONPATH="/traderbot/src:/traderbot/.venv/lib/python3.12/site-packages"
ENV PATH="/usr/local/bin:/traderbot/.venv/bin:${PATH}"

RUN printf '#!/bin/sh\nexec python3 -c "from traderbot.cli import main; main()" "$@"\n' > /usr/local/bin/traderbot && \
    chmod +x /usr/local/bin/traderbot

WORKDIR /workspace
USER traderbot
