import os

from fastapi import FastAPI, Response

from app.db.startup import lifespan

app = FastAPI(title="Gastos API", lifespan=lifespan)


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
