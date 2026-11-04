import os

from fastapi import FastAPI, Response

from app.db.startup import lifespan
from app.auth import router as auth_router

app = FastAPI(title="Gastos API", lifespan=lifespan)
app.include_router(auth_router)


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
