import asyncpg
from decouple import config
from fastapi import Body, FastAPI, HTTPException, status
from passlib.hash import pbkdf2_sha256
from pydantic import BaseModel

from middlewares.add_cors_middleware import add_cors_middleware

app = FastAPI()

DATABASE_URL = config("DATABASE_URL")

add_cors_middleware(app)


@app.on_event("startup")
async def startup():
    app.state.db = await asyncpg.create_pool(DATABASE_URL)


@app.on_event("shutdown")
async def shutdown():
    await app.state.db.close()


@app.get("/")
async def get_docs():
    return {"docs": "see /docs", "redoc": "see /redoc"}


class AuthData(BaseModel):
    app_login: str
    app_password: str


@app.post("/eusou/workers/{cpf}")
async def get_worker_by_login(cpf: str, auth: AuthData = Body(...)):
    query = """
        SELECT * FROM workers
        WHERE app_login = $1
          AND is_active = true
        LIMIT 1
    """

    async with app.state.db.acquire() as conn:
        row = await conn.fetchrow(query, auth.app_login)

    if not row:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Login ou senha inválidos",
        )

    worker_dict = dict(row)

    if not pbkdf2_sha256.verify(auth.app_password, worker_dict["app_password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Login ou senha inválidos",
        )

    return {
        "success": True,
        "worker_data": worker_dict,
        "need_change_password": pbkdf2_sha256.verify(
            worker_dict["cpf"], worker_dict["app_password"]
        ),
    }


@app.post("/eusou/subsidiaries/{subsidiarie_id}/workers/{worker_id}/scales")
async def handle_get_scales_by_subsidiarie_and_worker_id(
    subsidiarie_id: int, worker_id: int
):
    query = """
        SELECT days_off, ilegal_dates
        FROM scale
        WHERE subsidiarie_id = $1 AND worker_id = $2
        LIMIT 1
    """

    async with app.state.db.acquire() as conn:
        row = await conn.fetchrow(query, subsidiarie_id, worker_id)

    if not row:
        return {"days_off": [], "ilegal_dates": []}

    return {
        "days_off": eval(row["days_off"]),
        "ilegal_dates": eval(row["ilegal_dates"]),
    }


@app.patch("/eusou/workers/update-data/{worker_id}")
async def patch_workers_data(worker_id: int, data: dict = Body(...)):
    async with app.state.db.acquire() as conn:
        existing = await conn.fetchrow("SELECT * FROM workers WHERE id = $1", worker_id)

        if not existing:
            raise HTTPException(status_code=404, detail="Worker not found")

        fields = []
        values = []

        for i, (key, value) in enumerate(data.items(), start=1):
            fields.append(f"{key} = ${i}")
            values.append(value)

        if not fields:
            return {"message": "No fields to update", "worker": dict(existing)}

        values.append(worker_id)
        set_clause = ", ".join(fields)

        update_query = (
            f"UPDATE workers SET {set_clause} WHERE id = ${len(values)} RETURNING *"
        )

        updated = await conn.fetchrow(update_query, *values)

        return {"message": "Worker updated successfully", "worker": dict(updated)}


class PasswordChangeRequest(BaseModel):
    current_password: str
    new_password: str


@app.patch("/eusou/workers/{cpf}/change-password")
async def patch_change_password(cpf: str, payload: PasswordChangeRequest = Body(...)):
    async with app.state.db.acquire() as conn:
        query = "SELECT app_password FROM workers WHERE cpf = $1 AND is_active = true"

        row = await conn.fetchrow(query, cpf)

        if not row:
            raise HTTPException(status_code=404, detail="Worker not found")

        current_password_db = row["app_password"]

        try:
            if not pbkdf2_sha256.verify(payload.current_password, current_password_db):
                raise HTTPException(
                    status_code=401, detail="Current password is incorrect"
                )

        except Exception:
            raise HTTPException(status_code=401, detail="Current password is incorrect")

        new_password_hashed = pbkdf2_sha256.hash(payload.new_password)

        update_query = "UPDATE workers SET app_password = $1 WHERE cpf = $2"

        await conn.execute(update_query, new_password_hashed, cpf)

        return {"message": "Password updated successfully"}
