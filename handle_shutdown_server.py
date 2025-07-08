async def handle_shutdown_server(app):
    await app.state.db.close()
