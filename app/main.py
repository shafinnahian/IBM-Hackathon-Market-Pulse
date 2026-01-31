from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import jobs, salaries

app = FastAPI(
    title="Market Pulse API",
    description=(
        "Job market intelligence API providing tech job listings and salary benchmarks. "
        "Search jobs from The Muse and Adzuna by title, company, location, category, or level. "
        "Compare compensation across cities, experience levels, and companies."
    ),
    version="1.0.0",
    servers=[
        {"url": "https://market-pulse-app.25raqj64rgw0.us-south.codeengine.appdomain.cloud"},
    ],
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(jobs.router)
app.include_router(salaries.router)


@app.get("/")
def root():
    return {"status": "ok", "project": "Market Pulse"}


@app.get("/health")
def health():
    return {"status": "healthy"}
