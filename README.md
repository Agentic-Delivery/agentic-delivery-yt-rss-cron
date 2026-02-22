# agentic-delivery-yt-rss-cron

Automated YouTube channel monitoring + relevance filtering for the `/yt-intel` pipeline.

## What it does

Polls 17 curated YouTube channels via RSS, applies a two-stage relevance filter (keyword matching + metadata scoring), and triggers the full `/yt-intel` intelligence pipeline for qualifying videos.

```
channels.yaml -> poll.sh -> fetch_rss.py (Stage 1: keyword filter, FREE)
                                 |
                           [new videos only]
                                 |
                           filter_stage2.py (Stage 2: yt-dlp metadata, 2-5s each)
                                 |
                           [score >= threshold]
                                 |
                           trigger.sh -> claude -p (full yt-intel pipeline, ~$0.50 each)
                                 |
                           state/processed.json (track what's done)
```

## Quick start

```bash
# Check dependencies
bash install.sh --check

# Dry run (no claude invocations)
bash poll.sh --dry-run

# Single poll cycle
bash poll.sh

# Daemon mode (polls every 30 min)
bash poll.sh --daemon

# Install as systemd timer
bash install.sh --systemd
```

## Configuration

- `config.yaml` — Polling interval, thresholds, budget limits
- `channels.yaml` — YouTube channels to monitor (17 curated)
- `keywords.yaml` — Keyword groups with weights for relevance filtering

## Two-stage relevance gate

**Stage 1** (free): Keyword matching on RSS title + description. Eliminates obviously irrelevant content.

**Stage 2** (2-5s per video): Deterministic scoring on yt-dlp metadata — tag matching, duration filtering, description keyword density, channel category boost. No LLM call.

**Stage 3** (existing yt-intel, ~$0.50): Full pipeline only for videos scoring >= 4/10.

## Budget controls

- Daily cap: $5 (configurable)
- Per-video cap: $0.50
- Circuit breaker stops pipeline when budget exhausted
- Tracked in `state/budget.json`

## Dependencies

- Python 3.12+
- PyYAML
- yt-dlp
- Claude Code CLI (`claude`)
