import base64
from datetime import datetime
from io import BytesIO

import asyncpg
from decouple import config
from fastapi import (
    Body,
    FastAPI,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
    status,
)
from fastapi.responses import JSONResponse, StreamingResponse
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


@app.get("/workers-courses/{worker_id}")
async def get_workers_courses(worker_id: int):
    async with app.state.db.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, worker_id, file, date_file, is_payed
            FROM workerscourses
            WHERE worker_id = $1
            """,
            worker_id,
        )

    if not rows:
        raise HTTPException(status_code=404, detail="Nenhum curso encontrado.")

    result = []

    for row in rows:
        file_base64 = base64.b64encode(row["file"]).decode("utf-8")

        result.append(
            {
                "id": row["id"],
                "worker_id": row["worker_id"],
                "date_file": row["date_file"],
                "is_payed": row["is_payed"],
                "file_base64": file_base64,
            }
        )

    return JSONResponse(content=result)


@app.get("/workers-courses/file/{file_id}")
async def get_workers_courses_by_file_id(file_id: int):
    async with app.state.db.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT file FROM workerscourses WHERE id = $1", file_id
        )

    if not row or not row["file"]:
        raise HTTPException(status_code=404, detail="Arquivo do curso não encontrado.")

    return StreamingResponse(
        BytesIO(row["file"]),
        media_type="application/pdf",
        headers={"Content-Disposition": "inline; filename=curso.pdf"},
    )


@app.post("/workers-courses")
async def upload_course(
    worker_id: int = Form(...),
    date_file: str = Form(...),
    is_payed: bool = Form(...),
    file: UploadFile = File(...),
):
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="O arquivo deve ser um PDF.")

    file_data = await file.read()

    async with app.state.db.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO workerscourses (worker_id, file, date_file, is_payed)
            VALUES ($1, $2, $3, $4)
            """,
            worker_id,
            file_data,
            date_file,
            is_payed,
        )

    return {"message": "Curso enviado e salvo com sucesso!"}


def serialize_row(row):
    row_dict = dict(row)
    for key, value in row_dict.items():
        if isinstance(value, bytes):
            row_dict[key] = base64.b64encode(value).decode("utf-8")
    return row_dict


@app.get("/workerscourses/current-month")
async def get_current_month_courses():
    current_year_month = datetime.now().strftime("%Y-%m")

    query = """
        SELECT wc.*, w.name AS worker_name, w.email AS worker_email
        FROM workerscourses wc
        JOIN workers w ON wc.worker_id = w.id
        WHERE wc.date_file SIMILAR TO '[0-9]{4}-[0-9]{2}-[0-9]{2}'
          AND TO_CHAR(TO_DATE(wc.date_file, 'YYYY-MM-DD'), 'YYYY-MM') = $1
    """

    async with app.state.db.acquire() as conn:
        rows = await conn.fetch(query, current_year_month)

    return [serialize_row(row) for row in rows]
