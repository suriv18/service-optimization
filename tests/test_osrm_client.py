"""
Tests para OsrmClient e funciones de distancia.

Coordenadas de Lima, Perú:
  - Estación de Transferencia Lima Centro (La Victoria): -12.0612, -77.0617
  - Miraflores Centro (Av. Larco):                       -12.1179, -77.0330
  - Barranco Centro (Av. Grau):                          -12.1347, -77.0325
  - Surquillo Norte (Av. República de Panamá):           -12.1080, -77.0200
"""
import math
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import httpx

from app.infrastructure.osrm_client import OsrmClient, _haversine_m, _road_distance_m


# ---------------------------------------------------------------------------
# _haversine_m — función pura
# ---------------------------------------------------------------------------

class TestHaversineM:
    def test_misma_ubicacion_es_cero(self):
        d = _haversine_m(-12.0612, -77.0617, -12.0612, -77.0617)
        assert d == pytest.approx(0.0)

    def test_deposito_a_miraflores_centro(self):
        """
        Estación de Transferencia Lima Centro → Miraflores Centro (Av. Larco).
        Distancia en línea recta ~6.5 km (Lima tiene calles relativamente ortogonales).
        """
        d = _haversine_m(-12.0612, -77.0617, -12.1179, -77.0330)
        assert 5_500 < d < 8_000, f"Distancia esperada ~6-7 km, obtuvo {d:.0f} m"

    def test_miraflores_a_barranco_es_corto(self):
        """Miraflores Centro → Barranco Centro: distritos contiguos ~2 km."""
        d = _haversine_m(-12.1179, -77.0330, -12.1347, -77.0325)
        assert d < 3_000, f"Distritos contiguos deben ser <3 km, obtuvo {d:.0f} m"

    def test_simetria(self):
        """d(A→B) debe ser igual a d(B→A)."""
        d_ab = _haversine_m(-12.0612, -77.0617, -12.1179, -77.0330)
        d_ba = _haversine_m(-12.1179, -77.0330, -12.0612, -77.0617)
        assert d_ab == pytest.approx(d_ba)

    def test_formula_haversine_precision(self):
        """Verifica que el cálculo coincide con la fórmula haversine manual."""
        lat1, lon1 = -12.0612, -77.0617
        lat2, lon2 = -12.1179, -77.0330
        R = 6_371_000.0
        phi1, phi2 = math.radians(lat1), math.radians(lat2)
        dphi = math.radians(lat2 - lat1)
        dlambda = math.radians(lon2 - lon1)
        a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
        expected = 2 * R * math.asin(math.sqrt(a))
        assert _haversine_m(lat1, lon1, lat2, lon2) == pytest.approx(expected)


# ---------------------------------------------------------------------------
# _road_distance_m — aproximación con factor 1.3
# ---------------------------------------------------------------------------

class TestRoadDistanceM:
    def test_road_es_haversine_por_factor_13(self):
        lat1, lon1 = -12.0612, -77.0617
        lat2, lon2 = -12.1179, -77.0330
        h = _haversine_m(lat1, lon1, lat2, lon2)
        r = _road_distance_m(lat1, lon1, lat2, lon2)
        assert r == pytest.approx(h * 1.3)

    def test_road_mismo_punto_es_cero(self):
        d = _road_distance_m(-12.1080, -77.0200, -12.1080, -77.0200)
        assert d == pytest.approx(0.0)

    def test_road_deposito_a_surquillo(self):
        """Ruta vial (estimada) La Victoria → Surquillo: ~6 km × 1.3 = ~7-8 km."""
        d = _road_distance_m(-12.0612, -77.0617, -12.1080, -77.0200)
        assert 5_000 < d < 12_000


# ---------------------------------------------------------------------------
# OsrmClient.duration_matrix — con mock OSRM exitoso
# ---------------------------------------------------------------------------

class TestDurationMatrix:
    @pytest.mark.asyncio
    async def test_osrm_ok_retorna_durations(self):
        """Con OSRM respondiendo correctamente devuelve la matriz de duraciones."""
        coords = [
            (-12.0612, -77.0617),   # depósito
            (-12.1179, -77.0330),   # Miraflores Centro
        ]
        osrm_response = {
            "code": "Ok",
            "durations": [[0.0, 720.0], [720.0, 0.0]],
            "distances": [[0.0, 6000.0], [6000.0, 0.0]],
        }
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = osrm_response

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            client = OsrmClient()
            matrix = await client.duration_matrix(coords)

        assert matrix == [[0.0, 720.0], [720.0, 0.0]]

    @pytest.mark.asyncio
    async def test_osrm_no_disponible_usa_haversine_fallback(self):
        """Cuando OSRM no está disponible (ConnectError), usa haversine×1.3/velocidad."""
        coords = [
            (-12.0612, -77.0617),   # depósito Lima Centro
            (-12.1179, -77.0330),   # Miraflores Centro
        ]
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(
                side_effect=httpx.ConnectError("OSRM no disponible")
            )
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            client = OsrmClient()
            matrix = await client.duration_matrix(coords)

        assert len(matrix) == 2
        assert matrix[0][0] == pytest.approx(0.0)
        assert matrix[1][1] == pytest.approx(0.0)
        # Duración fallback debe ser positiva y razonable (3–20 min = 180–1200 s)
        assert 180 < matrix[0][1] < 1_200
        assert matrix[0][1] == pytest.approx(matrix[1][0])

    @pytest.mark.asyncio
    async def test_lista_vacia_retorna_vacia(self):
        client = OsrmClient()
        result = await client.duration_matrix([])
        assert result == []

    @pytest.mark.asyncio
    async def test_osrm_payload_inesperado_usa_fallback(self):
        """Si OSRM responde sin 'durations', usa fallback haversine."""
        coords = [
            (-12.0612, -77.0617),
            (-12.1080, -77.0200),
        ]
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"code": "Ok"}  # sin 'durations'

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            client = OsrmClient()
            matrix = await client.duration_matrix(coords)

        assert matrix[0][0] == pytest.approx(0.0)
        assert matrix[0][1] > 0


# ---------------------------------------------------------------------------
# OsrmClient.distance_matrix
# ---------------------------------------------------------------------------

class TestDistanceMatrix:
    @pytest.mark.asyncio
    async def test_osrm_ok_retorna_distances(self):
        """Con OSRM correcto devuelve la matriz de distancias en metros."""
        coords = [
            (-12.0612, -77.0617),
            (-12.1347, -77.0325),   # Barranco
        ]
        osrm_response = {
            "code": "Ok",
            "durations": [[0.0, 900.0], [900.0, 0.0]],
            "distances": [[0.0, 7500.0], [7500.0, 0.0]],
        }
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = osrm_response

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            client = OsrmClient()
            matrix = await client.distance_matrix(coords)

        assert matrix == [[0.0, 7500.0], [7500.0, 0.0]]

    @pytest.mark.asyncio
    async def test_fallback_distancias_son_road_distance(self):
        """Sin OSRM, las distancias deben coincidir con _road_distance_m."""
        coords = [
            (-12.0612, -77.0617),
            (-12.1179, -77.0330),
        ]
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(
                side_effect=httpx.ConnectError("timeout")
            )
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            client = OsrmClient()
            matrix = await client.distance_matrix(coords)

        expected = _road_distance_m(
            coords[0][0], coords[0][1],
            coords[1][0], coords[1][1],
        )
        assert matrix[0][1] == pytest.approx(expected)
        assert matrix[1][0] == pytest.approx(expected)
        assert matrix[0][0] == pytest.approx(0.0)

    @pytest.mark.asyncio
    async def test_osrm_ok_sin_distances_usa_fallback(self):
        """
        OSRM responde code=Ok pero sin campo 'distances' (línea 109).
        Debe emitir warning y calcular con haversine×1.3.
        """
        coords = [
            (-12.0612, -77.0617),   # depósito Lima Centro
            (-12.1347, -77.0325),   # Barranco
        ]
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "code": "Ok",
            "durations": [[0.0, 900.0], [900.0, 0.0]],
            # sin 'distances' — fuerza la rama de warning + fallback
        }

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            client = OsrmClient()
            matrix = await client.distance_matrix(coords)

        # Debe usar haversine*1.3 como fallback
        expected = _road_distance_m(
            coords[0][0], coords[0][1],
            coords[1][0], coords[1][1],
        )
        assert matrix[0][0] == pytest.approx(0.0)
        assert matrix[1][1] == pytest.approx(0.0)
        assert matrix[0][1] == pytest.approx(expected)
        assert matrix[1][0] == pytest.approx(expected)

    @pytest.mark.asyncio
    async def test_lista_vacia_retorna_vacia(self):
        client = OsrmClient()
        result = await client.distance_matrix([])
        assert result == []
