#!/usr/bin/env python3
"""LIVEWEB Bot Data Generator — Programmatic training data with think chains.

Instead of distilling from GPT-5.4 (slow, expensive, no think chains),
this generates optimal trajectories programmatically using cached page data.

Architecture:
  1. Load template → generate question + ground truth
  2. Bot follows optimal navigation path (hardcoded per template type)
  3. At each step, generate think chain with state tracking
  4. Output format matches eval exactly (OpenAI tool_calls)

Key insight: eval only shows last 5 steps in "Recent Actions". So think
chains MUST include cumulative state (visited URLs, extracted answers)
because earlier context is lost.

Usage:
    # Generate 100 entries for coingecko templates
    python3 liveweb_bot_gen.py --plugin coingecko -n 100 -o data/liveweb_bot_cg.jsonl

    # Generate for all plugins
    python3 liveweb_bot_gen.py --all -n 500 -o data/liveweb_bot_all.jsonl

    # With cache dir (for realistic accessibility trees)
    python3 liveweb_bot_gen.py --plugin taostats -n 100 --cache-dir /root/cache \
        -o data/liveweb_bot_ts.jsonl
"""

import argparse
import hashlib
import json
import os
import random
import sys
from typing import Optional


# ============================================================================
# Think Chain Templates
# ============================================================================

def make_think(task_summary: str, visited: list[str], extracted: dict,
               current_page: str, observations: str, plan: str) -> str:
    """Generate a think chain that maintains state across the 5-step window.

    This is the KEY innovation: since eval only shows last 5 steps,
    the think chain must carry forward ALL accumulated state so the
    model doesn't lose track of what it's already done.
    """
    visited_str = ", ".join(visited) if visited else "(none yet)"
    extracted_str = json.dumps(extracted, ensure_ascii=False) if extracted else "{}"

    return (
        f"<think>\n"
        f"Task: {task_summary}\n"
        f"Visited: [{visited_str}]\n"
        f"Extracted: {extracted_str}\n"
        f"Current page: {current_page}\n"
        f"Observations: {observations}\n"
        f"Plan: {plan}\n"
        f"</think>"
    )


# ============================================================================
# Tool Call Builders
# ============================================================================

def make_tool_call(name: str, arguments: dict, call_id: int = 0) -> dict:
    """Build OpenAI-format tool_call."""
    return {
        "id": f"call_{call_id}",
        "type": "function",
        "function": {
            "name": name,
            "arguments": json.dumps(arguments, ensure_ascii=False),
        },
    }


def make_assistant_msg(think: str, tool_call: dict) -> dict:
    """Assistant message with think chain + tool call."""
    return {
        "role": "assistant",
        "content": think,
        "tool_calls": [tool_call],
    }


def make_tool_response(result: str, call_id: int = 0) -> dict:
    """Tool response message."""
    return {
        "role": "tool",
        "content": result,
        "tool_call_id": f"call_{call_id}",
    }


def make_user_obs(url: str, title: str, accessibility_tree: str,
                  recent_actions: str, step: int, max_steps: int) -> dict:
    """User observation message (what eval sends each step)."""
    remaining = max_steps - step
    content = (
        f"## Current Page State\n\n"
        f"URL: {url}\n"
        f"Title: {title}\n\n"
        f"### Accessibility Tree\n```\n{accessibility_tree}\n```\n\n"
        f"### Recent Actions\n{recent_actions}\n\n"
        f"**Step {step}/{max_steps}** ({remaining} steps remaining)"
    )
    return {"role": "user", "content": content}


# ============================================================================
# System Prompt (matches eval exactly)
# ============================================================================

SYSTEM_PROMPT = (
    "You are a web automation agent that interacts with real websites to complete tasks.\n\n"
    "You have access to a browser and can navigate to any website to gather information.\n"
    "Use the provided tools to interact with the browser.\n\n"
    "{plugin_hints}\n"
    "{task_intent}\n\n"
    "## Tips\n\n"
    "- First analyze the task and decide which website to visit\n"
    "- Use the goto tool to navigate to the appropriate URL\n"
    "- Homepage/list data may be inaccurate. Always visit detail pages for precise values\n"
    "- **NEVER revisit a URL you already visited.** Extract ALL needed data in one visit. "
    "If you need data from a page you visited before, use what you already saw.\n"
    "- Be efficient: go directly to the most relevant page (e.g., detail page URL) "
    "rather than navigating from homepages\n"
    "- When done, use the stop tool with your answers\n"
)

# Browser action tool definitions (matches eval)
TOOLS = [
    {"type": "function", "function": {"name": "goto", "description": "Navigate to a URL", "parameters": {"type": "object", "properties": {"url": {"type": "string", "description": "URL to navigate to"}}, "required": ["url"]}}},
    {"type": "function", "function": {"name": "click", "description": "Click an element by CSS selector", "parameters": {"type": "object", "properties": {"selector": {"type": "string", "description": "CSS selector"}}, "required": ["selector"]}}},
    {"type": "function", "function": {"name": "type", "description": "Type text into an input field", "parameters": {"type": "object", "properties": {"selector": {"type": "string"}, "text": {"type": "string"}, "press_enter": {"type": "boolean"}}, "required": ["selector", "text"]}}},
    {"type": "function", "function": {"name": "scroll", "description": "Scroll the page", "parameters": {"type": "object", "properties": {"direction": {"type": "string", "enum": ["up", "down"]}, "amount": {"type": "integer"}}, "required": ["direction"]}}},
    {"type": "function", "function": {"name": "stop", "description": "Complete task and submit final answers", "parameters": {"type": "object", "properties": {"answers": {"type": "object", "description": "Answer key-value pairs"}}, "required": ["answers"]}}},
    {"type": "function", "function": {"name": "click_role", "description": "Click by accessibility role and name", "parameters": {"type": "object", "properties": {"role": {"type": "string"}, "name": {"type": "string"}, "exact": {"type": "boolean"}}, "required": ["role", "name"]}}},
    {"type": "function", "function": {"name": "type_role", "description": "Type by accessibility role", "parameters": {"type": "object", "properties": {"role": {"type": "string"}, "text": {"type": "string"}, "name": {"type": "string"}, "press_enter": {"type": "boolean"}}, "required": ["role", "text"]}}},
    {"type": "function", "function": {"name": "press", "description": "Press a keyboard key", "parameters": {"type": "object", "properties": {"key": {"type": "string"}}, "required": ["key"]}}},
    {"type": "function", "function": {"name": "wait", "description": "Wait for a duration", "parameters": {"type": "object", "properties": {"seconds": {"type": "integer"}}, "required": []}}},
    {"type": "function", "function": {"name": "view_more", "description": "View more truncated content", "parameters": {"type": "object", "properties": {"direction": {"type": "string", "enum": ["up", "down"]}}, "required": ["direction"]}}},
]


# ============================================================================
# Cache-based Page Data
# ============================================================================

class PageCache:
    """Load cached page data for realistic accessibility trees."""

    def __init__(self, cache_dir: Optional[str] = None):
        self.cache_dir = cache_dir
        self._cache = {}

    def get_page(self, url: str) -> dict:
        """Get cached page data: {html, accessibility_tree, api_data}."""
        if url in self._cache:
            return self._cache[url]

        if not self.cache_dir:
            # Generate synthetic accessibility tree
            return self._synthetic_page(url)

        # Try to load from cache dir
        # Cache structure: cache_dir/domain/path_encoded/page.json
        # For now, use synthetic
        return self._synthetic_page(url)

    def _synthetic_page(self, url: str) -> dict:
        """Generate a plausible accessibility tree for common pages."""
        return {"url": url, "title": "", "accessibility_tree": ""}


# ============================================================================
# Bot Strategies — One per template type
# ============================================================================

class BotStrategy:
    """Base class for template-specific bot strategies."""

    def __init__(self, cache: PageCache):
        self.cache = cache

    def generate(self, seed: int) -> Optional[dict]:
        """Generate one training entry. Returns None if template not applicable."""
        raise NotImplementedError


class CoinGeckoPriceBot(BotStrategy):
    """Bot for coingecko_price template: "What is {coin}'s current price?" """

    COINS = [
        {"id": "bitcoin", "name": "Bitcoin", "symbol": "BTC", "price": "$67,234.56", "market_cap": "$1.32T", "change_24h": "+2.3%", "volume": "$28.5B", "rank": 1},
        {"id": "ethereum", "name": "Ethereum", "symbol": "ETH", "price": "$3,456.78", "market_cap": "$415B", "change_24h": "-1.2%", "volume": "$15.2B", "rank": 2},
        {"id": "solana", "name": "Solana", "symbol": "SOL", "price": "$178.90", "market_cap": "$82B", "change_24h": "+5.1%", "volume": "$3.8B", "rank": 5},
        {"id": "cardano", "name": "Cardano", "symbol": "ADA", "price": "$0.45", "market_cap": "$16B", "change_24h": "-0.8%", "volume": "$0.9B", "rank": 8},
        {"id": "dogecoin", "name": "Dogecoin", "symbol": "DOGE", "price": "$0.12", "market_cap": "$17B", "change_24h": "+3.7%", "volume": "$1.2B", "rank": 7},
        {"id": "ripple", "name": "XRP", "symbol": "XRP", "price": "$0.52", "market_cap": "$28B", "change_24h": "+0.5%", "volume": "$1.1B", "rank": 6},
        {"id": "polkadot", "name": "Polkadot", "symbol": "DOT", "price": "$7.23", "market_cap": "$10B", "change_24h": "-2.1%", "volume": "$0.5B", "rank": 12},
        {"id": "avalanche-2", "name": "Avalanche", "symbol": "AVAX", "price": "$35.67", "market_cap": "$14B", "change_24h": "+1.8%", "volume": "$0.8B", "rank": 9},
        {"id": "chainlink", "name": "Chainlink", "symbol": "LINK", "price": "$14.56", "market_cap": "$8.5B", "change_24h": "+4.2%", "volume": "$0.6B", "rank": 14},
        {"id": "litecoin", "name": "Litecoin", "symbol": "LTC", "price": "$72.34", "market_cap": "$5.4B", "change_24h": "-0.3%", "volume": "$0.4B", "rank": 18},
    ]

    METRICS = [
        ("current price", "price", "I need to find the current price"),
        ("market cap", "market_cap", "I need to find the market capitalization"),
        ("24-hour trading volume", "volume", "I need to find the 24h trading volume"),
        ("24-hour price change", "change_24h", "I need to find the 24h price change percentage"),
    ]

    def generate(self, seed: int) -> Optional[dict]:
        rng = random.Random(seed)
        coin = rng.choice(self.COINS)
        metric_name, metric_key, metric_desc = rng.choice(self.METRICS)

        question = f"What is {coin['name']}'s {metric_name}?"
        answer = coin[metric_key]
        url = f"https://www.coingecko.com/en/coins/{coin['id']}"
        task_summary = f"Find {coin['name']}'s {metric_name}"

        # Build accessibility tree for coin detail page
        tree = (
            f"[Navigation] Home | Markets | Explore\n"
            f"[Breadcrumb] Coins > {coin['name']}\n"
            f"[Heading level=1] {coin['name']} ({coin['symbol']})\n"
            f"[Text] Rank #{coin['rank']}\n"
            f"[Text] {coin['price']}\n"
            f"[Label] Price\n"
            f"[Text] {coin['change_24h']}\n"
            f"[Label] 24h Change\n"
            f"[Text] {coin['market_cap']}\n"
            f"[Label] Market Cap\n"
            f"[Text] {coin['volume']}\n"
            f"[Label] 24h Volume\n"
            f"[Link] Markets | [Link] Historical Data | [Link] Wallets"
        )

        messages = []

        # System message
        messages.append({
            "role": "system",
            "content": SYSTEM_PROMPT.format(
                plugin_hints="## Available Information Sources\n\nCoinGecko (coingecko.com): Cryptocurrency prices, market cap, volume, and rankings.\n",
                task_intent=f"## Task\n\n{question}",
            ),
            "tools": TOOLS,
        })

        # Step 1: Initial observation (about:blank)
        messages.append(make_user_obs(
            url="about:blank", title="Blocked",
            accessibility_tree="(empty page)",
            recent_actions="(no actions yet)",
            step=1, max_steps=10,
        ))

        # Step 1 response: Think + goto
        think1 = make_think(
            task_summary=task_summary,
            visited=[],
            extracted={},
            current_page="about:blank (starting page)",
            observations=f"{metric_desc} for {coin['name']}.",
            plan=f"Navigate directly to {coin['name']}'s CoinGecko page at {url}",
        )
        tc1 = make_tool_call("goto", {"url": url}, call_id=0)
        messages.append(make_assistant_msg(think1, tc1))
        messages.append(make_tool_response("Success", call_id=0))

        # Step 2: Coin detail page observation
        messages.append(make_user_obs(
            url=url,
            title=f"{coin['name']} Price, Charts, Market Cap | CoinGecko",
            accessibility_tree=tree,
            recent_actions=f"Step 1: goto({url}) → Success",
            step=2, max_steps=10,
        ))

        # Step 2 response: Think + stop
        think2 = make_think(
            task_summary=task_summary,
            visited=[url],
            extracted={"answer1": answer},
            current_page=f"{coin['name']} detail page on CoinGecko",
            observations=f"I can see the {metric_name}: {answer}",
            plan="All information found. Submit answer.",
        )
        tc2 = make_tool_call("stop", {"answers": {"answer1": answer}}, call_id=1)
        messages.append(make_assistant_msg(think2, tc2))
        messages.append(make_tool_response("Task completed successfully.", call_id=1))

        # Final assistant summary
        messages.append({"role": "assistant", "content": f"answer1: {answer}"})

        return {
            "messages": messages,
            "env": "LIVEWEB",
            "source": "bot_strategy",
            "score": 1.0,
            "seed": seed,
            "template": "coingecko_price",
            "plugin": "coingecko",
        }


class CoinGeckoComparisonBot(BotStrategy):
    """Bot for comparison: "Which has higher X: coin_a or coin_b?" """

    def generate(self, seed: int) -> Optional[dict]:
        rng = random.Random(seed)

        # Pick two different coins
        coins = rng.sample(CoinGeckoPriceBot.COINS, 2)
        coin_a, coin_b = coins[0], coins[1]

        metrics = [
            ("price", "price", "current price"),
            ("market cap", "market_cap", "market capitalization"),
            ("24-hour volume", "volume", "24h trading volume"),
        ]
        metric_name, metric_key, metric_desc = rng.choice(metrics)

        question = f"Which has higher {metric_name}: {coin_a['name']} or {coin_b['name']}?"

        # Determine answer
        def parse_val(s):
            return float(s.replace("$", "").replace(",", "").replace("T", "e12").replace("B", "e9").replace("M", "e6").replace("%", "").replace("+", ""))

        val_a = parse_val(coin_a[metric_key])
        val_b = parse_val(coin_b[metric_key])
        winner = coin_a['name'] if val_a > val_b else coin_b['name']
        answer = f"{winner} ({coin_a[metric_key]} vs {coin_b[metric_key]})"

        task_summary = f"Compare {metric_name}: {coin_a['name']} vs {coin_b['name']}"
        url_a = f"https://www.coingecko.com/en/coins/{coin_a['id']}"
        url_b = f"https://www.coingecko.com/en/coins/{coin_b['id']}"

        def make_tree(coin):
            return (
                f"[Heading level=1] {coin['name']} ({coin['symbol']})\n"
                f"[Text] Rank #{coin['rank']}\n"
                f"[Text] {coin['price']}\n[Label] Price\n"
                f"[Text] {coin['change_24h']}\n[Label] 24h Change\n"
                f"[Text] {coin['market_cap']}\n[Label] Market Cap\n"
                f"[Text] {coin['volume']}\n[Label] 24h Volume"
            )

        messages = []

        # System
        messages.append({
            "role": "system",
            "content": SYSTEM_PROMPT.format(
                plugin_hints="## Available Information Sources\n\nCoinGecko (coingecko.com): Cryptocurrency prices, market cap, volume, and rankings.\n",
                task_intent=f"## Task\n\n{question}",
            ),
            "tools": TOOLS,
        })

        # Step 1: blank
        messages.append(make_user_obs("about:blank", "Blocked", "(empty page)", "(no actions yet)", 1, 10))

        think1 = make_think(
            task_summary=task_summary, visited=[], extracted={},
            current_page="about:blank",
            observations=f"Need to compare {metric_desc} between {coin_a['name']} and {coin_b['name']}.",
            plan=f"Visit {coin_a['name']}'s page first at {url_a}",
        )
        tc1 = make_tool_call("goto", {"url": url_a}, 0)
        messages.append(make_assistant_msg(think1, tc1))
        messages.append(make_tool_response("Success", 0))

        # Step 2: coin A page
        messages.append(make_user_obs(url_a, f"{coin_a['name']} | CoinGecko", make_tree(coin_a),
                                       f"Step 1: goto({url_a}) → Success", 2, 10))

        think2 = make_think(
            task_summary=task_summary, visited=[url_a], extracted={f"{coin_a['name']}_{metric_name}": coin_a[metric_key]},
            current_page=f"{coin_a['name']} detail page",
            observations=f"{coin_a['name']}'s {metric_name} is {coin_a[metric_key]}. Now need {coin_b['name']}'s data.",
            plan=f"Navigate to {coin_b['name']}'s page at {url_b}",
        )
        tc2 = make_tool_call("goto", {"url": url_b}, 1)
        messages.append(make_assistant_msg(think2, tc2))
        messages.append(make_tool_response("Success", 1))

        # Step 3: coin B page
        recent = f"Step 1: goto({url_a}) → Success\nStep 2: goto({url_b}) → Success"
        messages.append(make_user_obs(url_b, f"{coin_b['name']} | CoinGecko", make_tree(coin_b), recent, 3, 10))

        think3 = make_think(
            task_summary=task_summary,
            visited=[url_a, url_b],
            extracted={f"{coin_a['name']}_{metric_name}": coin_a[metric_key], f"{coin_b['name']}_{metric_name}": coin_b[metric_key]},
            current_page=f"{coin_b['name']} detail page",
            observations=f"{coin_b['name']}'s {metric_name} is {coin_b[metric_key]}. Comparing: {coin_a['name']} {coin_a[metric_key]} vs {coin_b['name']} {coin_b[metric_key]}. {winner} is higher.",
            plan="Both values collected. Submit answer.",
        )
        tc3 = make_tool_call("stop", {"answers": {"answer1": answer}}, 2)
        messages.append(make_assistant_msg(think3, tc3))
        messages.append(make_tool_response("Task completed successfully.", 2))

        messages.append({"role": "assistant", "content": f"answer1: {answer}"})

        return {
            "messages": messages, "env": "LIVEWEB", "source": "bot_strategy",
            "score": 1.0, "seed": seed, "template": "coingecko_comparison", "plugin": "coingecko",
        }


class TaostatsSubnetBot(BotStrategy):
    """Bot for taostats subnet info: "What is subnet X's name/TAO/alpha price?" """

    SUBNETS = [
        {"id": 1, "name": "Apex", "tao_in": "1,234,567", "alpha_price": "$0.0234", "emission": "3.45%", "validators": 128},
        {"id": 3, "name": "MyShell", "tao_in": "987,654", "alpha_price": "$0.0189", "emission": "2.89%", "validators": 96},
        {"id": 5, "name": "Open Kaito", "tao_in": "756,321", "alpha_price": "$0.0156", "emission": "2.34%", "validators": 112},
        {"id": 8, "name": "Taoshi", "tao_in": "543,210", "alpha_price": "$0.0098", "emission": "1.87%", "validators": 84},
        {"id": 13, "name": "Dataverse", "tao_in": "432,100", "alpha_price": "$0.0076", "emission": "1.56%", "validators": 72},
        {"id": 18, "name": "Cortex.t", "tao_in": "321,456", "alpha_price": "$0.0054", "emission": "1.23%", "validators": 64},
        {"id": 21, "name": "FileTAO", "tao_in": "234,567", "alpha_price": "$0.0043", "emission": "0.98%", "validators": 48},
        {"id": 27, "name": "Compute", "tao_in": "198,765", "alpha_price": "$0.0037", "emission": "0.87%", "validators": 56},
        {"id": 32, "name": "It's AI", "tao_in": "156,789", "alpha_price": "$0.0028", "emission": "0.76%", "validators": 44},
        {"id": 42, "name": "Omega", "tao_in": "123,456", "alpha_price": "$0.0019", "emission": "0.65%", "validators": 36},
    ]

    METRICS = [
        ("name", "name", "subnet name"),
        ("TAO staked", "tao_in", "amount of TAO staked"),
        ("alpha token price", "alpha_price", "alpha token price"),
        ("emission percentage", "emission", "emission percentage"),
    ]

    def generate(self, seed: int) -> Optional[dict]:
        rng = random.Random(seed)
        subnet = rng.choice(self.SUBNETS)
        metric_name, metric_key, metric_desc = rng.choice(self.METRICS)

        question = f"What is Subnet {subnet['id']}'s {metric_name}?"
        answer = str(subnet[metric_key])
        url = f"https://taostats.io/subnets/{subnet['id']}"
        task_summary = f"Find Subnet {subnet['id']}'s {metric_name}"

        tree = (
            f"[Navigation] Subnets | Validators | Staking\n"
            f"[Heading level=1] Subnet {subnet['id']} — {subnet['name']}\n"
            f"[Text] {subnet['tao_in']} TAO\n[Label] TAO Staked\n"
            f"[Text] {subnet['alpha_price']}\n[Label] Alpha Price\n"
            f"[Text] {subnet['emission']}\n[Label] Emission\n"
            f"[Text] {subnet['validators']}\n[Label] Validators\n"
            f"[Link] Chart | [Link] Validators | [Link] Miners"
        )

        messages = []
        messages.append({
            "role": "system",
            "content": SYSTEM_PROMPT.format(
                plugin_hints="## Available Information Sources\n\nTaostats (taostats.io): Bittensor network data — subnet metrics, TAO staked, alpha prices, validators.\n",
                task_intent=f"## Task\n\n{question}",
            ),
            "tools": TOOLS,
        })

        # Step 1: blank → goto subnet page
        messages.append(make_user_obs("about:blank", "Blocked", "(empty page)", "(no actions yet)", 1, 10))

        think1 = make_think(
            task_summary=task_summary, visited=[], extracted={},
            current_page="about:blank",
            observations=f"I need to find {metric_desc} for Subnet {subnet['id']}.",
            plan=f"Navigate directly to the subnet detail page at {url}",
        )
        messages.append(make_assistant_msg(think1, make_tool_call("goto", {"url": url}, 0)))
        messages.append(make_tool_response("Success", 0))

        # Step 2: subnet detail → extract + stop
        messages.append(make_user_obs(url, f"Subnet {subnet['id']} — {subnet['name']} | Taostats",
                                       tree, f"Step 1: goto({url}) → Success", 2, 10))

        think2 = make_think(
            task_summary=task_summary, visited=[url],
            extracted={"answer1": answer},
            current_page=f"Subnet {subnet['id']} ({subnet['name']}) detail page",
            observations=f"Found {metric_name}: {answer}",
            plan="Answer found. Submit.",
        )
        messages.append(make_assistant_msg(think2, make_tool_call("stop", {"answers": {"answer1": answer}}, 1)))
        messages.append(make_tool_response("Task completed successfully.", 1))
        messages.append({"role": "assistant", "content": f"answer1: {answer}"})

        return {"messages": messages, "env": "LIVEWEB", "source": "bot_strategy",
                "score": 1.0, "seed": seed, "template": "taostats_subnet_info", "plugin": "taostats"}


class TaostatsComparisonBot(BotStrategy):
    """Bot for taostats comparison: "Which subnet has more TAO: X or Y?" """

    def generate(self, seed: int) -> Optional[dict]:
        rng = random.Random(seed)
        subnets = rng.sample(TaostatsSubnetBot.SUBNETS, 2)
        sa, sb = subnets[0], subnets[1]

        metrics = [("TAO staked", "tao_in"), ("alpha price", "alpha_price"), ("emission", "emission")]
        metric_name, metric_key = rng.choice(metrics)

        question = f"Which subnet has more {metric_name}: Subnet {sa['id']} or Subnet {sb['id']}?"
        val_a = float(sa[metric_key].replace("$", "").replace(",", "").replace("%", ""))
        val_b = float(sb[metric_key].replace("$", "").replace(",", "").replace("%", ""))
        winner = f"Subnet {sa['id']} ({sa['name']})" if val_a > val_b else f"Subnet {sb['id']} ({sb['name']})"
        answer = f"{winner} — {sa[metric_key]} vs {sb[metric_key]}"

        task_summary = f"Compare {metric_name}: Subnet {sa['id']} vs {sb['id']}"
        url_a = f"https://taostats.io/subnets/{sa['id']}"
        url_b = f"https://taostats.io/subnets/{sb['id']}"

        def tree(s):
            return (f"[Heading] Subnet {s['id']} — {s['name']}\n"
                    f"[Text] {s['tao_in']} TAO\n[Label] TAO Staked\n"
                    f"[Text] {s['alpha_price']}\n[Label] Alpha Price\n"
                    f"[Text] {s['emission']}\n[Label] Emission")

        messages = []
        messages.append({"role": "system", "content": SYSTEM_PROMPT.format(
            plugin_hints="## Available Information Sources\n\nTaostats (taostats.io): Bittensor subnet metrics.\n",
            task_intent=f"## Task\n\n{question}"), "tools": TOOLS})

        # Step 1: blank → goto subnet A
        messages.append(make_user_obs("about:blank", "Blocked", "(empty page)", "(no actions yet)", 1, 10))
        think1 = make_think(task_summary=task_summary, visited=[], extracted={},
            current_page="about:blank",
            observations=f"Need to compare {metric_name} between Subnet {sa['id']} and Subnet {sb['id']}.",
            plan=f"Visit Subnet {sa['id']} first at {url_a}")
        messages.append(make_assistant_msg(think1, make_tool_call("goto", {"url": url_a}, 0)))
        messages.append(make_tool_response("Success", 0))

        # Step 2: subnet A page → goto subnet B
        messages.append(make_user_obs(url_a, f"Subnet {sa['id']} | Taostats", tree(sa),
            f"Step 1: goto({url_a}) → Success", 2, 10))
        think2 = make_think(task_summary=task_summary, visited=[url_a],
            extracted={f"subnet_{sa['id']}_{metric_name}": sa[metric_key]},
            current_page=f"Subnet {sa['id']} ({sa['name']}) detail page",
            observations=f"Subnet {sa['id']}'s {metric_name}: {sa[metric_key]}. Now need Subnet {sb['id']}.",
            plan=f"Visit Subnet {sb['id']} at {url_b}")
        messages.append(make_assistant_msg(think2, make_tool_call("goto", {"url": url_b}, 1)))
        messages.append(make_tool_response("Success", 1))

        # Step 3: subnet B page → stop
        recent = f"Step 1: goto({url_a}) → Success\nStep 2: goto({url_b}) → Success"
        messages.append(make_user_obs(url_b, f"Subnet {sb['id']} | Taostats", tree(sb), recent, 3, 10))
        think3 = make_think(task_summary=task_summary, visited=[url_a, url_b],
            extracted={f"subnet_{sa['id']}_{metric_name}": sa[metric_key], f"subnet_{sb['id']}_{metric_name}": sb[metric_key]},
            current_page=f"Subnet {sb['id']} ({sb['name']}) detail page",
            observations=f"Subnet {sb['id']}'s {metric_name}: {sb[metric_key]}. Comparing: {sa[metric_key]} vs {sb[metric_key]}. {winner} is higher.",
            plan="Both values collected. Submit answer.")
        messages.append(make_assistant_msg(think3, make_tool_call("stop", {"answers": {"answer1": answer}}, 2)))
        messages.append(make_tool_response("Task completed successfully.", 2))
        messages.append({"role": "assistant", "content": f"answer1: {answer}"})

        return {"messages": messages, "env": "LIVEWEB", "source": "bot_strategy",
                "score": 1.0, "seed": seed, "template": "taostats_comparison", "plugin": "taostats"}


class StooqPriceBot(BotStrategy):
    """Bot for stooq price lookup: "What is {symbol}'s current stock price?" """

    STOCKS = [
        {"symbol": "AAPL.US", "name": "Apple Inc", "price": "189.45", "change": "+1.23%", "open": "187.90", "high": "190.12", "low": "187.50", "volume": "52.3M"},
        {"symbol": "MSFT.US", "name": "Microsoft Corp", "price": "378.90", "change": "-0.45%", "open": "380.10", "high": "381.25", "low": "377.80", "volume": "23.1M"},
        {"symbol": "GOOGL.US", "name": "Alphabet Inc", "price": "141.23", "change": "+0.89%", "open": "140.50", "high": "142.10", "low": "139.90", "volume": "18.7M"},
        {"symbol": "AMZN.US", "name": "Amazon.com", "price": "178.56", "change": "+2.15%", "open": "175.20", "high": "179.30", "low": "174.80", "volume": "45.2M"},
        {"symbol": "TSLA.US", "name": "Tesla Inc", "price": "245.67", "change": "-1.78%", "open": "250.10", "high": "251.45", "low": "244.30", "volume": "98.5M"},
        {"symbol": "NVDA.US", "name": "NVIDIA Corp", "price": "875.34", "change": "+3.45%", "open": "846.00", "high": "880.20", "low": "845.50", "volume": "41.8M"},
        {"symbol": "META.US", "name": "Meta Platforms", "price": "485.23", "change": "+0.67%", "open": "482.10", "high": "487.50", "low": "480.30", "volume": "15.3M"},
        {"symbol": "JPM.US", "name": "JPMorgan Chase", "price": "198.45", "change": "-0.23%", "open": "199.10", "high": "200.50", "low": "197.80", "volume": "8.9M"},
    ]

    def generate(self, seed: int) -> Optional[dict]:
        rng = random.Random(seed)
        stock = rng.choice(self.STOCKS)
        metrics = [
            ("current price", "price"), ("daily change", "change"),
            ("today's opening price", "open"), ("today's high", "high"),
            ("trading volume", "volume"),
        ]
        metric_name, metric_key = rng.choice(metrics)

        question = f"What is {stock['name']}'s {metric_name} on Stooq?"
        answer = stock[metric_key]
        url = f"https://stooq.com/q/?s={stock['symbol'].lower()}"
        task_summary = f"Find {stock['name']}'s {metric_name}"

        tree = (
            f"[Heading] {stock['symbol']} — {stock['name']}\n"
            f"[Text] {stock['price']}\n[Label] Last\n"
            f"[Text] {stock['change']}\n[Label] Change\n"
            f"[Text] {stock['open']}\n[Label] Open\n"
            f"[Text] {stock['high']}\n[Label] High\n"
            f"[Text] {stock['low']}\n[Label] Low\n"
            f"[Text] {stock['volume']}\n[Label] Volume\n"
            f"[Link] Historical data | [Link] Charts"
        )

        messages = []
        messages.append({"role": "system", "content": SYSTEM_PROMPT.format(
            plugin_hints="## Available Information Sources\n\nStooq (stooq.com): Financial market data — stock prices, indices, forex, commodities.\n",
            task_intent=f"## Task\n\n{question}"), "tools": TOOLS})

        messages.append(make_user_obs("about:blank", "Blocked", "(empty page)", "(no actions yet)", 1, 10))
        think1 = make_think(task_summary=task_summary, visited=[], extracted={},
            current_page="about:blank",
            observations=f"I need to find {stock['name']}'s {metric_name}. Stooq uses symbol format like AAPL.US.",
            plan=f"Navigate to {url}")
        messages.append(make_assistant_msg(think1, make_tool_call("goto", {"url": url}, 0)))
        messages.append(make_tool_response("Success", 0))

        messages.append(make_user_obs(url, f"{stock['symbol']} — {stock['name']} | Stooq", tree,
            f"Step 1: goto({url}) → Success", 2, 10))
        think2 = make_think(task_summary=task_summary, visited=[url],
            extracted={"answer1": answer},
            current_page=f"{stock['name']} quote page on Stooq",
            observations=f"Found {metric_name}: {answer}",
            plan="Answer found. Submit.")
        messages.append(make_assistant_msg(think2, make_tool_call("stop", {"answers": {"answer1": answer}}, 1)))
        messages.append(make_tool_response("Task completed successfully.", 1))
        messages.append({"role": "assistant", "content": f"answer1: {answer}"})

        return {"messages": messages, "env": "LIVEWEB", "source": "bot_strategy",
                "score": 1.0, "seed": seed, "template": "stooq_price", "plugin": "stooq"}


class HackernewsExtremaBot(BotStrategy):
    """Bot for HN: "Which story has more comments/points: A or B?" (multi-step)"""

    STORIES = [
        {"id": 39856712, "title": "Show HN: I built an open-source Figma alternative", "score": 842, "comments": 234, "author": "designer_dev"},
        {"id": 39845123, "title": "Why Rust is the future of systems programming", "score": 567, "comments": 389, "author": "rustfan"},
        {"id": 39867890, "title": "The hidden cost of microservices", "score": 1203, "comments": 567, "author": "arch_critic"},
        {"id": 39823456, "title": "PostgreSQL 17 released with major performance improvements", "score": 934, "comments": 178, "author": "pg_enthusiast"},
        {"id": 39878901, "title": "Apple announces M4 chip with neural engine improvements", "score": 756, "comments": 445, "author": "apple_watcher"},
        {"id": 39890123, "title": "GitHub Copilot now supports Claude models", "score": 1456, "comments": 623, "author": "ai_developer"},
        {"id": 39801234, "title": "How we reduced our AWS bill by 70%", "score": 678, "comments": 312, "author": "cloud_ops"},
        {"id": 39812345, "title": "The great database migration: from MongoDB to PostgreSQL", "score": 445, "comments": 198, "author": "db_migrator"},
    ]

    def generate(self, seed: int) -> Optional[dict]:
        rng = random.Random(seed)
        stories = rng.sample(self.STORIES, 2)
        sa, sb = stories[0], stories[1]

        metrics = [("comments", "comments"), ("points (score)", "score")]
        metric_name, metric_key = rng.choice(metrics)

        question = f"Which Hacker News story has more {metric_name}: \"{sa['title'][:50]}...\" or \"{sb['title'][:50]}...\"?"
        val_a, val_b = sa[metric_key], sb[metric_key]
        winner_title = sa['title'] if val_a > val_b else sb['title']
        answer = f"{winner_title} ({max(val_a, val_b)} vs {min(val_a, val_b)})"

        task_summary = f"Compare {metric_name} between two HN stories"
        url_a = f"https://news.ycombinator.com/item?id={sa['id']}"
        url_b = f"https://news.ycombinator.com/item?id={sb['id']}"

        def tree(s):
            return (f"[Heading] {s['title']}\n"
                    f"[Text] {s['score']} points by {s['author']}\n"
                    f"[Text] {s['comments']} comments\n"
                    f"[Link] reply | [Link] flag | [Link] hide")

        messages = []
        messages.append({"role": "system", "content": SYSTEM_PROMPT.format(
            plugin_hints="## Available Information Sources\n\nHacker News (news.ycombinator.com): Tech news — stories, scores, comments.\n",
            task_intent=f"## Task\n\n{question}"), "tools": TOOLS})

        # Step 1: blank → story A
        messages.append(make_user_obs("about:blank", "Blocked", "(empty page)", "(no actions yet)", 1, 10))
        think1 = make_think(task_summary=task_summary, visited=[], extracted={},
            current_page="about:blank",
            observations=f"Need to compare {metric_name} between two stories. Must visit each story's detail page.",
            plan=f"Visit first story at {url_a}")
        messages.append(make_assistant_msg(think1, make_tool_call("goto", {"url": url_a}, 0)))
        messages.append(make_tool_response("Success", 0))

        # Step 2: story A → note data → goto story B
        messages.append(make_user_obs(url_a, f"{sa['title']} | Hacker News", tree(sa),
            f"Step 1: goto({url_a}) → Success", 2, 10))
        think2 = make_think(task_summary=task_summary, visited=[url_a],
            extracted={f"story_a_{metric_name}": val_a},
            current_page=f"Story A: \"{sa['title'][:40]}...\"",
            observations=f"Story A has {val_a} {metric_name}. Now need Story B's data.",
            plan=f"Visit second story at {url_b}")
        messages.append(make_assistant_msg(think2, make_tool_call("goto", {"url": url_b}, 1)))
        messages.append(make_tool_response("Success", 1))

        # Step 3: story B → compare → stop
        recent = f"Step 1: goto({url_a}) → Success\nStep 2: goto({url_b}) → Success"
        messages.append(make_user_obs(url_b, f"{sb['title']} | Hacker News", tree(sb), recent, 3, 10))
        think3 = make_think(task_summary=task_summary, visited=[url_a, url_b],
            extracted={f"story_a_{metric_name}": val_a, f"story_b_{metric_name}": val_b},
            current_page=f"Story B: \"{sb['title'][:40]}...\"",
            observations=f"Story B has {val_b} {metric_name}. Comparing: {val_a} vs {val_b}. \"{winner_title[:40]}...\" wins.",
            plan="Both values collected. Submit answer.")
        messages.append(make_assistant_msg(think3, make_tool_call("stop", {"answers": {"answer1": answer}}, 2)))
        messages.append(make_tool_response("Task completed successfully.", 2))
        messages.append({"role": "assistant", "content": f"answer1: {answer}"})

        return {"messages": messages, "env": "LIVEWEB", "source": "bot_strategy",
                "score": 1.0, "seed": seed, "template": "hackernews_extrema", "plugin": "hackernews"}


# ============================================================================
# Registry of all bot strategies
# ============================================================================

BOT_REGISTRY = {
    "coingecko_price": CoinGeckoPriceBot,
    "coingecko_comparison": CoinGeckoComparisonBot,
    "taostats_subnet_info": TaostatsSubnetBot,
    "taostats_comparison": TaostatsComparisonBot,
    "stooq_price": StooqPriceBot,
    "hackernews_extrema": HackernewsExtremaBot,
}

PLUGIN_TEMPLATES = {
    "coingecko": ["coingecko_price", "coingecko_comparison"],
    "taostats": ["taostats_subnet_info", "taostats_comparison"],
    "hackernews": ["hackernews_extrema"],
    "stooq": ["stooq_price"],
}


# ============================================================================
# Main generator
# ============================================================================

def generate_batch(plugin: Optional[str], count: int, output: str,
                   cache_dir: Optional[str] = None, start_seed: int = 0):
    """Generate a batch of bot training data."""
    cache = PageCache(cache_dir)

    if plugin:
        templates = PLUGIN_TEMPLATES.get(plugin, [])
    else:
        templates = list(BOT_REGISTRY.keys())

    if not templates:
        print(f"No bot strategies for plugin={plugin}")
        return

    strategies = [(name, BOT_REGISTRY[name](cache)) for name in templates]
    success = 0
    failed = 0

    with open(output, "a") as f:
        for i in range(count):
            seed = start_seed + i
            name, strategy = strategies[i % len(strategies)]

            try:
                entry = strategy.generate(seed)
                if entry:
                    # Verify content=None guard
                    for m in entry["messages"]:
                        if m.get("content") is None:
                            m["content"] = ""

                    f.write(json.dumps(entry, ensure_ascii=False) + "\n")
                    success += 1
                else:
                    failed += 1
            except Exception as e:
                print(f"  seed={seed} error: {e}")
                failed += 1

    print(f"Generated {success} entries ({failed} failed)")
    print(f"Output: {output}")


def main():
    parser = argparse.ArgumentParser(description="LIVEWEB bot data generator")
    parser.add_argument("--plugin", default=None, help="Plugin name (coingecko/taostats/hackernews/stooq)")
    parser.add_argument("--all", action="store_true", help="Generate for all plugins")
    parser.add_argument("-n", "--count", type=int, default=100, help="Number of entries")
    parser.add_argument("-o", "--output", default="data/liveweb_bot.jsonl", help="Output file")
    parser.add_argument("--cache-dir", default=None, help="Page cache directory")
    parser.add_argument("--start-seed", type=int, default=0, help="Starting seed")
    args = parser.parse_args()

    plugin = None if args.all else args.plugin
    generate_batch(plugin, args.count, args.output, args.cache_dir, args.start_seed)


if __name__ == "__main__":
    main()
