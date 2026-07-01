"""
Fixtures compartidos para los tests de service-optimization.

Datos basados en distritos y zonas reales de Lima, Perú.
Coordenadas verificadas de operaciones de recolección de residuos sólidos
(Municipalidad Metropolitana de Lima / EMILIMA).
"""
from datetime import date
from uuid import UUID

import pytest

from app.domain.models import (
    AlertaCriticaModel,
    ParametrosSolverModel,
    SolicitudOptimizacion,
    UbicacionModel,
    UnidadModel,
    ZonaModel,
)

# ---------------------------------------------------------------------------
# UUIDs fijos para reproducibilidad
# ---------------------------------------------------------------------------
TENANT_MML = UUID("11111111-1111-1111-1111-111111111111")  # Municipalidad Metropolitana de Lima
DISTRITO_MIRAFLORES = UUID("22222222-2222-2222-2222-222222222222")

# Unidades reales (camiones compactadores Lima)
UNIDAD_CAM4892 = UUID("aaaaaaa1-0000-0000-0000-000000000001")  # CAM-4892
UNIDAD_RIJ0234 = UUID("aaaaaaa2-0000-0000-0000-000000000002")  # RIJ-0234

# Zonas reales de recolección en Miraflores / Surquillo
ZONA_MIRAFLORES_CENTRO = UUID("bbbbbb01-0000-0000-0000-000000000001")   # Av. Larco
ZONA_MIRAFLORES_COSTA  = UUID("bbbbbb02-0000-0000-0000-000000000002")   # Malecón de Miraflores
ZONA_SURQUILLO_NORTE   = UUID("bbbbbb03-0000-0000-0000-000000000003")   # Av. República de Panamá
ZONA_BARRANCO_CENTRO   = UUID("bbbbbb04-0000-0000-0000-000000000004")   # Av. Grau, Barranco

# Alerta crítica
ALERTA_001 = UUID("cccccc01-0000-0000-0000-000000000001")


# ---------------------------------------------------------------------------
# Fixtures de dominio
# ---------------------------------------------------------------------------

@pytest.fixture
def deposito_inicio_lima_centro() -> UbicacionModel:
    """Estación de Transferencia Lima Centro — Av. Argentina, La Victoria."""
    return UbicacionModel(latitud=-12.0612, longitud=-77.0617)


@pytest.fixture
def deposito_fin_portillo_grande() -> UbicacionModel:
    """Relleno Sanitario Portillo Grande — Lurín, Lima Sur."""
    return UbicacionModel(latitud=-12.2780, longitud=-76.8750)


@pytest.fixture
def unidad_cam4892() -> UnidadModel:
    """Camión compactador CAM-4892, turno matutino Miraflores (05:00–13:00)."""
    return UnidadModel(
        unidad_id=UNIDAD_CAM4892,
        capacidad_kg=8000.0,
        inicio_disponibilidad="05:00",
        fin_disponibilidad="13:00",
    )


@pytest.fixture
def unidad_rij0234() -> UnidadModel:
    """Camión compactador RIJ-0234, turno matutino complementario (05:30–13:30)."""
    return UnidadModel(
        unidad_id=UNIDAD_RIJ0234,
        capacidad_kg=7500.0,
        inicio_disponibilidad="05:30",
        fin_disponibilidad="13:30",
    )


@pytest.fixture
def zona_miraflores_centro() -> ZonaModel:
    """Zona ZM-01 — Av. Larco / Miraflores Centro. ~450 kg/día."""
    return ZonaModel(
        zona_id=ZONA_MIRAFLORES_CENTRO,
        latitud=-12.1179,
        longitud=-77.0330,
        demanda_kg=450.0,
        ventana_inicio="06:00",
        ventana_fin="10:00",
        prioridad=3,
    )


@pytest.fixture
def zona_miraflores_costa() -> ZonaModel:
    """Zona ZM-02 — Malecón Cisneros, Miraflores. ~280 kg/día."""
    return ZonaModel(
        zona_id=ZONA_MIRAFLORES_COSTA,
        latitud=-12.1347,
        longitud=-77.0325,
        demanda_kg=280.0,
        ventana_inicio="06:00",
        ventana_fin="10:00",
        prioridad=2,
    )


@pytest.fixture
def zona_surquillo_norte() -> ZonaModel:
    """Zona ZSQ-01 — Av. República de Panamá, Surquillo. ~520 kg/día."""
    return ZonaModel(
        zona_id=ZONA_SURQUILLO_NORTE,
        latitud=-12.1080,
        longitud=-77.0200,
        demanda_kg=520.0,
        ventana_inicio="06:00",
        ventana_fin="11:00",
        prioridad=3,
    )


@pytest.fixture
def zona_barranco_centro() -> ZonaModel:
    """Zona ZB-01 — Av. Grau, Barranco. ~320 kg/día."""
    return ZonaModel(
        zona_id=ZONA_BARRANCO_CENTRO,
        latitud=-12.1347,
        longitud=-77.0325,
        demanda_kg=320.0,
        ventana_inicio="06:00",
        ventana_fin="11:00",
        prioridad=2,
    )


@pytest.fixture
def alerta_critica_miraflores_centro() -> AlertaCriticaModel:
    """Alerta crítica reportada por ciudadano en Miraflores Centro."""
    return AlertaCriticaModel(
        alerta_id=ALERTA_001,
        zona_id=ZONA_MIRAFLORES_CENTRO,
        nivel_criticidad="CRITICA",
    )


@pytest.fixture
def parametros_rapidos() -> ParametrosSolverModel:
    """Parámetros solver con tiempo límite corto para tests (1 segundo)."""
    return ParametrosSolverModel(
        tiempo_limite_s=1,
        objetivo="DISTANCIA",
        penalta_critica=1000.0,
    )


@pytest.fixture
def solicitud_una_zona(
    deposito_inicio_lima_centro,
    deposito_fin_portillo_grande,
    unidad_cam4892,
    zona_miraflores_centro,
    parametros_rapidos,
) -> SolicitudOptimizacion:
    """Solicitud mínima: 1 unidad, 1 zona — caso simple de validación."""
    return SolicitudOptimizacion(
        tenant_id=TENANT_MML,
        distrito_id=DISTRITO_MIRAFLORES,
        fecha_operacion=date(2026, 6, 30),
        deposito_inicio=deposito_inicio_lima_centro,
        deposito_fin=deposito_fin_portillo_grande,
        unidades=[unidad_cam4892],
        zonas=[zona_miraflores_centro],
        alertas_criticas=[],
        parametros_solver=parametros_rapidos,
    )


@pytest.fixture
def solicitud_dos_zonas_dos_unidades(
    deposito_inicio_lima_centro,
    deposito_fin_portillo_grande,
    unidad_cam4892,
    unidad_rij0234,
    zona_miraflores_centro,
    zona_surquillo_norte,
    parametros_rapidos,
) -> SolicitudOptimizacion:
    """Solicitud con 2 unidades y 2 zonas — caso multi-vehículo."""
    return SolicitudOptimizacion(
        tenant_id=TENANT_MML,
        distrito_id=DISTRITO_MIRAFLORES,
        fecha_operacion=date(2026, 6, 30),
        deposito_inicio=deposito_inicio_lima_centro,
        deposito_fin=deposito_fin_portillo_grande,
        unidades=[unidad_cam4892, unidad_rij0234],
        zonas=[zona_miraflores_centro, zona_surquillo_norte],
        alertas_criticas=[],
        parametros_solver=parametros_rapidos,
    )


@pytest.fixture
def solicitud_sin_zonas(
    deposito_inicio_lima_centro,
    deposito_fin_portillo_grande,
    unidad_cam4892,
) -> SolicitudOptimizacion:
    """Solicitud con lista de zonas vacía — edge case."""
    return SolicitudOptimizacion(
        tenant_id=TENANT_MML,
        distrito_id=DISTRITO_MIRAFLORES,
        fecha_operacion=date(2026, 6, 30),
        deposito_inicio=deposito_inicio_lima_centro,
        deposito_fin=deposito_fin_portillo_grande,
        unidades=[unidad_cam4892],
        zonas=[],
        alertas_criticas=[],
    )


@pytest.fixture
def solicitud_sin_unidades(
    deposito_inicio_lima_centro,
    deposito_fin_portillo_grande,
    zona_miraflores_centro,
) -> SolicitudOptimizacion:
    """Solicitud sin unidades disponibles — edge case."""
    return SolicitudOptimizacion(
        tenant_id=TENANT_MML,
        distrito_id=DISTRITO_MIRAFLORES,
        fecha_operacion=date(2026, 6, 30),
        deposito_inicio=deposito_inicio_lima_centro,
        deposito_fin=deposito_fin_portillo_grande,
        unidades=[],
        zonas=[zona_miraflores_centro],
        alertas_criticas=[],
    )


# ---------------------------------------------------------------------------
# Matrices de distancia/duración sintéticas (Lima urbana realista)
# ---------------------------------------------------------------------------

def make_matrix_2x2(depot_to_zone_m: float, speed_ms: float = 8.33) -> tuple:
    """
    Genera matrices 2×2 [deposito, zona] con distancia y duración realistas.
    speed_ms: velocidad media urbana en Lima ~30 km/h = 8.33 m/s
    """
    d = depot_to_zone_m
    t = d / speed_ms
    dist = [[0.0, d], [d, 0.0]]
    dur  = [[0.0, t], [t, 0.0]]
    return dur, dist


def make_matrix_3x3(d01: float, d02: float, d12: float, speed_ms: float = 8.33) -> tuple:
    """
    Genera matrices 3×3 [deposito, zona1, zona2].
    Distancias en metros; duración calculada a velocidad urbana Lima.
    """
    def t(d): return d / speed_ms
    dist = [
        [0.0,  d01,  d02],
        [d01,  0.0,  d12],
        [d02,  d12,  0.0],
    ]
    dur = [
        [0.0,    t(d01), t(d02)],
        [t(d01), 0.0,    t(d12)],
        [t(d02), t(d12), 0.0],
    ]
    return dur, dist
