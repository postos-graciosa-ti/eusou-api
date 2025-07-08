import base64
from io import BytesIO

from fastapi import Body, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse
from passlib.hash import pbkdf2_sha256

from models.auth import AuthData, PasswordChangeRequest
from security.create_access_token import create_access_token
from security.verify_token import verify_token


async def handle_get_worker_by_login(app, cpf: str, auth: AuthData = Body(...)):
    query = """
        SELECT * FROM workers
        WHERE app_login = $1 AND is_active = true
        LIMIT 1
    """

    async with app.state.db.acquire() as conn:
        row = await conn.fetchrow(query, auth.app_login)

    if not row:
        raise HTTPException(status_code=401, detail="Login ou senha inválidos")

    worker_dict = dict(row)

    if not pbkdf2_sha256.verify(auth.app_password, worker_dict["app_password"]):
        raise HTTPException(status_code=401, detail="Login ou senha inválidos")

    token = create_access_token(data={"sub": str(worker_dict["id"])})

    return {
        "access_token": token,
        "token_type": "bearer",
        "worker_data": worker_dict,
        "need_change_password": pbkdf2_sha256.verify(
            worker_dict["cpf"], worker_dict["app_password"]
        ),
    }


async def handle_get_workers_courses_by_file_id(app, file_id: int):
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


async def handle_get_scales_by_subsidiarie_and_worker_id(
    app, subsidiarie_id: int, worker_id: int
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


async def handle_patch_workers_data(app, worker_id: int, data: dict = Body(...)):
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


async def handle_patch_change_password(
    app, cpf: str, payload: PasswordChangeRequest = Body(...)
):
    async with app.state.db.acquire() as conn:
        query = "SELECT app_password FROM workers WHERE cpf = $1 AND is_active = true"

        row = await conn.fetchrow(query, cpf)

        if not row:
            raise HTTPException(status_code=404, detail="Worker not found")

        current_password_db = row["app_password"]

        if not pbkdf2_sha256.verify(payload.current_password, current_password_db):
            raise HTTPException(status_code=401, detail="Senha atual incorreta")

        new_password_hashed = pbkdf2_sha256.hash(payload.new_password)

        await conn.execute(
            "UPDATE workers SET app_password = $1 WHERE cpf = $2",
            new_password_hashed,
            cpf,
        )

        return {"message": "Senha atualizada com sucesso"}


async def handle_get_workers_courses(app, worker_id: int):
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


async def handle_upload_course(
    app,
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
