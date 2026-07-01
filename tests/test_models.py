"""
Tests de validación de modelos Pydantic.

Datos basados en operaciones reales de recolección de residuos sólidos
de la Municipalidad Metropolitana de Lima (MML / EMILIMA).
"""
from datetime import date
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from app.domain.models import (
    AlertaCriticaModel,
    ParametrosSolverModel,
    RespuestaOptimizacion,
    RutaUnidadModel,
    SolicitudOptimizacion,
    UbicacionModel,
    UnidadModel,
    ZonaModel,
    ParadaModel,
)


# ---------------------------------------------------------------------------
# UbicacionModel
# ---------------------------------------------------------------------------

class TestUbicacionModel:
    def test_coordenadas_estacion_transferencia_lima_norte(self):
        """Estación de Transferencia Lima Norte, Carabayllo — coordenadas válidas."""
        loc = UbicacionModel(latitud=-11.8456, longitud=-77.0023)
        assert loc.latitud == pytest.approx(-11.8456)
        assert loc.longitud == pytest.approx(-77.0023)

    def test_coordenadas_relleno_sanitario_portillo_grande(self):
        """Relleno Sanitario Portillo Grande, Lurín."""
        loc = UbicacionModel(latitud=-12.2780, longitud=-76.8750)
        assert loc.latitud == pytest.approx(-12.2780)
        assert loc.longitud == pytest.approx(-76.8750)

    def test_requiere_latitud(self):
        with pytest.raises(ValidationError):
            UbicacionModel(longitud=-77.0617)

    def test_requiere_longitud(self):
        with pytest.raises(ValidationError):
            UbicacionModel(latitud=-12.0612)


# ---------------------------------------------------------------------------
# UnidadModel
# ---------------------------------------------------------------------------

class TestUnidadModel:
    def test_camion_compactador_cam4892_turno_manaña(self):
        """Camión CAM-4892, turno matutino Miraflores 05:00–13:00."""
        u = UnidadModel(
            unidad_id=UUID("aaaaaaa1-0000-0000-0000-000000000001"),
            capacidad_kg=8000.0,
            inicio_disponibilidad="05:00",
            fin_disponibilidad="13:00",
        )
        assert u.capacidad_kg == 8000.0
        assert u.inicio_disponibilidad == "05:00"
        assert u.fin_disponibilidad == "13:00"

    def test_unidad_sin_id_falla(self):
        with pytest.raises(ValidationError):
            UnidadModel(
                capacidad_kg=7500.0,
                inicio_disponibilidad="05:30",
                fin_disponibilidad="13:30",
            )

    def test_unidad_capacidad_negativa_no_es_bloqueada_por_pydantic(self):
        """Pydantic no restringe floats negativos salvo que se indique ge=0."""
        u = UnidadModel(
            unidad_id=uuid4(),
            capacidad_kg=-1.0,
            inicio_disponibilidad="06:00",
            fin_disponibilidad="14:00",
        )
        assert u.capacidad_kg == -1.0


# ---------------------------------------------------------------------------
# ZonaModel
# ---------------------------------------------------------------------------

class TestZonaModel:
    def test_zona_miraflores_centro(self):
        """Zona ZM-01, Av. Larco, Miraflores — prioridad alta, 450 kg/día."""
        z = ZonaModel(
            zona_id=UUID("bbbbbb01-0000-0000-0000-000000000001"),
            latitud=-12.1179,
            longitud=-77.0330,
            demanda_kg=450.0,
            ventana_inicio="06:00",
            ventana_fin="10:00",
            prioridad=3,
        )
        assert z.demanda_kg == 450.0
        assert z.prioridad == 3
        assert z.ventana_inicio == "06:00"

    def test_zona_surquillo_norte(self):
        """Zona ZSQ-01, Av. República de Panamá — demanda alta, 520 kg/día."""
        z = ZonaModel(
            zona_id=UUID("bbbbbb03-0000-0000-0000-000000000003"),
            latitud=-12.1080,
            longitud=-77.0200,
            demanda_kg=520.0,
            ventana_inicio="06:00",
            ventana_fin="11:00",
            prioridad=3,
        )
        assert z.demanda_kg == 520.0
        assert z.longitud == pytest.approx(-77.0200)

    def test_zona_sin_id_falla(self):
        with pytest.raises(ValidationError):
            ZonaModel(
                latitud=-12.1179,
                longitud=-77.0330,
                demanda_kg=450.0,
                ventana_inicio="06:00",
                ventana_fin="10:00",
                prioridad=3,
            )


# ---------------------------------------------------------------------------
# AlertaCriticaModel
# ---------------------------------------------------------------------------

class TestAlertaCriticaModel:
    def test_alerta_critica_miraflores_centro(self):
        a = AlertaCriticaModel(
            alerta_id=UUID("cccccc01-0000-0000-0000-000000000001"),
            zona_id=UUID("bbbbbb01-0000-0000-0000-000000000001"),
            nivel_criticidad="CRITICA",
        )
        assert a.nivel_criticidad == "CRITICA"

    def test_nivel_criticidad_alta(self):
        a = AlertaCriticaModel(
            alerta_id=uuid4(),
            zona_id=uuid4(),
            nivel_criticidad="ALTA",
        )
        assert a.nivel_criticidad == "ALTA"


# ---------------------------------------------------------------------------
# ParametrosSolverModel — defaults y validación
# ---------------------------------------------------------------------------

class TestParametrosSolverModel:
    def test_defaults_razonables(self):
        p = ParametrosSolverModel()
        assert p.tiempo_limite_s == 30
        assert p.objetivo == "DISTANCIA"
        assert p.penalta_critica == 1000.0

    def test_tiempo_limite_minimo_1(self):
        with pytest.raises(ValidationError):
            ParametrosSolverModel(tiempo_limite_s=0)

    def test_tiempo_limite_personalizado(self):
        p = ParametrosSolverModel(tiempo_limite_s=60, objetivo="TIEMPO")
        assert p.tiempo_limite_s == 60
        assert p.objetivo == "TIEMPO"


# ---------------------------------------------------------------------------
# SolicitudOptimizacion
# ---------------------------------------------------------------------------

class TestSolicitudOptimizacion:
    def test_solicitud_completa_miraflores(self):
        """Solicitud real: turno matutino Miraflores, lunes 2026-06-29."""
        solicitud = SolicitudOptimizacion(
            tenant_id=UUID("11111111-1111-1111-1111-111111111111"),
            distrito_id=UUID("22222222-2222-2222-2222-222222222222"),
            fecha_operacion=date(2026, 6, 29),
            deposito_inicio=UbicacionModel(latitud=-12.0612, longitud=-77.0617),
            deposito_fin=UbicacionModel(latitud=-12.2780, longitud=-76.8750),
            unidades=[
                UnidadModel(
                    unidad_id=UUID("aaaaaaa1-0000-0000-0000-000000000001"),
                    capacidad_kg=8000.0,
                    inicio_disponibilidad="05:00",
                    fin_disponibilidad="13:00",
                )
            ],
            zonas=[
                ZonaModel(
                    zona_id=UUID("bbbbbb01-0000-0000-0000-000000000001"),
                    latitud=-12.1179,
                    longitud=-77.0330,
                    demanda_kg=450.0,
                    ventana_inicio="06:00",
                    ventana_fin="10:00",
                    prioridad=3,
                )
            ],
            alertas_criticas=[],
        )
        assert len(solicitud.unidades) == 1
        assert len(solicitud.zonas) == 1
        assert solicitud.alertas_criticas == []
        assert solicitud.parametros_solver is None

    def test_solicitud_sin_zonas_ni_unidades_es_valida(self):
        """El modelo no impone min-length — la lógica de negocio está en el solver."""
        solicitud = SolicitudOptimizacion(
            tenant_id=UUID("11111111-1111-1111-1111-111111111111"),
            distrito_id=UUID("22222222-2222-2222-2222-222222222222"),
            fecha_operacion=date(2026, 6, 29),
            deposito_inicio=UbicacionModel(latitud=-12.0612, longitud=-77.0617),
            deposito_fin=UbicacionModel(latitud=-12.0612, longitud=-77.0617),
            unidades=[],
            zonas=[],
        )
        assert solicitud.unidades == []
        assert solicitud.zonas == []

    def test_solicitud_falta_tenant_falla(self):
        with pytest.raises(ValidationError):
            SolicitudOptimizacion(
                distrito_id=uuid4(),
                fecha_operacion=date(2026, 6, 29),
                deposito_inicio=UbicacionModel(latitud=-12.0612, longitud=-77.0617),
                deposito_fin=UbicacionModel(latitud=-12.0612, longitud=-77.0617),
                unidades=[],
                zonas=[],
            )


# ---------------------------------------------------------------------------
# RespuestaOptimizacion
# ---------------------------------------------------------------------------

class TestRespuestaOptimizacion:
    def test_respuesta_factible_miraflores(self):
        """Respuesta típica: ruta factible Miraflores Centro."""
        r = RespuestaOptimizacion(
            estado="FACTIBLE",
            mensaje="Solución óptima encontrada",
            resuelto_en_ms=320,
            distancia_total_m=8500.0,
            duracion_total_s=3600,
            rutas_por_unidad=[],
        )
        assert r.estado == "FACTIBLE"
        assert r.distancia_total_m == pytest.approx(8500.0)
        assert r.duracion_total_s == 3600

    def test_respuesta_no_factible_sin_unidades(self):
        r = RespuestaOptimizacion(
            estado="NO_FACTIBLE",
            mensaje="No hay unidades de recolección disponibles",
            resuelto_en_ms=1,
            distancia_total_m=0.0,
            duracion_total_s=0,
            rutas_por_unidad=[],
        )
        assert r.estado == "NO_FACTIBLE"
        assert r.rutas_por_unidad == []

    def test_respuesta_con_ruta_unidad(self):
        ruta = RutaUnidadModel(
            unidad_id=UUID("aaaaaaa1-0000-0000-0000-000000000001"),
            distancia_m=4200.0,
            duracion_s=1800,
            carga_total_kg=450.0,
            paradas=[
                ParadaModel(
                    zona_id=UUID("bbbbbb01-0000-0000-0000-000000000001"),
                    orden=1,
                    eta="06:15",
                    carga_acumulada_kg=450.0,
                )
            ],
        )
        r = RespuestaOptimizacion(
            estado="FACTIBLE",
            mensaje="Solución óptima encontrada",
            resuelto_en_ms=250,
            distancia_total_m=4200.0,
            duracion_total_s=1800,
            rutas_por_unidad=[ruta],
        )
        assert len(r.rutas_por_unidad) == 1
        assert r.rutas_por_unidad[0].carga_total_kg == 450.0
        assert r.rutas_por_unidad[0].paradas[0].eta == "06:15"
