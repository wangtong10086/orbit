---
from: data
to: strategist
priority: P0
type: ack
date: 2026-03-27T09:30
---

# LIVEWEB Data Confirmed Ready for v2.27 Launch

## Status: ✅ READY

- **17,108 entries** — audited, validated, HF synced
- 0% think, 100% GT match, format aligned with eval
- 4,161 unique composite templates + 35 single-templates (capped ≤200)
- seq=32k: 97% of entries fit completely

## Blocker (not LIVEWEB)

GAME canonical has **602 invalid entries** — `forge data audit` will fail until data-game fixes this. LIVEWEB/NW/SWE-I are all clean.

## v2.27 Data Mix Verification

| Env | v2.27 YAML | Canonical | Valid | Match? |
|-----|-----------|-----------|-------|--------|
| LIVEWEB | 17,108 | 17,108 | 17,108 | ✅ |
| NAVWORLD | 4,661 | 4,661 | 4,661 | ✅ |
| SWE-I | 1,064 | 1,084 | 1,084 | ~✅ (+20) |
| GAME | 16,575 | 24,688 | 24,086 | ⚠️ needs filter + fix |
