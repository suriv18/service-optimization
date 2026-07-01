from fastapi import FastAPI

from app.api.v1.optimizar import router

app = FastAPI(title="Ciudad Sana — Optimization Service", version="0.1.0")
app.include_router(router, prefix="/api/v1")


@app.get("/health")
async def health():
    return {"status": "ok"}
