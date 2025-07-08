import asyncio

import httpx
from decouple import config


async def handle_periodic_health_check():
    await asyncio.sleep(1)

    while True:
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(config("HEALTH_CHECK_ENDPOINT"))

                print(
                    f"[HEALTH CHECK] Status: {response.status_code} - {response.json()}"
                )

        except Exception as e:
            print(f"[HEALTH CHECK ERROR] {e}")

        await asyncio.sleep(30)
