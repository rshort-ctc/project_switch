CODE_CHUNKS_COLLECTION = "switch_code_chunks"
DEFAULT_VECTOR_DISTANCE = "Cosine"


def code_chunks_collection_config(vector_size: int) -> dict[str, object]:
    if vector_size <= 0:
        raise ValueError("vector size must be greater than zero")
    return {
        "vectors": {
            "size": vector_size,
            "distance": DEFAULT_VECTOR_DISTANCE,
        }
    }
