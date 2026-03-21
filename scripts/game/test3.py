"""Run 3 games with full detail. Usage: python3 test3.py GAME_NAME [SEED]"""
import sys, json, re, os, random

game_name = sys.argv[1]
seed_start = int(sys.argv[2]) if len(sys.argv) > 2 else random.randint(1000000, 9999999)

sys.path.insert(0, "/root/game_gen/game")
sys.path.insert(0, "/root/game_gen")
os.chdir("/root/affinetes/environments/openspiel")

# Load bot
try:
    mod = __import__(f"{game_name}_bot")
    bot_func = getattr(mod, f"{game_name}_bot")
except:
    from game_bots import BOTS
    bot_func = BOTS.get(game_name)

# Use MCTS gen
from game_bot_gen_mcts import generate_game_trajectory

THINK_PAT = re.compile(r"<think>(.*?)</think>", re.DOTALL)
wins, losses = 0, 0

for i in range(3):
    seed = seed_start + i
    record = generate_game_trajectory(game_name, seed, bot_func)
    if not record:
        losses += 1
        continue
    won = record.get("won", record.get("score", 0) >= 0.5)
    if won: wins += 1
    else: losses += 1
    label = "WIN" if won else "LOSS"
    turns = sum(1 for m in record["messages"] if m["role"] == "assistant")
    print(f"\n{'='*60}")
    print(f"GAME {i+1}: {label} score={record['score']:.2f} turns={turns}")
    print(f"{'='*60}")
    for m in record["messages"][1:]:
        if m["role"] == "user":
            for l in m["content"].split("\n"):
                if any(k in l.lower() for k in ["dice","bid","liar","card","board","current","prize","hand","score","pot","round","knock","claim","stock","upcard","phase","deadwood","legal"]):
                    print(f"  STATE: {l.strip()[:160]}")
        else:
            think = THINK_PAT.search(m["content"])
            action = THINK_PAT.sub("", m["content"]).strip()
            if think: print(f"  THINK: {think.group(1).strip()[:300]}")
            print(f"  ACTION: {action}")
print(f"\nRESULT: {wins}W {losses}L")
