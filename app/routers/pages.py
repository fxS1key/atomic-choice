"""
Главные страницы:
  /           — основное SPA-приложение (templates/app.html)
  /how-it-works — объяснение криптографии и потока данных
  /legacy      — старый интерфейс (static/atomic_choice.html)
"""
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.templating import Jinja2Templates

from app.core.config import settings

router = APIRouter(tags=["pages"])

templates = Jinja2Templates(directory="templates")


@router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(
        "app.html",
        {"request": request, "public_url": settings.PUBLIC_URL or ""},
    )


@router.get("/how-it-works", response_class=HTMLResponse)
async def how_it_works(request: Request):
    return templates.TemplateResponse(
        "how_it_works.html",
        {"request": request},
    )


@router.get("/legacy", response_class=HTMLResponse)
async def legacy():
    legacy_path = Path("static/atomic_choice.html")
    if legacy_path.exists():
        return FileResponse(legacy_path, media_type="text/html")
    return HTMLResponse("<h1>legacy UI not found</h1>", status_code=404)
