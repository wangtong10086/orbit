# Short-term Memory

## Last active: 2026-03-25

### Two Root Causes Found → Path to 50+

**Fix 1 (DONE): Stooq cache symbol case** — 49 entries lowercased on m1+m2
- Verified: score 14→36.8 (6/20 samples)
- No code change needed — cache data fixed to match official code expectations

**Fix 2 (AWAITING OFFICIAL): Taostats table rendering**
- 97.6% of taostats accessibility trees show "No Rows To Show" — both in training and eval
- Root cause: Playwright captures tree before React/AG Grid renders table
- Fix: `setup_page_for_cache()` must `wait_for_selector` for actual table rows
- Impact: taostats 9% accuracy → 40%+ = +15-20 score points
- Documented in `knowledge/liveweb_fundamental_fixes.md`

### Score Projection: 14 → 50+
| Fix | Impact | Cumulative |
|-----|--------|-----------|
| Stooq cache case (DONE) | +20 | ~35 |
| Taostats rendering (PENDING) | +15-20 | ~50-55 |

### Official Code Updates (pulled)
- `5f30f36`: stooq URL normalization (aapl→aapl.us)
- `1d03905`: stale cache fallback (don't delete expired data)
- training branch: teacher bot think quality fixes (commits c385bd3, 60c12c9)

### HARD RULE: LIVEWEB ONLY
