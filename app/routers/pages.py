"""
Главная страница — обслуживает static/atomic_choice.html.
"""
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse, HTMLResponse

router = APIRouter(tags=["pages"])

INDEX_FILE = Path("static/atomic_choice.html")


@router.get("/", response_class=HTMLResponse)
async def index():
    return FileResponse(INDEX_FILE, media_type="text/html")
