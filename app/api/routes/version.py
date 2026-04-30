import platform

from fastapi import APIRouter

from app import __version__
from app.schemas.version import VersionResponse

router = APIRouter(tags=["version"])


@router.get("/version", response_model=VersionResponse)
def version() -> VersionResponse:
    return VersionResponse(version=__version__, python=platform.python_version())
