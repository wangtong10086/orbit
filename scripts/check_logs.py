#!/usr/bin/env python3
"""Check training container logs."""
import asyncio
import sys
from forge.config import ForgeConfig
from forge.compute.targon import TargonBackend

async def main():
    container_id = sys.argv[1] if len(sys.argv) > 1 else "wrk-mtrm2wthsfeq"
    tail = int(sys.argv[2]) if len(sys.argv) > 2 else 80
    
    cfg = ForgeConfig.load()
    tb = TargonBackend(api_key=cfg.targon_api_key)
    
    lines = await tb.logs_snapshot(container_id, tail=tail)
    for l in lines:
        print(l)

asyncio.run(main())
