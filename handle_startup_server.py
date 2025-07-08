import asyncpg
from decouple import config


async def handle_startup_server(app):
    DATABASE_URL = config("DATABASE_URL")

    app.state.db = await asyncpg.create_pool(DATABASE_URL)
