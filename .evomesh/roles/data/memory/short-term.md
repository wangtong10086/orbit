# Short-term Memory

## Last active: 2026-03-25

### v2.23 LIVEWEB Score: 14-17 (noreason mode)
- m1: 17.50 (98 samples), m2: 13.96 (99 samples)
- Cache fix: errors 30%→7-13% ✅
- Null GT: 36-41% of answers (model stops too early)
- Model accuracy: 19-27% when GT available → **#1 bottleneck to 50+**

### Root Cause Analysis: Why Accuracy is Low
1. **Think blocks too vague**: training data says "Looking at the page content" instead of quoting exact values
2. **Taostats nearly all wrong**: model hallucinates subnet names (says "BitAds" for 3 different subnets)
3. **Computation errors**: percentages off 3x, volumes off 10x
4. **No multi-step reasoning**: stop entries have accumulated "Working Memory" but don't show how values were extracted

### Path to 50+
- Even with 0% errors + 0% null GT → max ~27 with current 27% accuracy
- Need accuracy from 27% → 50%+ → requires better training data quality
- Key: think blocks must teach PRECISE data extraction from accessibility_tree + explicit computation

### Cache v4: deployed on m1+m2
- 4528+ real pages, stealth fix in block_patterns.py (not yet pushed)
- Taostats subnet pages: Cloudflare CAPTCHA, partial success (3/11)

### HARD RULE: LIVEWEB ONLY
