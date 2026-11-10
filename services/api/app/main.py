from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .routers import auth as auth_router
from .routers import dashboard as dashboard_router
from .routers import insights as insights_router
from .routers import internal_tools as internal_tools_router
from .routers import jobs as jobs_router
from .routers import projects as projects_router
from .routers import recordings as recordings_router
from .routers import similar_signals as similar_signals_router


app = FastAPI(title="SignalScope AI", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    return {"status": "ok"}


app.include_router(auth_router.router)
app.include_router(recordings_router.router)
app.include_router(projects_router.router)
app.include_router(insights_router.router)
app.include_router(similar_signals_router.router)
app.include_router(internal_tools_router.router)
app.include_router(jobs_router.router)
app.include_router(dashboard_router.router)
