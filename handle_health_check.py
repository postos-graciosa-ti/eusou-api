import asyncio


async def handle_health_check():
    while True:
        print("[Health Check] App rodando normalmente.")

        await asyncio.sleep(30)
