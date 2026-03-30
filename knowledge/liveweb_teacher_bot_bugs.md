# LIVEWEB Teacher Bot — Remaining Issues

> Updated: 2026-03-30
> Code: liveweb-arena (unango/training branch, commit 8d09a9d)

## Fixed Bugs (in unango/training)

- ~~Bug 1: disabled plugins in composite~~ → Fixed: `include_plugins`/`exclude_plugins` params
- ~~Bug 2: content=null~~ → Fixed: `content: ""`
- ~~Bug 3: missing `tools` field~~ → Fixed: `tools` now in output
- ~~Bug 4: stooq hardcoded path~~ → Fixed: `os.environ["LIVEWEB_CACHE_DIR"]` set in `__init__`

## Still Needs Post-Processing

- `env` and `score` fields still missing at top level (only `tools` was added)
- Generation script must add `entry['env'] = 'LIVEWEB'` and `entry['score'] = entry['metadata']['score']`

## Operational Notes

- Stooq cache TTL (~24h) must be refreshed before generation: update `_fetched_at` in `_plugin_init/stooq_homepage.json`
- Use `include_plugins=['coingecko','hackernews','hybrid','stooq','taostats']` to exclude disabled plugins (openmeteo, openlibrary, arxiv)
