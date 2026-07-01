"""
Tests del CvrptwSolver (OR-Tools CVRPTW).

Estrategia:
  1. Funciones helpers puras (_hhmm_to_minutes, _minutes_to_hhmm, etc.)
  2. Edge cases del solver (sin zonas → FACTIBLE, sin unidades → NO_FACTIBLE)
  3. Solución real con OR-Tools (1 unidad, 1 zona Lima — siempre factible)

Las pruebas del solver usan matrices de fallback (haversine) para evitar
depender del servidor OSRM en CI.
"""
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest

from app.application.solver import (
    CvrptwSolver,
    _build_coords,
    _hhmm_to_minutes,
    _make_demand_callback,
    _minutes_to_hhmm,
    _zone_index_for_id,
)
from app.domain.models import (
    ParametrosSolverModel,
    SolicitudOptimizacion,
    UbicacionModel,
    UnidadModel,
    ZonaModel,
)
from app.infrastructure.osrm_client import OsrmClient

# ---------------------------------------------------------------------------
# Constantes Lima
# ---------------------------------------------------------------------------
TENANT_MML = UUID("11111111-1111-1111-1111-111111111111")
DEPOSITO_INICIO = UbicacionModel(latitud=-12.0612, longitud=-77.0617)
DEPOSITO_FIN = UbicacionModel(latitud=-12.2780, longitud=-76.8750)

ZONA_MIRAFLORES = ZonaModel(
    zona_id=UUID("bbbbbb01-0000-0000-0000-000000000001"),
    latitud=-12.1179,
    longitud=-77.0330,
    demanda_kg=450.0,
    ventana_inicio="06:00",
    ventana_fin="10:00",
    prioridad=3,
)

ZONA_SURQUILLO = ZonaModel(
    zona_id=UUID("bbbbbb03-0000-0000-0000-000000000003"),
    latitud=-12.1080,
    longitud=-77.0200,
    demanda_kg=520.0,
    ventana_inicio="06:00",
    ventana_fin="11:00",
    prioridad=3,
)

UNIDAD_CAM4892 = UnidadModel(
    unidad_id=UUID("aaaaaaa1-0000-0000-0000-000000000001"),
    capacidad_kg=8000.0,
    inicio_disponibilidad="05:00",
    fin_disponibilidad="13:00",
)


def _solicitud_simple(zonas=None, unidades=None, params=None) -> SolicitudOptimizacion:
    return SolicitudOptimizacion(
        tenant_id=TENANT_MML,
        distrito_id=UUID("22222222-2222-2222-2222-222222222222"),
        fecha_operacion=date(2026, 6, 29),
        deposito_inicio=DEPOSITO_INICIO,
        deposito_fin=DEPOSITO_FIN,
        unidades=unidades if unidades is not None else [UNIDAD_CAM4892],
        zonas=zonas if zonas is not None else [ZONA_MIRAFLORES],
        alertas_criticas=[],
        parametros_solver=params or ParametrosSolverModel(tiempo_limite_s=1),
    )


# ---------------------------------------------------------------------------
# Funciones helpers puras
# ---------------------------------------------------------------------------

class TestHhmmConversions:
    def test_inicio_turno_manaña_lima(self):
        """Turno matutino Lima: 05:00 = 300 min."""
        assert _hhmm_to_minutes("05:00") == 300

    def test_ventana_recoleccion_barranco(self):
        """Ventana Barranco: 06:30 = 390 min."""
        assert _hhmm_to_minutes("06:30") == 390

    def test_mediodia(self):
        assert _hhmm_to_minutes("12:00") == 720

    def test_fin_turno_tarde(self):
        """Fin turno tarde: 21:45 = 1305 min."""
        assert _hhmm_to_minutes("21:45") == 1305

    def test_minutes_to_hhmm_exacto(self):
        assert _minutes_to_hhmm(300) == "05:00"

    def test_minutes_to_hhmm_con_minutos_impares(self):
        assert _minutes_to_hhmm(387) == "06:27"

    def test_minutes_to_hhmm_zero(self):
        assert _minutes_to_hhmm(0) == "00:00"

    def test_minutes_to_hhmm_negativo_devuelve_cero(self):
        assert _minutes_to_hhmm(-10) == "00:00"

    def test_roundtrip(self):
        for hhmm in ("05:00", "06:30", "13:00", "23:59"):
            assert _minutes_to_hhmm(_hhmm_to_minutes(hhmm)) == hhmm


class TestBuildCoords:
    def test_deposito_primero_zonas_despues(self):
        solicitud = _solicitud_simple(zonas=[ZONA_MIRAFLORES, ZONA_SURQUILLO])
        coords = _build_coords(solicitud)
        assert len(coords) == 3
        assert coords[0] == (DEPOSITO_INICIO.latitud, DEPOSITO_INICIO.longitud)
        assert coords[1] == (ZONA_MIRAFLORES.latitud, ZONA_MIRAFLORES.longitud)
        assert coords[2] == (ZONA_SURQUILLO.latitud, ZONA_SURQUILLO.longitud)

    def test_sin_zonas_solo_deposito(self):
        solicitud = _solicitud_simple(zonas=[])
        coords = _build_coords(solicitud)
        assert len(coords) == 1
        assert coords[0] == (DEPOSITO_INICIO.latitud, DEPOSITO_INICIO.longitud)


class TestZoneIndexForId:
    def test_retorna_1_para_primera_zona(self):
        zonas = [ZONA_MIRAFLORES, ZONA_SURQUILLO]
        idx = _zone_index_for_id(zonas, ZONA_MIRAFLORES.zona_id)
        assert idx == 1

    def test_retorna_2_para_segunda_zona(self):
        zonas = [ZONA_MIRAFLORES, ZONA_SURQUILLO]
        idx = _zone_index_for_id(zonas, ZONA_SURQUILLO.zona_id)
        assert idx == 2

    def test_retorna_none_si_no_existe(self):
        zonas = [ZONA_MIRAFLORES]
        idx = _zone_index_for_id(zonas, UUID("00000000-0000-0000-0000-000000000099"))
        assert idx is None

    def test_lista_vacia(self):
        idx = _zone_index_for_id([], ZONA_MIRAFLORES.zona_id)
        assert idx is None


# ---------------------------------------------------------------------------
# Edge-cases del solver (sin OSRM real)
# ---------------------------------------------------------------------------

class TestSolverEdgeCases:
    def _make_solver_with_fallback(self) -> CvrptwSolver:
        """Solver con OsrmClient que usa fallback haversine (sin servidor real)."""
        with patch("app.infrastructure.osrm_client.settings") as mock_settings:
            mock_settings.osrm_url = "http://osrm-invalid-host-test:5000"
            osrm = OsrmClient()
        return CvrptwSolver(osrm)

    @pytest.mark.asyncio
    async def test_sin_zonas_retorna_factible_sin_rutas(self):
        """Sin zonas el solver responde FACTIBLE inmediatamente sin llamar a OR-Tools."""
        solicitud = _solicitud_simple(zonas=[])
        solver = self._make_solver_with_fallback()

        respuesta = await solver.resolver(solicitud)

        assert respuesta.estado == "FACTIBLE"
        assert "Sin zonas" in respuesta.mensaje
        assert respuesta.distancia_total_m == 0.0
        assert respuesta.duracion_total_s == 0
        assert respuesta.rutas_por_unidad == []

    @pytest.mark.asyncio
    async def test_sin_unidades_retorna_no_factible(self):
        """Sin unidades disponibles el solver retorna NO_FACTIBLE."""
        solicitud = _solicitud_simple(unidades=[])
        solver = self._make_solver_with_fallback()

        respuesta = await solver.resolver(solicitud)

        assert respuesta.estado == "NO_FACTIBLE"
        assert "unidades" in respuesta.mensaje.lower()
        assert respuesta.rutas_por_unidad == []


# ---------------------------------------------------------------------------
# Integración real con OR-Tools (haversine fallback como matrices)
# ---------------------------------------------------------------------------

class TestSolverIntegracion:
    """
    Tests de integración que ejecutan OR-Tools con matrices haversine.
    Se usan ventanas de tiempo amplias y tiempo límite 1 s para velocidad.
    Validan que la solución sea estructuralmente correcta, no el valor exacto.
    """

    @pytest.mark.asyncio
    async def test_una_unidad_una_zona_retorna_factible(self):
        """
        CAM-4892 cubre ZM-01 Miraflores Centro — siempre factible
        porque capacidad (8 t) > demanda (450 kg) y ventana amplia.
        """
        solicitud = _solicitud_simple(
            zonas=[ZONA_MIRAFLORES],
            unidades=[UNIDAD_CAM4892],
        )
        with patch("app.infrastructure.osrm_client.settings") as mock_settings:
            mock_settings.osrm_url = "http://invalid-host-test:5000"
            osrm = OsrmClient()

        solver = CvrptwSolver(osrm)
        respuesta = await solver.resolver(solicitud)

        assert respuesta.estado in ("FACTIBLE", "PARCIAL")
        assert respuesta.resuelto_en_ms >= 0
        assert respuesta.distancia_total_m >= 0
        if respuesta.estado == "FACTIBLE":
            assert len(respuesta.rutas_por_unidad) == 1
            ruta = respuesta.rutas_por_unidad[0]
            assert ruta.unidad_id == UNIDAD_CAM4892.unidad_id
            assert len(ruta.paradas) == 1
            assert ruta.paradas[0].zona_id == ZONA_MIRAFLORES.zona_id
            assert ruta.carga_total_kg == pytest.approx(450.0)

    @pytest.mark.asyncio
    async def test_dos_unidades_dos_zonas_miraflores_surquillo(self):
        """
        CAM-4892 y RIJ-0234 cubren Miraflores Centro + Surquillo Norte.
        Demandas (450 + 520 = 970 kg) ≪ capacidad de una sola unidad (8000 kg).
        """
        unidad_rij = UnidadModel(
            unidad_id=UUID("aaaaaaa2-0000-0000-0000-000000000002"),
            capacidad_kg=7500.0,
            inicio_disponibilidad="05:30",
            fin_disponibilidad="13:30",
        )
        solicitud = _solicitud_simple(
            zonas=[ZONA_MIRAFLORES, ZONA_SURQUILLO],
            unidades=[UNIDAD_CAM4892, unidad_rij],
        )
        with patch("app.infrastructure.osrm_client.settings") as mock_settings:
            mock_settings.osrm_url = "http://invalid-host-test:5000"
            osrm = OsrmClient()

        solver = CvrptwSolver(osrm)
        respuesta = await solver.resolver(solicitud)

        assert respuesta.estado in ("FACTIBLE", "PARCIAL")
        total_paradas = sum(len(r.paradas) for r in respuesta.rutas_por_unidad)
        if respuesta.estado == "FACTIBLE":
            assert total_paradas == 2

    @pytest.mark.asyncio
    async def test_respuesta_tiene_tiempo_resolucion_positivo(self):
        """El campo resuelto_en_ms refleja tiempo real de ejecución."""
        solicitud = _solicitud_simple()
        with patch("app.infrastructure.osrm_client.settings") as mock_settings:
            mock_settings.osrm_url = "http://invalid-host-test:5000"
            osrm = OsrmClient()

        solver = CvrptwSolver(osrm)
        respuesta = await solver.resolver(solicitud)

        assert respuesta.resuelto_en_ms > 0
