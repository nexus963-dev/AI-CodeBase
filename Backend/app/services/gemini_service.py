import google.generativeai as genai

from app.config.settings import settings

genai.configure(api_key=settings.GEMINI_API_KEY)

model = genai.GenerativeModel("gemini-3.6-flash")


def generate_repository_answer(prompt: str) -> str:
    """
    Sends the prompt to Gemini and returns the generated answer.
    """

    response = model.generate_content(prompt)

    return response.text