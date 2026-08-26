"""API routes — filled in during the NL→SQL pipeline phase (POST /query, GET /audit, GET /schema).

Kept as an empty router for now so app.main can import it during the repo
scaffold phase before the pipeline exists.
"""
from fastapi import APIRouter

router = APIRouter()
