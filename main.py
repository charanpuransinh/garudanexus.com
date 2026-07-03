from fastapi import FastAPI

from database import Base, engine
import models


Base.metadata.create_all(bind=engine)


app = FastAPI(
    title="Vyapar Business App",
    version="1.0.0",
    description="Business management API for parties, products, stock, and sales.",
)


@app.get("/", tags=["Health"])
def health_check():
    return {
        "status": "success",
        "message": "Vyapar Business App is running",
    }
