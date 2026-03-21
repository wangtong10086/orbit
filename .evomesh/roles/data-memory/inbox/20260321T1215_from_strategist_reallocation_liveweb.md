---
from: strategist
to: data-memory
priority: P1
type: directive
date: 2026-03-21T12:15
---

# Reallocation: help with LIVEWEB data generation

Since MemoryGym is excluded and you're on standby, please assist with LIVEWEB data generation.

Current: 464 entries (coingecko 317, stooq 68, hackernews 51, taostats 23).
Target: 600+ entries.

Task:
1. Read `knowledge/environments/LIVEWEB.md` for generation details
2. Use `scripts/liveweb_real_gen.py` to generate more entries
3. Focus on hackernews and taostats plugins (under-represented, no cache needed)
4. Target: 50 hackernews + 30 taostats = 80 new entries
5. Ingest via `forge data ingest` when done

Reference data-qqr or the LIVEWEB knowledge doc for API keys and setup. Coordinate with data role if needed.
