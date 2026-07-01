import time

from fastapi import APIRouter

from app.application.solver import CvrptwSolver
from app.domain.models import RespuestaOptimizacion, SolicitudOptimizacion
from app.infrastructure.osrm_client import OsrmClient

router = APIRouter()


@router.post("/optimizar", response_model=RespuestaOptimizacion)
async def optimizar(solicitud: SolicitudOptimizacion) -> RespuestaOptimizacion:
    osrm = OsrmClient()
    solver = CvrptwSolver(osrm)
    return await solver.resolver(solicitud)
