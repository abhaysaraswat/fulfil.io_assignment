"""FastAPI application entry point."""
from fastapi import FastAPI

app = FastAPI(
    title="Product Importer",
    description="Import products from CSV files into a SQL database",
    version="0.1.0",
)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}
