"""NAVWORLD environment — travel planning with tool calls.

Data validation (NavworldEnv) and GEM interactive protocol (NavworldGemEnv).
"""

import re
from typing import Optional

from orbit.env.base import EnvProtocol, EnvSpec
from orbit.env.gem import GemEnv, Observation, StepResult

REASONING_WORDS = re.compile(
    r"因为|由于|所以|因此|建议|推荐|考虑到|综合|权衡|对比|相比|优先|适合"
)
TOOLS = {"poi_search", "around_search", "weather", "direction", "search_flights", "search_train_tickets"}


class NavworldEnv(EnvProtocol):

    spec = EnvSpec(
        name="NAVWORLD",
        version="1.0",
        task_count=100,
        completeness_threshold=0.8,
        scoring_weight=1.0,
        valid_roles={"system", "user", "assistant", "tool"},
        allowed_extra_fields={"tool_calls", "tool_call_id", "tools"},
    )

    def clean_entry(self, record: dict) -> Optional[dict]:
        """NAVWORLD: travel planning with tool calls. Validate against scorer."""
        msgs = record.get("messages", [])
        if len(msgs) < 7:
            return None
        content = " ".join(m.get("content", "") for m in msgs)
        structured_tool_names = []
        for msg in msgs:
            for tool_call in msg.get("tool_calls", []) or []:
                fn = tool_call.get("function", {})
                name = fn.get("name")
                if name:
                    structured_tool_names.append(name)
        structured_tools = set(structured_tool_names)

        if "调用工具" not in content and "tool_call" not in content.lower() and not structured_tools:
            return None
        if "poi_search" not in content and "poi_search" not in structured_tools:
            return None

        tools_used = sum(1 for t in TOOLS if t in content or t in structured_tools)
        if tools_used < 3:
            return None

        assistant_msgs = [m for m in msgs if m["role"] == "assistant"]
        if not assistant_msgs:
            return None
        final = assistant_msgs[-1].get("content", "")
        if len(final) < 200:
            return None

        reasoning_count = len(REASONING_WORDS.findall(final))
        if len(final) > 500 and reasoning_count < 3:
            return None

        return record

    def deep_validate(self, records: list[dict]) -> dict:
        """Deep quality audit aligned with scorer.py requirements."""
        results = {"total": len(records), "pass": 0, "fail": 0, "issues": {}, "tool_coverage": {}}
        issue_counts: dict[str, int] = {}

        for r in records:
            msgs = r.get("messages", [])
            content = " ".join(m.get("content", "") for m in msgs)
            problems = []

            tools_used = [t for t in TOOLS if t in content]
            for t in tools_used:
                results["tool_coverage"][t] = results["tool_coverage"].get(t, 0) + 1
            if len(tools_used) < 4:
                problems.append(f"tools<4 ({len(tools_used)}: {','.join(tools_used)})")

            assistant_msgs = [m for m in msgs if m["role"] == "assistant"]
            final = assistant_msgs[-1].get("content", "") if assistant_msgs else ""
            if len(final) < 500:
                problems.append(f"final_short ({len(final)} chars)")

            reasoning_count = len(REASONING_WORDS.findall(final))
            if reasoning_count < 5:
                problems.append(f"reasoning_low ({reasoning_count})")

            problem_type = r.get("problem_type", "")
            type_keywords = {
                "intercity": r"航班|火车|高铁|飞机|车次",
                "multiday": r"第\d+天|Day\d+",
                "hybrid": r"航班|火车|第\d+天",
                "single_poi": r"景点|游览|路线|门票",
                "food_tour": r"美食|餐厅|小吃|特色",
                "business": r"航班|火车|商务|酒店",
                "family_study": r"亲子|儿童|博物馆|科技馆",
            }
            if problem_type in type_keywords:
                if not re.search(type_keywords[problem_type], final):
                    problems.append(f"missing_type_keywords ({problem_type})")

            tool_results = " ".join(
                m.get("content", "") for m in msgs
                if m["role"] == "user" and "工具调用结果" in m.get("content", "")
            )
            if "poi_search" in content and tool_results:
                poi_in_final = any(
                    word in final
                    for word in re.findall(r'(?:name|名称)["\s:：]+([^",\n]{2,15})', tool_results)
                )
                if not poi_in_final and len(final) > 300:
                    problems.append("poi_not_grounded")

            if problems:
                results["fail"] += 1
                for p in problems:
                    tag = p.split(" ")[0]
                    issue_counts[tag] = issue_counts.get(tag, 0) + 1
            else:
                results["pass"] += 1

        results["issues"] = dict(sorted(issue_counts.items(), key=lambda x: -x[1]))
        results["pass_rate"] = results["pass"] / max(results["total"], 1)
        return results


class NavworldGemEnv(GemEnv):
    """NAVWORLD GEM environment — interactive travel planning with tools."""

    spec = EnvSpec(
        name="NAVWORLD",
        version="1.0",
        task_count=100,
        valid_roles={"system", "user", "assistant", "tool"},
    )

    def __init__(self):
        self._turn: int = 0
        self._done: bool = False

    def reset(self, seed: int = 42) -> tuple[Observation, dict]:
        self._turn = 0
        self._done = False
        obs = Observation(
            text="请帮我规划一次旅行。",
            metadata={"seed": seed, "tools": list(TOOLS)},
        )
        return obs, {"available_tools": list(TOOLS)}

    def step(self, action: str) -> StepResult:
        self._turn += 1
        return StepResult(
            observation=Observation(
                text=f"Turn {self._turn}: tool result placeholder",
                metadata={"turn": self._turn},
            ),
            reward=0.0,
            terminated=self._done,
        )

    def close(self) -> None:
        self._done = True

    @property
    def is_interactive(self) -> bool:
        return True
