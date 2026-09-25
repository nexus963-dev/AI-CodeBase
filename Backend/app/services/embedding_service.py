from typing import List
from sentence_transformers import SentenceTransformer

# Load the model only once
model = SentenceTransformer("all-MiniLM-L6-v2")


def generate_embeddings(chunk_data: List[dict]) -> List[dict]:

    embedded_chunks = []

    for index, chunk in enumerate(chunk_data, start=1):

        print(f"Generating embedding {index}/{len(chunk_data)}")

        try:
            embedding = model.encode(chunk["chunk"])

            # Convert NumPy array to Python list
            embedding = embedding.tolist()

            # Add embedding to the chunk
            chunk["embedding"] = embedding

            # Store the enriched chunk
            embedded_chunks.append(chunk)

        except Exception as e:
            print(f"Error generating embedding for chunk {index}: {e}")
            continue

    return embedded_chunks