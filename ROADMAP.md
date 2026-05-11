# Roadmap

## Core Features

### Reply to feeders
When someone feeds the pet, automatically reply to their post with a mood-appropriate thank-you message. The reply should reflect the current hunger state — a starving pet replies very differently than a thriving one.

### Hunger milestones
Trigger special one-off posts at notable hunger events:
- First feed of the day
- Recovering from `critical` back to `hungry`
- Hitting 100 hunger (fully satiated)
- Going X hours without any feed

### Pet death & revival
If hunger stays at 0 for a configurable number of hours, the pet goes silent and publishes a final "last words" post. A sufficiently large ETH donation (configurable threshold) triggers a revival post and resets hunger to 50.

---

## Personality & Content

### Memory / RAG
Store a rolling window of recent interactions (mentions, feed events, replies) in a vector store. Inject relevant context into each generation call so the pet can reference specific feeders by name, recall past conversations, and build a sense of continuity over time.

### Image generation
Attach generated images to posts — ASCII art or AI-generated visuals of the rock in different moods. Cycle through a mood-matched image set or generate fresh ones via an image API.

### Seasonal & contextual events
Pull in external signals to influence personality:
- Time of day (drowsy at night, energetic in the morning)
- Day of the week or holidays
- Current weather at a fixed location via a weather API

---

## Social Mechanics

### Feeder leaderboard
Track cumulative hunger points contributed per Bluesky DID and ETH address in the DB. Periodically post a shoutout to the top feeder(s) of the week.

### Threaded conversations
Beyond just parsing feed signals, let the pet actively reply to interesting mentions — questions, philosophical provocations, or anyone who seems to be talking directly to it. Use the AI model to decide whether a mention warrants a reply.

---

## Fly.io Deployment (Haiku 4.5 — ~$9/year)

Target setup: Fly.io free tier + `claude-haiku-4-5`. Total estimated annual cost ~$9 (API only; hosting is free). The free tier includes 3 shared-cpu-1x 256 MB VMs — enough to run the always-on scheduler loop with headroom.

### fly.toml

```toml
app = "tee-peb"
primary_region = "iad"

[build]
  dockerfile = "Dockerfile"

[env]
  POST_INTERVAL_MINUTES = "30"
  HUNGER_DECAY_PER_HOUR = "3"
  MODEL = "claude-haiku-4-5"

[mounts]
  source = "petrock_data"
  destination = "/data"

[[services]]
  internal_port = 8080   # only needed if web dashboard is added later
  protocol = "tcp"

  [[services.tcp_checks]]
    grace_period = "5s"
    interval = "30s"
    restart_limit = 3
    timeout = "5s"
```

### Dockerfile

```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV DB_PATH=/data/petrock.db

CMD ["python", "main.py"]
```

`DB_PATH` must be read in `db.py` (currently hardcoded) so SQLite is written to the persistent Fly volume at `/data` rather than the ephemeral container filesystem.

### Secrets (set once via CLI, never committed)

```bash
fly secrets set \
  ANTHROPIC_API_KEY=... \
  BLUESKY_IDENTIFIER=... \
  BLUESKY_APP_PASSWORD=... \
  ETH_PRIVATE_KEY=... \
  ETH_RPC_URL=...
```

### Persistent volume

```bash
fly volumes create petrock_data --region iad --size 1   # 1 GB, free tier
```

The SQLite database, feed log, and post log all live here. Without this volume the DB resets on every deploy/restart.

### Deploy

```bash
fly launch          # first time — generates app + links volume
fly deploy          # subsequent deploys
fly logs            # tail live logs
```

### Code changes required before deploying

1. **`db.py`** — replace the hardcoded `petrock.db` path with `os.getenv("DB_PATH", "petrock.db")` so the volume path is respected.
2. **`brain.py`** — remove `cache_control: {"type": "ephemeral"}` from the system prompt dict. The ephemeral cache TTL is 5 minutes; posts fire every 30 minutes, so every call pays the cache-write premium with zero cache-read savings (~$3/year wasted on Sonnet, less on Haiku but still dead cost).
3. **`config.py`** — `MODEL` default is already read from env, so switching to Haiku only requires setting the `MODEL` env var in `fly.toml` (already shown above).

### Cost ceiling

| Item | Annual |
|---|---|
| Anthropic `claude-haiku-4-5` (17,520 calls @ ~310 in / ~60 out tokens) | ~$9 |
| Fly.io (free tier, 1 shared VM + 1 GB volume) | $0 |
| ETH RPC — Alchemy or Infura free tier (< 3K req/month) | $0 |
| Bluesky | $0 |
| **Total** | **~$9/year** |

Fly's free tier terms could change. Hetzner CX11 (~$50/year) is the fallback — the same Dockerfile and secrets work unchanged, just swap `fly deploy` for `docker compose up -d` behind a systemd service.

---

## Infrastructure

### Web dashboard
A lightweight read-only web page (FastAPI + plain HTML) showing:
- Live hunger bar and current mood
- Recent posts with timestamps
- Feed history (social and ETH)
- Wallet address with QR code

### Docker + systemd
Production-ready deployment:
- `Dockerfile` with a minimal Python image
- `docker-compose.yml` for easy local runs
- `petrock.service` systemd unit for auto-restart on reboot

### TEE upgrade
Wrap the agent in a Trusted Execution Environment (Intel TDX or AWS Nitro Enclaves) to provide cryptographic proof that no human can interfere after deployment — matching the original Nous Research experiment. Includes remote attestation so anyone can verify the agent is running unmodified code.

---

## Developer Experience

### `--dry-run` flag
Pass `--dry-run` to `main.py` to generate and print a post without publishing it. Useful for iterating on the personality prompt or testing mood transitions without spamming Bluesky.

### Test suite
Unit tests covering:
- Tamagotchi state machine (decay, feed caps, mood thresholds, anti-spam)
- Feed signal parsing (keyword and emoji detection)
- ETH hunger gain curve
- Post length enforcement in the brain
