import math
import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Straight-line distance in metres between two WGS-84 coordinates."""
    R = 6_371_000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def _road_distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Haversine * 1.3 approximation when OSRM is unavailable."""
    return _haversine_m(lat1, lon1, lat2, lon2) * 1.3


class OsrmClient:
    """
    Wraps the OSRM Table API to obtain NxN duration matrices.

    Falls back to haversine*1.3 distance (converted to seconds at 30 km/h)
    when OSRM is not reachable.
    """

    SPEED_M_S = 30_000 / 3600  # 30 km/h → ~8.33 m/s (urban estimate)

    def __init__(self) -> None:
        self._base_url = settings.osrm_url.rstrip("/")

    async def duration_matrix(
        self, coords: list[tuple[float, float]]
    ) -> list[list[float]]:
        """
        Returns an NxN matrix of travel durations in **seconds**.

        coords: list of (lat, lon) tuples — depot first, then zones.
        """
        if not coords:
            return []

        n = len(coords)

        try:
            coords_str = ";".join(f"{lon},{lat}" for lat, lon in coords)
            url = (
                f"{self._base_url}/table/v1/driving/{coords_str}"
                "?annotations=duration,distance"
            )
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                data = resp.json()
                if data.get("code") == "Ok" and "durations" in data:
                    return data["durations"]
                logger.warning("OSRM returned unexpected payload — using haversine fallback")
        except Exception as exc:
            logger.warning("OSRM unavailable (%s) — using haversine fallback", exc)

        # Fallback: distance-based duration estimate
        matrix: list[list[float]] = []
        for i in range(n):
            row: list[float] = []
            for j in range(n):
                if i == j:
                    row.append(0.0)
                else:
                    dist = _road_distance_m(
                        coords[i][0], coords[i][1],
                        coords[j][0], coords[j][1],
                    )
                    row.append(dist / self.SPEED_M_S)
            matrix.append(row)
        return matrix

    async def distance_matrix(
        self, coords: list[tuple[float, float]]
    ) -> list[list[float]]:
        """
        Returns an NxN matrix of travel distances in **metres**.

        Tries OSRM first; falls back to haversine*1.3.
        """
        if not coords:
            return []

        n = len(coords)

        try:
            coords_str = ";".join(f"{lon},{lat}" for lat, lon in coords)
            url = (
                f"{self._base_url}/table/v1/driving/{coords_str}"
                "?annotations=duration,distance"
            )
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                data = resp.json()
                if data.get("code") == "Ok" and "distances" in data:
                    return data["distances"]
                logger.warning("OSRM returned no distances — using haversine fallback")
        except Exception as exc:
            logger.warning("OSRM unavailable (%s) — using haversine fallback for distances", exc)

        matrix: list[list[float]] = []
        for i in range(n):
            row: list[float] = []
            for j in range(n):
                if i == j:
                    row.append(0.0)
                else:
                    row.append(
                        _road_distance_m(
                            coords[i][0], coords[i][1],
                            coords[j][0], coords[j][1],
                        )
                    )
            matrix.append(row)
        return matrix
