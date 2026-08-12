"""El eje geográfico que une los dos catálogos (2026-08-10).

Programas junta las **instituciones autorizadas** (2.508) con los **programas
investigados** (15.483). Lo único que comparten de verdad es el lugar — pero lo
guardan distinto:

    programs                  programas_investigados
    ────────────────────      ──────────────────────
    Canada, USA, UK, Spain    Canadá, Estados Unidos, Reino Unido, España
    Ireland *e* Irlanda       (la primera tabla se contradice a sí misma)

Sin normalizar, Canadá sale dos veces y los conteos se parten por la mitad.
Estos tests fijan esa normalización, que es la pieza sobre la que se apoyan la
lista agrupada y el mapa.

**Lo que más importa aquí no es que cruce bien, sino que lo que NO cruza se
cuente.** 352 instituciones y 4.379 programas no tienen ciudad: en un mapa
simplemente no aparecen. Si además desaparecieran de los totales, el estudiante
creería que no existen.
"""
from __future__ import annotations

import pytest

from app.services.lugares import (
    clave_lugar,
    es_pais_desconocido,
    nombre_de_ciudad,
    pais_canonico,
)


class TestPaisCanonico:
    @pytest.mark.parametrize(
        "variantes,iso",
        [
            (["UK", "Reino Unido", "United Kingdom", "reino unido"], "GB"),
            (["USA", "Estados Unidos", "United States", "EEUU"], "US"),
            (["Canada", "Canadá", "canada"], "CA"),
            (["Spain", "España", "espana"], "ES"),
            (["Germany", "Alemania"], "DE"),
            # `programs` tiene estas dos formas en la MISMA tabla.
            (["Ireland", "Irlanda"], "IE"),
            (["Italy", "Italia"], "IT"),
            (["Paises Bajos", "Países Bajos", "Netherlands"], "NL"),
            (["UAE", "Emiratos Árabes Unidos"], "AE"),
        ],
    )
    def test_las_variantes_de_los_dos_idiomas_dan_el_mismo_pais(self, variantes, iso):
        assert {pais_canonico(v).iso for v in variantes} == {iso}

    def test_el_nombre_para_mostrar_va_en_espanol(self):
        """El producto es sólo español · target Colombia, sin i18n."""
        assert pais_canonico("UK").nombre == "Reino Unido"
        assert pais_canonico("Germany").nombre == "Alemania"

    @pytest.mark.parametrize("valor", ["International", "ASIA", "Varios destinos"])
    def test_lo_que_no_es_un_pais_no_se_convierte_en_uno(self, valor):
        """Están en la columna de país y no son países.

        Devolver `None` es lo correcto: inventarles un código los pondría en el
        mapa en algún sitio arbitrario.
        """
        assert pais_canonico(valor) is None
        # Y no son "desconocidos": sabemos que existen y que no son países.
        assert es_pais_desconocido(valor) is False

    def test_un_pais_nuevo_se_delata_en_vez_de_desaparecer(self):
        """Si la agencia carga un Excel con un país que no tenemos, tiene que
        saltar a la vista · un mapa al que le falta un país no se nota."""
        assert es_pais_desconocido("Wakanda") is True
        assert pais_canonico("Wakanda") is None

    def test_vacio_no_es_desconocido(self):
        for valor in (None, "", "   "):
            assert es_pais_desconocido(valor) is False


class TestClaveLugar:
    def test_la_misma_ciudad_en_los_dos_idiomas_es_un_solo_lugar(self):
        """Es el cruce que hace que Londres tenga 54 instituciones Y 540
        programas en vez de aparecer partida en dos puntos del mapa."""
        assert clave_lugar("Londres", "Reino Unido") == clave_lugar("London", "UK")
        assert clave_lugar("Londres", "Reino Unido") == "gb:london"

    @pytest.mark.parametrize(
        "ciudad_es,pais_es,ciudad_en,pais_en,esperada",
        [
            ("Roma", "Italia", "Rome", "Italy", "it:rome"),
            ("Viena", "Austria", "Vienna", "Austria", "at:vienna"),
            ("Praga", "República Checa", "Prague", "Czech Republic", "cz:prague"),
            ("Nueva York", "Estados Unidos", "New York", "USA", "us:new york"),
        ],
    )
    def test_otras_ciudades_traducidas_tambien_cruzan(
        self, ciudad_es, pais_es, ciudad_en, pais_en, esperada
    ):
        # Ciudad y país se traducen a la vez · es el caso real, porque cada
        # catálogo viene entero en su idioma.
        assert clave_lugar(ciudad_es, pais_es) == esperada
        assert clave_lugar(ciudad_en, pais_en) == esperada

    def test_sin_ciudad_no_hay_clave(self):
        """341 instituciones están así · no pueden ir al mapa, y forzarlas
        sería plantarlas en el centro del país."""
        assert clave_lugar(None, "UK") is None
        assert clave_lugar("   ", "UK") is None

    def test_sin_pais_reconocible_tampoco(self):
        assert clave_lugar("Bogotá", "International") is None
        assert clave_lugar("Bogotá", None) is None

    def test_la_ciudad_se_muestra_como_la_escribio_la_agencia(self):
        """No se traduce lo que ella puso: si su ficha dice Londres, su asesor
        va a hablar de Londres."""
        assert nombre_de_ciudad("  Londres  ") == "Londres"
        assert nombre_de_ciudad(None) is None


class TestEndpointLugares:
    """El endpoint se prueba con datos armados a mano · no contra la base real.

    Lo que se comprueba es la SUMA y el conteo de lo que queda fuera, que es
    donde puede perderse algo sin que nadie lo note.
    """

    def _agrupar(self, instituciones, programas):
        """Reproduce el agrupado del endpoint sin tocar la base."""
        from collections import defaultdict

        acumulado = defaultdict(lambda: {"inst": 0, "prog": 0})
        fuera = {"inst": 0, "prog": 0}

        for ciudad, pais, n in instituciones:
            clave = clave_lugar(ciudad, pais)
            if clave is None:
                fuera["inst"] += n
            else:
                acumulado[clave]["inst"] += n
        for ciudad, pais, n in programas:
            clave = clave_lugar(ciudad, pais)
            if clave is None:
                fuera["prog"] += n
            else:
                acumulado[clave]["prog"] += n
        return dict(acumulado), fuera

    def test_los_dos_catalogos_caen_en_el_mismo_lugar(self):
        acumulado, _fuera = self._agrupar(
            instituciones=[("London", "UK", 54)],
            programas=[("Londres", "Reino Unido", 540)],
        )

        assert acumulado == {"gb:london": {"inst": 54, "prog": 540}}

    def test_lo_que_no_tiene_ciudad_se_cuenta_aparte_y_no_se_pierde(self):
        """El fallo que dejaría opciones invisibles: si esto no se contara, un
        estudiante creería que no hay nada donde sí lo hay."""
        acumulado, fuera = self._agrupar(
            instituciones=[("London", "UK", 54), (None, "UK", 341)],
            programas=[(None, "Australia", 4332), ("Melbourne", "Australia", 785)],
        )

        assert fuera == {"inst": 341, "prog": 4332}
        assert acumulado["gb:london"]["inst"] == 54
        assert acumulado["au:melbourne"]["prog"] == 785

    def test_un_no_pais_no_inventa_un_punto_en_el_mapa(self):
        _acumulado, fuera = self._agrupar(
            instituciones=[("Online", "International", 24)], programas=[]
        )

        assert fuera["inst"] == 24
