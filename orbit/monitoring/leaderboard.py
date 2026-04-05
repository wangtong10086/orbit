"""Leaderboard tracking and display."""

import json
from typing import Optional

import aiohttp


class Leaderboard:
    """Fetch and display Affine leaderboard scores."""

    def __init__(self, api_url: str = "https://api.affine.io/api/v1"):
        self.api_url = api_url

    async def _fetch(self, session: aiohttp.ClientSession, endpoint: str) -> dict:
        url = f"{self.api_url}{endpoint}"
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            resp.raise_for_status()
            return await resp.json()

    async def fetch(self, top: int = 256) -> dict:
        """Fetch current leaderboard data."""
        async with aiohttp.ClientSession() as session:
            scores = await self._fetch(session, f"/scores/latest?top={top}")
            envs = await self._fetch(session, "/config/environments")
            return {"scores": scores, "environments": envs}

    def get_enabled_envs(self, data: dict) -> list[str]:
        """Get list of enabled scoring environments."""
        param_value = data["environments"].get("param_value", {})
        return sorted([
            name for name, cfg in param_value.items()
            if isinstance(cfg, dict) and cfg.get("enabled_for_scoring", False)
        ])

    def get_miners(self, data: dict, top: int = 50) -> list[dict]:
        """Get miner scores list."""
        return data["scores"].get("scores", [])[:top]

    def format_table(
        self,
        data: dict,
        env_filter: Optional[str] = None,
        hotkey_filter: Optional[str] = None,
        top: int = 50,
    ) -> str:
        """Format leaderboard as a text table."""
        scores_data = data["scores"]
        block = scores_data.get("block_number", "?")
        scores_list = scores_data.get("scores", [])

        enabled_envs = self.get_enabled_envs(data)

        if env_filter:
            env_upper = env_filter.upper()
            enabled_envs = [e for e in enabled_envs if env_upper in e.upper()]

        if hotkey_filter:
            scores_list = [s for s in scores_list if hotkey_filter in s.get("miner_hotkey", "")]

        lines = []
        sep = "=" * 120

        lines.append(f"\n{sep}")
        lines.append(f"  AFFINE LEADERBOARD - Block {block}")
        lines.append(sep)

        header = f"{'Rank':>4} {'UID':>4} {'Hotkey':8} {'Model':25} {'Weight':>10}"
        for env in enabled_envs:
            short = env.split(":")[-1] if ":" in env else env
            header += f" {short:>10}"
        lines.append(header)
        lines.append("-" * 120)

        for i, score in enumerate(scores_list[:top]):
            uid = score.get("uid", "?")
            hotkey = score.get("miner_hotkey", "?")[:8]
            model = (score.get("model", "?") or "?")[:25]
            weight = score.get("overall_score", 0.0)

            row = f"{i+1:>4} {uid:>4} {hotkey:8} {model:25} {weight:>10.6f}"

            scores_by_env = score.get("scores_by_env", {})
            for env in enabled_envs:
                if env in scores_by_env:
                    env_score = scores_by_env[env].get("score", 0.0)
                    count = scores_by_env[env].get("sample_count", 0)
                    row += f" {env_score*100:>6.2f}/{count:<3}"
                else:
                    row += f" {'---':>10}"
            lines.append(row)

        lines.append(sep)
        active = len([s for s in scores_list if s.get("overall_score", 0) > 0])
        lines.append(f"  Total: {len(scores_list)} miners | Active (weight>0): {active}")
        lines.append(f"{sep}\n")

        return "\n".join(lines)

    def format_json(self, data: dict, top: int = 50) -> str:
        """Format leaderboard as JSON."""
        return json.dumps({
            "block": data["scores"].get("block_number"),
            "environments": self.get_enabled_envs(data),
            "miners": data["scores"].get("scores", [])[:top],
        }, indent=2)

    def analyze_weaknesses(self, data: dict, top: int = 10) -> dict:
        """Analyze which environments are weakest across top miners."""
        envs = self.get_enabled_envs(data)
        miners = self.get_miners(data, top=top)

        env_avg = {}
        for env in envs:
            scores = []
            for m in miners:
                env_data = m.get("scores_by_env", {}).get(env, {})
                s = env_data.get("score", 0.0)
                if s > 0:
                    scores.append(s)
            if scores:
                env_avg[env] = sum(scores) / len(scores)

        return dict(sorted(env_avg.items(), key=lambda x: x[1]))
