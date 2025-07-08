import asyncio
import base64
import threading
from datetime import datetime
from io import BytesIO

from fastapi import (
    Body,
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    UploadFile,
)
from fastapi.responses import JSONResponse, StreamingResponse
from passlib.hash import pbkdf2_sha256

from controllers.docs import handle_get_docs
from controllers.workers import (
    handle_get_scales_by_subsidiarie_and_worker_id,
    handle_get_worker_by_login,
    handle_get_workers_courses,
    handle_get_workers_courses_by_file_id,
    handle_patch_change_password,
    handle_patch_workers_data,
    handle_upload_course,
)
from handle_health_check import handle_health_check
from handle_shutdown_server import handle_shutdown_server
from handle_startup_server import handle_startup_server
from middlewares.add_cors_middleware import add_cors_middleware
from models.auth import AuthData, PasswordChangeRequest
from security.create_access_token import create_access_token
from security.verify_token import verify_token

app = FastAPI()

add_cors_middleware(app)


@app.on_event("startup")
async def startup():
    asyncio.create_task(handle_health_check())

    await handle_startup_server(app)


@app.on_event("shutdown")
async def shutdown():
    await handle_shutdown_server(app)


# public routes


@app.get("/")
async def get_docs():
    return await handle_get_docs()


@app.post("/eusou/workers/{cpf}")
async def get_worker_by_login(cpf: str, auth: AuthData = Body(...)):
    return await handle_get_worker_by_login(app, cpf, auth)


@app.get("/workers-courses/file/{file_id}")
async def get_workers_courses_by_file_id(file_id: int):
    return await handle_get_workers_courses_by_file_id(app, file_id)


# private routes


@app.post(
    "/eusou/subsidiaries/{subsidiarie_id}/workers/{worker_id}/scales",
    dependencies=[Depends(verify_token)],
)
async def get_scales_by_subsidiarie_and_worker_id(subsidiarie_id: int, worker_id: int):
    return await handle_get_scales_by_subsidiarie_and_worker_id(
        app, subsidiarie_id, worker_id
    )


@app.patch(
    "/eusou/workers/update-data/{worker_id}", dependencies=[Depends(verify_token)]
)
async def patch_workers_data(worker_id: int, data: dict = Body(...)):
    return await handle_patch_workers_data(app, worker_id, data)


@app.patch("/eusou/workers/{cpf}/change-password", dependencies=[Depends(verify_token)])
async def patch_change_password(cpf: str, payload: PasswordChangeRequest = Body(...)):
    return await handle_patch_change_password(app, cpf, payload)


@app.get("/workers-courses/{worker_id}", dependencies=[Depends(verify_token)])
async def get_workers_courses(worker_id: int):
    return await handle_get_workers_courses(app, worker_id)


@app.post("/workers-courses", dependencies=[Depends(verify_token)])
async def upload_course(
    worker_id: int = Form(...),
    date_file: str = Form(...),
    is_payed: bool = Form(...),
    file: UploadFile = File(...),
):
    return handle_upload_course(app, worker_id, date_file, is_payed, file)


# def serialize_row(row):
#     row_dict = dict(row)
#     for key, value in row_dict.items():
#         if isinstance(value, bytes):
#             row_dict[key] = base64.b64encode(value).decode("utf-8")
#     return row_dict


# @app.get("/workerscourses/current-month")
# async def get_current_month_courses(user_id: str = Depends(verify_token)):
#     current_year_month = datetime.now().strftime("%Y-%m")

#     query = """
#         SELECT wc.*, w.name AS worker_name, w.email AS worker_email
#         FROM workerscourses wc
#         JOIN workers w ON wc.worker_id = w.id
#         WHERE wc.date_file SIMILAR TO '[0-9]{4}-[0-9]{2}-[0-9]{2}'
#           AND TO_CHAR(TO_DATE(wc.date_file, 'YYYY-MM-DD'), 'YYYY-MM') = $1
#     """

#     async with app.state.db.acquire() as conn:
#         rows = await conn.fetch(query, current_year_month)

#     return [serialize_row(row) for row in rows]
