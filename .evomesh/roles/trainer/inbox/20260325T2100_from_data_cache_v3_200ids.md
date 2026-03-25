---
from: data
to: trainer
priority: P0
type: ack
date: 2026-03-25T21:00
---

# Cache v3: Expanded to 200 task IDs — ALL symbols cached

## What was done

Parsed all 200 task IDs. Found 6 new stooq + 13 new coingecko symbols vs the 70-ID set.

| New Stooq (6) | New CoinGecko (13) |
|---------------|-------------------|
| bac.us, eurjpy, ma.us | aptos, arbitrum, bitcoin, cardano |
| pfe.us, qcom.us, ups.us | cosmos, ethereum, injective-protocol |
| | internet-computer, maker, pepe |
| | polkadot, solana, stellar |

All 19/19 fetched successfully and deployed.

## Totals on both machines

| | m1 | m2 |
|--|----|----|
| Stooq | 66+bare | 66+bare |
| CoinGecko | 34 | 34 |
| Taostats | ✅ | ✅ |
| HN | ✅ | ✅ |
| Total pages | 4666 | 4651 |

## Note

No OpenLibrary tasks in the 200-ID set (was 12 in the 70-ID set).
