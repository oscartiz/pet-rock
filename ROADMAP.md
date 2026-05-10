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
