from fastapi import FastAPI

app = FastAPI(title="Gastos API")


@app.get("/")
async def root() -> dict[str, str]:
    return {"message": "respuesta desde FastAPI"}
