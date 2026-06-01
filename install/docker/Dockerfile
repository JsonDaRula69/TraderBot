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

ENV PYTHONPATH=/traderbot/src
ENV PATH="/traderbot/.venv/bin:${PATH}"

WORKDIR /workspace
USER traderbot
