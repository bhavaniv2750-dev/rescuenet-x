from fastapi import APIRouter

router = APIRouter()


@router.get("/")
def list_observations():
    return {
        "items": [],
        "count": 0,
        "message": "No field observations have been recorded.",
    }
