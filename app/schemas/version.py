from pydantic import BaseModel


class VersionResponse(BaseModel):
    version: str
    python: str
