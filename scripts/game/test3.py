"""Run N games with full detail, concurrently.
Usage: python3 test3.py GAME_NAME [SEED] [N_GAMES] [CONCURRENCY]
"""
import sys, json, re, os, random
from concurrent.futures import ProcessPoolExecutor, as_completed

game_name = sys.argv[1]
seed_start = int(sys.argv[2]) if len(sys.argv) > 2 else random.randint(1000000, 9999999)
n_games = int(sys.argv[3]) if len(sys.argv) > 3 else 3
max_workers = int(sys.argv[4]) if len(sys.argv) > 4 else 10

THINK_PAT = re.compile(r"<think>(.*?)</think>", re.DOTALL)


def play_one(args):
    """Play one game in a subprocess."""
    game_name, seed = args
    # Re-import in subprocess
    import sys, os
    sys.path.insert(0, "/root/project/scripts/game")
    sys.path.insert(0, "/root/project/scripts")
    os.chdir("/root/affinetes/environments/openspiel")

    try:
        mod = __import__(f"{game_name}_bot")
        bot_func = getattr(mod, f"{game_name}_bot")
    except:
        from game_bots import BOTS
        bot_func = BOTS.get(game_name)

    from game_bot_gen_mcts import generate_game_trajectory
    record = generate_game_trajectory(game_name, seed, bot_func)
    return seed, record


if __name__ == "__main__":
    tasks = [(game_name, seed_start + i) for i in range(n_games)]
    results = []

    workers = min(max_workers, n_games)
    with ProcessPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(play_one, t): t for t in tasks}
        for future in as_completed(futures):
            seed, record = future.result()
            results.append((seed, record))

    # Sort by seed for consistent output
    results.sort(key=lambda x: x[0])

    wins, losses = 0, 0
    for i, (seed, record) in enumerate(results):
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
