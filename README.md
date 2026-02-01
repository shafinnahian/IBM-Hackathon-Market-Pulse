# Market Pulse

LLM-based job market toolkit to optimize user profiles. Built for the IBM watsonx Hackathon.
[Project demo](https://youtu.be/K8tK7UBsHeI?si=ns9h1Ay-JeG7UlTW)

## Tech Stack

- **AI Platform:** IBM watsonx Orchestrate (required for hackathon)
- **Frontend:** React (TBD — will live in `frontend/`)
- **Backend:** Python / FastAPI
- **Database:** IBM Cloudant (NoSQL document store)
- **Hosting:** IBM Cloud Code Engine (serverless containers)
- **CI/CD:** GitHub Actions → Code Engine auto-deploy on push to `main`

## Project Structure

```
├── .github/workflows/deploy.yml   # CI/CD pipeline
├── .dockerignore
├── .env.example                   # Template for local environment variables
├── Dockerfile
├── pyproject.toml                 # Python project config + dependencies
├── requirements.txt               # Pinned deps for Docker builds
└── app/
    ├── __init__.py
    ├── config.py                  # Reads CLOUDANT_URL/CLOUDANT_APIKEY from env
    ├── database.py                # Cloudant client + helpers
    └── main.py                    # FastAPI app entry point
```

## What's Done

- [x] Project scaffolding (FastAPI app, health check, CORS)
- [x] Cloudant database client setup
- [x] Dockerfile for Code Engine deployment
- [x] GitHub Actions CI/CD workflow
- [x] IBM Cloud CLI + Code Engine plugin configured
- [x] Cloudant service credentials created
- [x] watsonx Orchestrate ADK installed locally

## What's Not Done

- [ ] IBM Cloud API key → GitHub secret (`IBM_IAM_API_KEY`)
- [ ] Cloudant credentials → GitHub secrets (`CLOUDANT_URL`, `CLOUDANT_APIKEY`)
- [ ] watsonx Orchestrate agent design and implementation
- [ ] Application routes and business logic
- [ ] Data ingestion from market APIs
- [ ] Frontend (React)

## IBM Cloud Services Available

| Service | Instance Name | Purpose |
|---------|--------------|---------|
| watsonx Orchestrate | watsonx-Hackathon Orchestrate | AI agent platform (required) |
| Code Engine | watsonx-Hackathon Code Engine | App hosting |
| Cloudant | watsonx-Hackathon Cloudant | Document database |
| Cloud Object Storage | watsonx-Hackathon COS | File/blob storage |
| Watson ML | watsonx-Hackathon WML | ML model serving |
| watsonx Studio | watsonx-Hackathon WS | ML development |
| NLU | watsonx-Hackathon NLU | Text analysis |
| Speech to Text | watsonx-Hackathon STT | Audio transcription |
| Text to Speech | watsonx-Hackathon TTS | Audio synthesis |

## Local Development

```bash
# Clone the repo
git clone https://github.com/shafinnahian/IBM-Hackathon-Market-Pulse.git
cd IBM-Hackathon-Market-Pulse

# Create a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Set up your environment
cp .env.example .env
# Edit .env with your Cloudant credentials

# Run the app
uvicorn app.main:app --reload
```

## Cloudant Usage

Cloudant is a NoSQL document database — data is stored as JSON documents.

```python
from app.database import get_cloudant, ensure_database

# Create a database
ensure_database("users")

# Store a document
client = get_cloudant()
client.post_document(db="users", document={
    "name": "Jesse",
    "skills": ["python", "react"],
    "location": "NYC"
}).get_result()

# Query documents
result = client.post_find(db="users", selector={
    "location": {"$eq": "NYC"}
}).get_result()
```

## CI/CD Setup

The GitHub Actions workflow deploys to Code Engine on every push to `main`.

**GitHub secrets needed** (Settings → Secrets and variables → Actions):
- `IBM_IAM_API_KEY` — IBM Cloud API key
- `CLOUDANT_URL` — Cloudant instance URL
- `CLOUDANT_APIKEY` — Cloudant API key

## API

| Method | Path      | Description          |
|--------|-----------|----------------------|
| GET    | `/`       | Status check         |
| GET    | `/health` | Health check         |
| GET    | `/docs`   | Swagger UI (auto)    |
