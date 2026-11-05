"""Explicit operator command: python -m app.db.setup_checkpoints."""

import asyncio

from app.graph.runtime import durable_graph


async def main() -> None:
    async with durable_graph(setup=True):
        pass
    print("Checkpoint schema setup complete.")


if __name__ == "__main__":
    asyncio.run(main())
