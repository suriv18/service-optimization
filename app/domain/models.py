from pydantic import BaseModel
from uuid import UUID
from datetime import date
from typing import Optional


class UbicacionModel(BaseModel):
    latitud: float
    longitud: float


class UnidadModel(BaseModel):
    unidad_id: UUID
    capacidad_kg: float
    inicio_disponibilidad: str  # "HH:MM"
    fin_disponibilidad: str     # "HH:MM"


class ZonaModel(BaseModel):
    zona_id: UUID
    latitud: float
    longitud: float
    demanda_kg: float
    ventana_inicio: str   # "HH:MM"
    ventana_fin: str      # "HH:MM"
    prioridad: int


class AlertaCriticaModel(BaseModel):
    alerta_id: UUID
    zona_id: UUID
    nivel_criticidad: str


class ParametrosSolverModel(BaseModel):
    tiempo_limite_s: int = 30
    objetivo: str = "DISTANCIA"
    penalta_critica: float = 1000.0


class SolicitudOptimizacion(BaseModel):
    tenant_id: UUID
    distrito_id: UUID
    fecha_operacion: date
    deposito_inicio: UbicacionModel
    deposito_fin: UbicacionModel
    unidades: list[UnidadModel]
    zonas: list[ZonaModel]
    alertas_criticas: list[AlertaCriticaModel] = []
    parametros_solver: Optional[ParametrosSolverModel] = None


class ParadaModel(BaseModel):
    zona_id: UUID
    orden: int
    eta: str           # "HH:MM"
    carga_acumulada_kg: float


class RutaUnidadModel(BaseModel):
    unidad_id: UUID
    distancia_m: float
    duracion_s: int
    carga_total_kg: float
    paradas: list[ParadaModel]


class RespuestaOptimizacion(BaseModel):
    estado: str
    mensaje: str
    resuelto_en_ms: int
    distancia_total_m: float
    duracion_total_s: int
    rutas_por_unidad: list[RutaUnidadModel]
