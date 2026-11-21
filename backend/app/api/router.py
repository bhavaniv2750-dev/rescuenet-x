from fastapi import APIRouter, Depends
from app.api.routes.agents import router as agents_router
from app.api.routes.auth import router as auth_router
from app.api.routes.alerts import router as alerts_router
from app.api.routes.dashboard import router as dashboard_router
from app.api.routes.datasets import router as datasets_router
from app.api.routes.facilities import router as facilities_router
from app.api.routes.flood import router as flood_router
from app.api.routes.health import router as health_router
from app.api.routes.incidents import router as incidents_router
from app.api.routes.records import router as records_router
from app.api.routes.teams import router as teams_router
from app.api.routes.vision import router as vision_router
from app.api.routes.volunteers import router as volunteers_router

from app.api.deps import require_roles
from app.core.security import DEPT, OPS

api_router = APIRouter()

api_router.include_router(health_router, tags=["Health"])
api_router.include_router(auth_router, prefix="/auth", tags=["Auth"])
api_router.include_router(dashboard_router, tags=["Dashboard"], dependencies=[Depends(require_roles(*DEPT))])
api_router.include_router(flood_router, prefix="/flood", tags=["Flood"])
api_router.include_router(incidents_router, prefix="/incidents", tags=["Incidents"])
api_router.include_router(alerts_router, prefix="/alerts", tags=["Alerts"])
api_router.include_router(teams_router, prefix="/teams", tags=["Rescue Teams"])
api_router.include_router(volunteers_router, prefix="/volunteers", tags=["Volunteers"])
api_router.include_router(facilities_router, prefix="/facilities", tags=["Facilities"])
api_router.include_router(records_router, prefix="/records", tags=["Rescue Records"])
api_router.include_router(agents_router, prefix="/agents", tags=["AI Agents"])
api_router.include_router(datasets_router, prefix="/datasets", tags=["Datasets"])
api_router.include_router(vision_router, prefix="/vision", tags=["Vision"], dependencies=[Depends(require_roles(*DEPT))])
