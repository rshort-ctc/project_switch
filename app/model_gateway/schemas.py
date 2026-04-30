from enum import StrEnum

from pydantic import BaseModel, Field


class ModelRole(StrEnum):
    PLANNER = "planner_model"
    CODER = "coder_model"
    REVIEWER = "reviewer_model"
    SUMMARIZER = "summarizer_model"
    EMBEDDING = "embedding_model"
    RERANKER = "reranker_model"


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatCompletionRequest(BaseModel):
    role: ModelRole
    messages: list[ChatMessage] = Field(min_length=1)
    temperature: float = 0.0
    max_tokens: int | None = Field(default=None, gt=0)
    stream: bool = False


class ChatCompletionResponse(BaseModel):
    model: str
    content: str
    finish_reason: str | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None


class EmbeddingRequest(BaseModel):
    role: ModelRole = ModelRole.EMBEDDING
    inputs: list[str] = Field(min_length=1)


class EmbeddingResponse(BaseModel):
    model: str
    embeddings: list[list[float]]
    prompt_tokens: int | None = None
    total_tokens: int | None = None


class RerankRequest(BaseModel):
    role: ModelRole = ModelRole.RERANKER
    query: str
    documents: list[str] = Field(min_length=1)
    top_n: int | None = Field(default=None, gt=0)


class RerankResult(BaseModel):
    index: int
    score: float


class RerankResponse(BaseModel):
    model: str
    results: list[RerankResult]


class ModelHealthResponse(BaseModel):
    status: str
    endpoint: str
    model_count: int
    local_only: bool
