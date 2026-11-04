from typing import Dict

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health", include_in_schema=False)
def health_check() -> Dict[str, str]:
    return {"status": "ok"}
