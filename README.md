# Product Importer

A web application for importing products from CSV files into a SQL database.

## Features (Planned)

- Upload large CSV files (up to 500,000 products)
- Real-time upload progress tracking
- Product CRUD operations with filtering and pagination
- Bulk delete functionality
- Webhook configuration and management

## Tech Stack

- **Backend**: FastAPI
- **Database**: PostgreSQL with SQLAlchemy
- **Task Queue**: Celery with Redis
- **Deployment**: Render

## Quick Start

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run the application
uvicorn app.main:app --reload
```

## API Endpoints

- `GET /health` - Health check endpoint

More endpoints coming soon!
