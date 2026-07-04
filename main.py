from fastapi import FastAPI

import models
from database import Base, engine
from party_routes import router as party_router
from product_routes import router as product_router
from transaction_routes import router as transaction_router

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Business Management API",
    version="1.0.0"
)

app.include_router(party_router)
app.include_router(product_router)
app.include_router(transaction_router)


@app.get("/")
def read_root():
    return {"message": "Business Management API is running successfully."}
