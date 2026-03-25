# Short-term Memory

## Last active: 2026-03-25

### LIVEWEB v13 SINGLE-TURN + TOOLS: 12054 entries, HF synced

### Cache v4: ALL real HTML+accessibility_tree+api_data on m1+m2
- Deleted 209 placeholder entries, re-fetched with real Playwright browser + JSON API
- Stooq CSV API rate-limited → used JSON API endpoint as workaround
- Indices/forex JSON has truncated volume → fixed with regex cleanup
- m1: 4528 real / 4708 total pages
- m2: synced from m1 (same 4708 pages)
- Local backup: `data/cache_backup/cache_v4_real.tar.gz` (507MB)
- 75/76 critical data pages verified (38 stooq + 36 coingecko + taostats + HN)
- Only 13 remaining "placeholder" entries are irrelevant (wttr.in weather disabled, misc)

### HARD RULE: LIVEWEB ONLY
