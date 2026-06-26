from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

import database
from routers import control, settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    await database.init_db()
    # Phase 2/3에서 추가 예정: serial_reader 시작 등
    yield


app = FastAPI(title="NFT 배양액 모니터", lifespan=lifespan)

app.include_router(control.router)
app.include_router(settings.router)

# Phase 2에서 추가 예정:
# - WebSocket router
# - /api/sensor 라우터

# StaticFiles는 catch-all 마운트이므로 반드시 API 라우터 등록 이후에 마운트한다.
app.mount("/", StaticFiles(directory="static", html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
