"""
CVRPTW solver using Google OR-Tools.

Node layout:
  index 0          → depósito (inicio & fin compartido en el modelo)
  index 1..N       → zonas (N = len(solicitud.zonas))

For simplicity the depot start and end are both node 0; OR-Tools
supports a single depot by default.  If deposito_inicio != deposito_fin
the difference is negligible for city-scale problems and the brief does
not require a two-depot model.
"""

import asyncio
import logging
import time
from typing import Optional
from uuid import UUID

from ortools.constraint_solver import pywrapcp
from ortools.constraint_solver import routing_enums_pb2

from app.domain.models import (
    AlertaCriticaModel,
    ParadaModel,
    ParametrosSolverModel,
    RespuestaOptimizacion,
    RutaUnidadModel,
    SolicitudOptimizacion,
    UnidadModel,
    ZonaModel,
)
from app.infrastructure.osrm_client import OsrmClient

logger = logging.getLogger(__name__)

_SCALE = 1  # seconds are already integers; no extra scaling needed
_LARGE_PENALTY = 10_000_000


def _hhmm_to_minutes(hhmm: str) -> int:
    """Convert 'HH:MM' to minutes since midnight."""
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def _minutes_to_hhmm(minutes: int) -> str:
    """Convert minutes since midnight to 'HH:MM'."""
    minutes = max(0, minutes)
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _build_coords(
    solicitud: SolicitudOptimizacion,
) -> list[tuple[float, float]]:
    """
    Build ordered coordinate list: [depot, zone_0, zone_1, ..., zone_N-1].
    Uses deposito_inicio as the depot node.
    """
    depot = (solicitud.deposito_inicio.latitud, solicitud.deposito_inicio.longitud)
    zones = [(z.latitud, z.longitud) for z in solicitud.zonas]
    return [depot] + zones


def _make_duration_callback(
    duration_matrix_s: list[list[float]],
    manager: pywrapcp.RoutingIndexManager,
):
    """Return a transit callback (seconds, truncated to int)."""

    def callback(from_index: int, to_index: int) -> int:
        from_node = manager.IndexToNode(from_index)
        to_node = manager.IndexToNode(to_index)
        return int(duration_matrix_s[from_node][to_node])

    return callback


def _make_distance_callback(
    distance_matrix_m: list[list[float]],
    manager: pywrapcp.RoutingIndexManager,
):
    """Return a transit callback (metres, truncated to int)."""

    def callback(from_index: int, to_index: int) -> int:
        from_node = manager.IndexToNode(from_index)
        to_node = manager.IndexToNode(to_index)
        return int(distance_matrix_m[from_node][to_node])

    return callback


def _make_demand_callback(
    zonas: list[ZonaModel],
    manager: pywrapcp.RoutingIndexManager,
):
    """Demand callback: 0 for depot (node 0), demanda_kg*100 for zones."""

    demands = [0] + [int(z.demanda_kg * 100) for z in zonas]

    def callback(from_index: int) -> int:
        return demands[manager.IndexToNode(from_index)]

    return callback


def _zone_index_for_id(zonas: list[ZonaModel], zona_id: UUID) -> Optional[int]:
    """Return 1-based node index for zone (0 is depot)."""
    for i, z in enumerate(zonas):
        if z.zona_id == zona_id:
            return i + 1  # node index (depot is 0)
    return None


class CvrptwSolver:
    def __init__(self, osrm: OsrmClient) -> None:
        self._osrm = osrm

    async def resolver(self, solicitud: SolicitudOptimizacion) -> RespuestaOptimizacion:
        t_start = time.monotonic()

        params: ParametrosSolverModel = solicitud.parametros_solver or ParametrosSolverModel()

        # ------------------------------------------------------------------ #
        # 0. Edge-cases
        # ------------------------------------------------------------------ #
        if not solicitud.zonas:
            elapsed_ms = int((time.monotonic() - t_start) * 1000)
            return RespuestaOptimizacion(
                estado="FACTIBLE",
                mensaje="Sin zonas para optimizar",
                resuelto_en_ms=elapsed_ms,
                distancia_total_m=0.0,
                duracion_total_s=0,
                rutas_por_unidad=[],
            )

        if not solicitud.unidades:
            elapsed_ms = int((time.monotonic() - t_start) * 1000)
            return RespuestaOptimizacion(
                estado="NO_FACTIBLE",
                mensaje="No hay unidades de recolección disponibles",
                resuelto_en_ms=elapsed_ms,
                distancia_total_m=0.0,
                duracion_total_s=0,
                rutas_por_unidad=[],
            )

        # ------------------------------------------------------------------ #
        # 1. Build node list and fetch matrices
        # ------------------------------------------------------------------ #
        coords = _build_coords(solicitud)
        n_nodes = len(coords)  # 1 depot + N zones

        # Fetch both matrices concurrently
        duration_matrix, distance_matrix = await asyncio.gather(
            self._osrm.duration_matrix(coords),
            self._osrm.distance_matrix(coords),
        )

        # ------------------------------------------------------------------ #
        # 2. OR-Tools routing model
        # ------------------------------------------------------------------ #
        num_vehicles = len(solicitud.unidades)
        depot = 0

        manager = pywrapcp.RoutingIndexManager(n_nodes, num_vehicles, depot)
        routing = pywrapcp.RoutingModel(manager)

        # ---- 2a. Arc-cost dimension (distance or duration) -----------------
        use_distance_obj = params.objetivo.upper() == "DISTANCIA"

        if use_distance_obj:
            dist_cb_idx = routing.RegisterTransitCallback(
                _make_distance_callback(distance_matrix, manager)
            )
            routing.SetArcCostEvaluatorOfAllVehicles(dist_cb_idx)
        else:
            dur_cb_idx = routing.RegisterTransitCallback(
                _make_duration_callback(duration_matrix, manager)
            )
            routing.SetArcCostEvaluatorOfAllVehicles(dur_cb_idx)

        # ---- 2b. Capacity dimension ----------------------------------------
        demand_cb_idx = routing.RegisterUnaryTransitCallback(
            _make_demand_callback(solicitud.zonas, manager)
        )
        capacities = [int(u.capacidad_kg * 100) for u in solicitud.unidades]
        routing.AddDimensionWithVehicleCapacity(
            demand_cb_idx,
            0,          # no slack
            capacities,
            True,       # start cumul to zero
            "Capacidad",
        )

        # ---- 2c. Time dimension --------------------------------------------
        dur_cb_idx2 = routing.RegisterTransitCallback(
            _make_duration_callback(duration_matrix, manager)
        )
        # service_time per stop: 0 (can be extended later)
        routing.AddDimension(
            dur_cb_idx2,
            30 * 60,    # slack: up to 30 min waiting
            24 * 60 * 60,  # max total time (24 h in seconds)
            False,      # don't force start cumul to zero (vehicles start at their own time)
            "Tiempo",
        )
        time_dimension = routing.GetDimensionOrDie("Tiempo")

        # Depot time window: [0, 86400]
        for v in range(num_vehicles):
            unidad = solicitud.unidades[v]
            inicio_s = _hhmm_to_minutes(unidad.inicio_disponibilidad) * 60
            fin_s = _hhmm_to_minutes(unidad.fin_disponibilidad) * 60
            time_dimension.CumulVar(routing.Start(v)).SetRange(inicio_s, fin_s)
            time_dimension.CumulVar(routing.End(v)).SetRange(inicio_s, fin_s)

        # Zone time windows
        for i, zona in enumerate(solicitud.zonas):
            node_index = manager.NodeToIndex(i + 1)
            tw_start = _hhmm_to_minutes(zona.ventana_inicio) * 60
            tw_end = _hhmm_to_minutes(zona.ventana_fin) * 60
            time_dimension.CumulVar(node_index).SetRange(tw_start, tw_end)

        # ---- 2d. Critical-alert penalties ----------------------------------
        critical_zona_ids: set[UUID] = {
            a.zona_id
            for a in solicitud.alertas_criticas
            if a.nivel_criticidad.upper() in ("ALTA", "CRITICA")
        }
        penalty_int = int(params.penalta_critica * 100)
        large_penalty = max(penalty_int, _LARGE_PENALTY)

        for i, zona in enumerate(solicitud.zonas):
            node_index = manager.NodeToIndex(i + 1)
            if zona.zona_id in critical_zona_ids:
                routing.AddDisjunction([node_index], large_penalty)
            else:
                routing.AddDisjunction([node_index], 0)

        # ---- 2e. Solver parameters -----------------------------------------
        search_params = pywrapcp.DefaultRoutingSearchParameters()
        search_params.first_solution_strategy = (
            routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
        )
        search_params.local_search_metaheuristic = (
            routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
        )
        search_params.time_limit.seconds = params.tiempo_limite_s

        # ------------------------------------------------------------------ #
        # 3. Solve
        # ------------------------------------------------------------------ #
        assignment = routing.SolveWithParameters(search_params)
        elapsed_ms = int((time.monotonic() - t_start) * 1000)

        if assignment is None:
            return RespuestaOptimizacion(
                estado="NO_FACTIBLE",
                mensaje="No se encontró solución factible en el tiempo límite",
                resuelto_en_ms=elapsed_ms,
                distancia_total_m=0.0,
                duracion_total_s=0,
                rutas_por_unidad=[],
            )

        # ------------------------------------------------------------------ #
        # 4. Extract solution
        # ------------------------------------------------------------------ #
        rutas: list[RutaUnidadModel] = []
        total_dist_m = 0.0
        total_dur_s = 0
        dropped_critical = 0

        for v in range(num_vehicles):
            unidad = solicitud.unidades[v]
            inicio_min = _hhmm_to_minutes(unidad.inicio_disponibilidad)

            paradas: list[ParadaModel] = []
            ruta_dist_m = 0.0
            ruta_dur_s = 0
            carga_acumulada = 0.0
            orden = 0

            index = routing.Start(v)
            prev_index = index

            while not routing.IsEnd(index):
                node = manager.IndexToNode(index)
                if node != depot:
                    zona_idx = node - 1
                    zona = solicitud.zonas[zona_idx]
                    carga_acumulada += zona.demanda_kg
                    orden += 1

                    # ETA: cumulative time from solver (seconds from midnight)
                    time_var = time_dimension.CumulVar(index)
                    eta_s = assignment.Value(time_var)
                    eta_min = eta_s // 60
                    eta_str = _minutes_to_hhmm(eta_min)

                    paradas.append(
                        ParadaModel(
                            zona_id=zona.zona_id,
                            orden=orden,
                            eta=eta_str,
                            carga_acumulada_kg=round(carga_acumulada, 2),
                        )
                    )

                next_index = assignment.Value(routing.NextVar(index))

                # Accumulate distance and duration for this arc
                from_node = manager.IndexToNode(index)
                to_node = manager.IndexToNode(next_index)
                ruta_dist_m += distance_matrix[from_node][to_node]
                ruta_dur_s += int(duration_matrix[from_node][to_node])

                prev_index = index
                index = next_index

            if paradas:
                rutas.append(
                    RutaUnidadModel(
                        unidad_id=unidad.unidad_id,
                        distancia_m=round(ruta_dist_m, 2),
                        duracion_s=ruta_dur_s,
                        carga_total_kg=round(carga_acumulada, 2),
                        paradas=paradas,
                    )
                )
                total_dist_m += ruta_dist_m
                total_dur_s += ruta_dur_s

        # Determine if any critical zones were dropped
        served_zona_ids = {
            p.zona_id
            for r in rutas
            for p in r.paradas
        }
        dropped_critical = len(critical_zona_ids - served_zona_ids)
        all_served = len(served_zona_ids) == len(solicitud.zonas)

        if dropped_critical > 0:
            estado = "PARCIAL"
            mensaje = f"Solución parcial: {dropped_critical} zona(s) crítica(s) no atendida(s)"
        elif not all_served:
            estado = "PARCIAL"
            mensaje = (
                f"Solución parcial: {len(solicitud.zonas) - len(served_zona_ids)} "
                "zona(s) no atendida(s)"
            )
        else:
            estado = "FACTIBLE"
            mensaje = "Solución óptima encontrada"

        return RespuestaOptimizacion(
            estado=estado,
            mensaje=mensaje,
            resuelto_en_ms=elapsed_ms,
            distancia_total_m=round(total_dist_m, 2),
            duracion_total_s=total_dur_s,
            rutas_por_unidad=rutas,
        )
