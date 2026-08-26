from fastapi import FastAPI

from app.api.routes import router
from app.core.logging import configure_logging

configure_logging()

app = FastAPI(
    title="WMS Natural-Language Query Interface",
    description="Converts plain-English warehouse-operations questions into safety-validated SQL.",
    version="0.1.0",
)

app.include_router(router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
