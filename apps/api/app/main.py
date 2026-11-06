import os

from fastapi import FastAPI, Response

from app.db.startup import lifespan
from app.auth import router as auth_router
from app.accounts import router as accounts_router
from app.expenses import router as expenses_router
from app.personal_space import router as personal_space_router

app = FastAPI(title="Gastos API", lifespan=lifespan)
app.include_router(auth_router)
app.include_router(accounts_router)
app.include_router(expenses_router)
app.include_router(personal_space_router)


@app.get("/")
async def root() -> dict[str, str]:
    return {"message": "Hola desde FastAPI"}


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/version")
async def version(response: Response) -> dict[str, str | None]:
    response.headers["Cache-Control"] = "no-store"
    return {"commit": os.getenv("RENDER_GIT_COMMIT")}
