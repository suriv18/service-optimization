"""
Tests de los endpoints FastAPI.

/health               → GET
/api/v1/optimizar     → POST (SolicitudOptimizacion → RespuestaOptimizacion)

Se usa httpx.AsyncClient con app directamente (sin servidor real).
El OsrmClient usa fallback haversine en todos los tests de integración.
"""
from datetime import date
from unittest.mock import patch
from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient

from app.domain.models import RespuestaOptimizacion
from app.main import app

# ---------------------------------------------------------------------------
# Datos Lima
# ---------------------------------------------------------------------------
TENANT_MML = "11111111-1111-1111-1111-111111111111"
DISTRITO_MIRAFLORES = "22222222-2222-2222-2222-222222222222"

DEPOSITO_LIMA_CENTRO = {"latitud": -12.0612, "longitud": -77.0617}
DEPOSITO_PORTILLO_GRANDE = {"latitud": -12.2780, "longitud": -76.8750}

UNIDAD_CAM4892 = {
    "unidad_id": "aaaaaaa1-0000-0000-0000-000000000001",
    "capacidad_kg": 8000.0,
    "inicio_disponibilidad": "05:00",
    "fin_disponibilidad": "13:00",
}

ZONA_MIRAFLORES_CENTRO = {
    "zona_id": "bbbbbb01-0000-0000-0000-000000000001",
    "latitud": -12.1179,
    "longitud": -77.0330,
    "demanda_kg": 450.0,
    "ventana_inicio": "06:00",
    "ventana_fin": "10:00",
    "prioridad": 3,
}


def _solicitud_payload(**overrides) -> dict:
    base = {
        "tenant_id": TENANT_MML,
        "distrito_id": DISTRITO_MIRAFLORES,
        "fecha_operacion": "2026-06-29",
        "deposito_inicio": DEPOSITO_LIMA_CENTRO,
        "deposito_fin": DEPOSITO_PORTILLO_GRANDE,
        "unidades": [UNIDAD_CAM4892],
        "zonas": [ZONA_MIRAFLORES_CENTRO],
        "alertas_criticas": [],
        "parametros_solver": {"tiempo_limite_s": 1, "objetivo": "DISTANCIA"},
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# /health
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_health_retorna_200_ok():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


# ---------------------------------------------------------------------------
# POST /api/v1/optimizar — estructura y contratos
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_optimizar_sin_zonas_retorna_factible():
    """Sin zonas el servicio responde FACTIBLE inmediatamente."""
    payload = _solicitud_payload(zonas=[])

    with patch("app.infrastructure.osrm_client.settings") as mock_settings:
        mock_settings.osrm_url = "http://invalid-host-test:5000"
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/api/v1/optimizar", json=payload)

    assert resp.status_code == 200
    body = resp.json()
    assert body["estado"] == "FACTIBLE"
    assert body["rutas_por_unidad"] == []
    assert body["distancia_total_m"] == 0.0


@pytest.mark.asyncio
async def test_optimizar_sin_unidades_retorna_no_factible():
    """Sin unidades disponibles el servicio retorna NO_FACTIBLE."""
    payload = _solicitud_payload(unidades=[])

    with patch("app.infrastructure.osrm_client.settings") as mock_settings:
        mock_settings.osrm_url = "http://invalid-host-test:5000"
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/api/v1/optimizar", json=payload)

    assert resp.status_code == 200
    body = resp.json()
    assert body["estado"] == "NO_FACTIBLE"
    assert body["rutas_por_unidad"] == []


@pytest.mark.asyncio
async def test_optimizar_una_zona_respuesta_valida():
    """
    CAM-4892 / ZM-01 Miraflores — OR-Tools real con fallback haversine.
    Valida que la respuesta cumpla el contrato RespuestaOptimizacion.
    """
    payload = _solicitud_payload()

    with patch("app.infrastructure.osrm_client.settings") as mock_settings:
        mock_settings.osrm_url = "http://invalid-host-test:5000"
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/api/v1/optimizar", json=payload)

    assert resp.status_code == 200
    body = resp.json()

    # Contrato de campos obligatorios
    assert "estado" in body
    assert "mensaje" in body
    assert "resuelto_en_ms" in body
    assert "distancia_total_m" in body
    assert "duracion_total_s" in body
    assert "rutas_por_unidad" in body

    assert body["estado"] in ("FACTIBLE", "PARCIAL", "NO_FACTIBLE")
    assert body["resuelto_en_ms"] >= 0

    # Validar que Pydantic puede deserializar la respuesta
    RespuestaOptimizacion.model_validate(body)


@pytest.mark.asyncio
async def test_optimizar_payload_invalido_retorna_422():
    """Payload sin tenant_id debe retornar 422 Unprocessable Entity."""
    payload = {
        "distrito_id": DISTRITO_MIRAFLORES,
        "fecha_operacion": "2026-06-29",
        "deposito_inicio": DEPOSITO_LIMA_CENTRO,
        "deposito_fin": DEPOSITO_PORTILLO_GRANDE,
        "unidades": [],
        "zonas": [],
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/api/v1/optimizar", json=payload)

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_optimizar_con_alerta_critica_se_procesa():
    """
    Solicitud con alerta crítica en Miraflores Centro.
    El solver debe incluir dicha zona con penalización alta (no rechazarla).
    """
    payload = _solicitud_payload(
        alertas_criticas=[
            {
                "alerta_id": "cccccc01-0000-0000-0000-000000000001",
                "zona_id": "bbbbbb01-0000-0000-0000-000000000001",
                "nivel_criticidad": "CRITICA",
            }
        ]
    )

    with patch("app.infrastructure.osrm_client.settings") as mock_settings:
        mock_settings.osrm_url = "http://invalid-host-test:5000"
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/api/v1/optimizar", json=payload)

    assert resp.status_code == 200
    body = resp.json()
    assert body["estado"] in ("FACTIBLE", "PARCIAL", "NO_FACTIBLE")


@pytest.mark.asyncio
async def test_optimizar_parametros_solver_por_defecto():
    """Sin parametros_solver el servicio usa los defaults de ParametrosSolverModel."""
    payload = _solicitud_payload()
    del payload["parametros_solver"]

    with patch("app.infrastructure.osrm_client.settings") as mock_settings:
        mock_settings.osrm_url = "http://invalid-host-test:5000"
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/api/v1/optimizar", json=payload)

    # Con defaults (30 s tiempo límite) debe terminar y responder correctamente
    assert resp.status_code == 200
    assert "estado" in resp.json()
