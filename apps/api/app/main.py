import os

from fastapi import FastAPI, Response

from app.reminder_preferences import router as reminder_preferences_router
from app.db.startup import lifespan
from app.auth import router as auth_router
from app.accounts import router as accounts_router
from app.movements import router as movements_router
from app.space_export import router as space_export_router
from app.movement_categories import router as movement_categories_router
from app.expenses import router as expenses_router
from app.expense_import import router as expense_import_router
from app.planning import router as planning_router
from app.usd_reference import router as usd_reference_router
from app.receipts import router as receipts_router
from app.personal_space import router as personal_space_router

from app.adjustment_indices import router as adjustment_indices_router
from app.commitments import router as commitments_router
from app.savings_goals import router as savings_goals_router
from app.transfers import router as transfers_router
from app.incomes import router as incomes_router

app = FastAPI(title="Gastos API", lifespan=lifespan)
app.include_router(auth_router)
app.include_router(reminder_preferences_router)
app.include_router(accounts_router)
app.include_router(movements_router)
app.include_router(space_export_router)
app.include_router(movement_categories_router)
app.include_router(incomes_router)
app.include_router(transfers_router)
app.include_router(savings_goals_router)
app.include_router(commitments_router)
app.include_router(adjustment_indices_router)
app.include_router(expenses_router)
app.include_router(expense_import_router)
app.include_router(receipts_router)
app.include_router(planning_router)
app.include_router(usd_reference_router)
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
