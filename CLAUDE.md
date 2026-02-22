# agentic-delivery-yt-rss-cron

Automated YouTube RSS monitor that feeds the `/yt-intel` intelligence pipeline.

## Architecture

Two-stage relevance filter before expensive LLM calls:
1. **Stage 1** — Free keyword matching on RSS title/description (`lib/fetch_rss.py`)
2. **Stage 2** — Deterministic yt-dlp metadata scoring (`lib/filter_stage2.py`)
3. **Stage 3** — Full yt-intel pipeline via `claude -p` (`lib/trigger.sh`)

Entry point: `poll.sh` (supports `--dry-run` and `--daemon` modes)

## Key files

| File | Purpose |
|------|---------|
| `config.yaml` | Thresholds, budget, intervals |
| `channels.yaml` | 17 monitored YouTube channels |
| `keywords.yaml` | Weighted keyword groups |
| `poll.sh` | Main orchestrator |
| `lib/fetch_rss.py` | RSS fetch + Stage 1 filter |
| `lib/filter_stage2.py` | yt-dlp metadata scoring |
| `lib/trigger.sh` | claude -p invocation wrapper |
| `lib/state_manager.py` | Processed video state tracking |
| `lib/budget.py` | Daily spend tracking + circuit breaker |
| `skill/SKILL.md` | Vendored yt-intel skill (modified for unattended mode) |

## State files (gitignored)

- `state/processed.json` — Keyed by video ID, tracks scores + status
- `state/budget.json` — Daily spend tracking
- `logs/` — Daily log files

## Running

```bash
bash poll.sh --dry-run   # Test without triggering claude
bash poll.sh             # Single poll cycle
bash poll.sh --daemon    # Continuous polling
```
