from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config.settings import settings
from app.routes.user import router as user_router
from app.routes.chat import router as chat_router
from app.routes.health import router as health_router
from app.database import Base, engine
from app.models.user import User # register the model with Base so that the table is created in the database

Base.metadata.create_all(bind=engine)
app = FastAPI(
    title="AI GitHub Repository Assistant",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:5174",
        "http://localhost:5175",
        "http://localhost:4173",
        settings.FRONTEND_URL,
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(user_router)
app.include_router(chat_router)
app.include_router(health_router)


@app.get("/db-test")
def test_db():
    try:
        connection = engine.connect()
        connection.close()
        return {"message": "Database connected successfully!"}
    except Exception as e:
        return {"error": str(e)}