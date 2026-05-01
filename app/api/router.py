from fastapi import APIRouter

from app.api.routes import (
    agent,
    approvals,
    ask,
    audit,
    chat,
    health,
    memory,
    model_gateway,
    repos,
    tasks,
    version,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(agent.router)
api_router.include_router(approvals.router)
api_router.include_router(ask.router)
api_router.include_router(audit.router)
api_router.include_router(chat.router)
api_router.include_router(memory.router)
api_router.include_router(model_gateway.router)
api_router.include_router(repos.router)
api_router.include_router(tasks.router)
api_router.include_router(version.router)
