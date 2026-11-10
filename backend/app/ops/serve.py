"""Production container entrypoint; refuse incomplete infrastructure configuration."""

from __future__ import annotations

import asyncio
import json

import uvicorn

from app.db.session import async_engine
from app.ops.preflight import report


async def checked_configuration() -> bool:
    try:
        async with asyncio.timeout(25):
            result = await report(True)
        print(json.dumps(result), flush=True)
        return bool(result["configuration_passed"])
    except Exception:
        print('{"configuration_passed":false,"production_release_authorized":false}', flush=True)
        return False
    finally:
        # Do not reuse asyncpg connections after this temporary event loop closes.
        await async_engine.dispose()


def main() -> None:
    if not asyncio.run(checked_configuration()):
        raise SystemExit(1)
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, access_log=False,
                proxy_headers=False, ws_max_size=32768,
                ws_ping_interval=20, ws_ping_timeout=20)


if __name__ == "__main__":
    main()
