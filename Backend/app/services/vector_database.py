import chromadb
from chromadb.api.models.Collection import Collection
from typing import List

from app.config.settings import settings


# Create one persistent client for the whole application
client = chromadb.PersistentClient(
    path=settings.CHROMA_DB_PATH
)

def get_or_create_repository_collection(repository_name: str) -> Collection:
    """
    Creates a collection if it doesn't exist,
    otherwise returns the existing collection.
    """

    collection = client.get_or_create_collection(
        name=repository_name
    )

    return collection

def get_repository_collection(repository_name: str) -> Collection:
    """
    Returns an existing repository collection.

    Raises an error if the repository has not been indexed.
    """

    return client.get_collection(name=repository_name)

def store_repository_embeddings(
    collection: Collection,
    embedded_chunks: List[dict]
):
    """
    Stores all embedded chunks inside the ChromaDB collection.
    """

    ids = []
    documents = []
    embeddings = []
    metadatas = []

    for chunk in embedded_chunks:

        ids.append(f"{chunk['file_path']}_{chunk['chunk_number']}")

        documents.append(chunk["chunk"])

        embeddings.append(chunk["embedding"])

        metadatas.append({
            "file_path": chunk["file_path"],
            "name": chunk["name"],
            "chunk_type": chunk["chunk_type"],
            "chunk_number": chunk["chunk_number"]
        })

    collection.add(
        ids=ids,
        documents=documents,
        embeddings=embeddings,
        metadatas=metadatas
    )

    print(f"Successfully stored {len(ids)} chunks in ChromaDB.")