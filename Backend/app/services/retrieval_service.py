from sentence_transformers import SentenceTransformer
from chromadb.api.models.Collection import Collection


model = SentenceTransformer("all-MiniLM-L6-v2")


def retrieve_relevant_chunks(
    collection: Collection,
    question: str,
    top_k: int = 5
):
    """
    Retrieves the most relevant repository chunks
    for the user's question.
    """

    question_embedding = model.encode(
        question
    ).tolist()

    results = collection.query(
        query_embeddings=[question_embedding],
        n_results=top_k
    )

    return results