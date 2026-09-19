"""La familia profesional como eje para recorrer el catálogo · Fase 3.

El recorrido de siempre es `país → área → programa`: una taxonomía
administrativa. Este es el del consejero — "esta familia te calza porque [lo
tuyo]; esto es lo que existe de ella" — y es lo que la clienta pidió el
2026-09-06 al hablar de "consejería de las familias más adecuadas".

Medido en local el 2026-09-19 con un perfil real de 11° (5 familias):

    las 5 familias devolvieron 5 listas distintas · 0 programas en común en 9
    de los 10 pares, 1 de 8 en el par más cercano (salud animal vs humana)
    36 de 40 resultados NO aparecían ordenando por el perfil entero

O sea que el eje no es cosmético: abre catálogo que antes era invisible.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.services import familias_programas as fam


def _familia(nombre="Salud y cuidado animal", careers=("Medicina veterinaria",
                                                       "Etología clínica"),
             como_es="Turnos largos y contacto directo con animales.",
             por_que="Porque contaste que cuidas perros callejeros con tu mamá.",
             calce="alto", ojo=None):
    return {"name": nombre, "fit_level": calce, "why_it_fits": por_que,
            "what_its_like": como_es, "careers": list(careers), "watch_out": ojo}


def _db(profile_data):
    db = MagicMock()
    cadena = db.query.return_value
    cadena.filter.return_value = cadena
    cadena.first.return_value = (
        SimpleNamespace(profile_data=profile_data) if profile_data is not None
        else None
    )
    return db


_USUARIO = SimpleNamespace(id=uuid4())


# ---------------------------------------------------------------------------
# Qué se embebe · y sobre todo qué NO
# ---------------------------------------------------------------------------


def test_el_texto_lleva_nombre_oficios_y_como_es():
    texto = fam.texto_de_familia(_familia())
    assert "Salud y cuidado animal" in texto
    assert "Medicina veterinaria" in texto
    assert "Turnos largos" in texto


def test_los_oficios_van_antes_que_la_descripcion():
    """Los oficios son lo que de verdad se parece al nombre de un programa;
    el día a día es contexto. El orden pesa en el vector."""
    texto = fam.texto_de_familia(_familia())
    assert texto.index("Medicina veterinaria") < texto.index("Turnos largos")


def test_el_porque_le_calza_NO_se_embebe():
    """El test que protege la decisión de diseño.

    `why_it_fits` está en segunda persona y habla de la PERSONA, no del campo.
    Embeberlo acercaría la familia a programas que mencionen perros en vez de a
    programas de veterinaria — misma razón por la que `texto_de_programa`
    excluye el país.
    """
    texto = fam.texto_de_familia(_familia())
    assert "perros callejeros" not in texto
    assert "Porque contaste" not in texto


def test_el_ojo_con_tampoco_se_embebe():
    """`watch_out` es una advertencia para la persona ("exige química fuerte"),
    no una descripción del campo · embeberla traería programas de química."""
    texto = fam.texto_de_familia(_familia(ojo="Exige química y biología fuertes."))
    assert "química" not in texto.lower()


def test_una_familia_sin_nada_util_da_texto_vacio():
    """Y `vector_de_familia` lo usa para no pedirle un embedding al proveedor
    por una cadena vacía, que ademas la API rechaza."""
    assert fam.texto_de_familia({"name": "", "careers": [], "what_its_like": ""}) == ""


# ---------------------------------------------------------------------------
# Leer las familias del perfil
# ---------------------------------------------------------------------------


def test_se_leen_en_el_orden_del_consejo():
    """El modelo las devuelve por calce y ese orden ES parte del consejo · el
    índice de la URL depende de él."""
    datos = {"career_families": [_familia("Primera"), _familia("Segunda")]}
    fs = fam.familias_del_usuario(_db(datos), _USUARIO)
    assert [f["name"] for f in fs] == ["Primera", "Segunda"]


def test_un_perfil_a_medio_hacer_no_revienta():
    """Se lee el JSON crudo y NO se valida contra `ConsolidatedProfile`: ese
    schema exige 200+ caracteres de narrativa, y quedarse sin navegación por
    una validación que al estudiante no le importa sería absurdo."""
    datos = {"career_families": [_familia()], "summary_narrative": "corto"}
    assert len(fam.familias_del_usuario(_db(datos), _USUARIO)) == 1


@pytest.mark.parametrize("datos", [None, {}, {"career_families": None},
                                   {"career_families": ["texto suelto"]},
                                   {"career_families": [{"name": "  "}]}])
def test_sin_familias_devuelve_lista_vacia(datos):
    """Los perfiles anteriores a `consolidate_v2` no las traen. Lista vacía no
    es un error: la pantalla cae al recorrido país → área de siempre."""
    assert fam.familias_del_usuario(_db(datos), _USUARIO) == []


def test_se_topan_en_cinco():
    datos = {"career_families": [_familia(f"F{i}") for i in range(9)]}
    assert len(fam.familias_del_usuario(_db(datos), _USUARIO)) == fam.MAX_FAMILIAS


def test_un_indice_viejo_no_es_un_error():
    """El estudiante guardó la URL, el perfil se regeneró y ahora hay 4 familias
    en vez de 5. Devolver None y caer a la búsqueda normal es mejor que un 404
    sobre una pantalla que sí tiene qué mostrar."""
    db = _db({"career_families": [_familia("Única")]})
    assert fam.familia_por_indice(db, _USUARIO, 0)["name"] == "Única"
    assert fam.familia_por_indice(db, _USUARIO, 7) is None
    assert fam.familia_por_indice(db, _USUARIO, -1) is None


# ---------------------------------------------------------------------------
# El contexto que ve el estudiante · texto ya escrito, nada generado
# ---------------------------------------------------------------------------


def test_el_contexto_trae_el_porque_y_el_ojo_con():
    """Aquí SÍ viajan · son para leerlos, no para embeberlos. La distinción
    entre lo que ordena el catálogo y lo que explica el catálogo."""
    c = fam.contexto_de_familia(_familia(ojo="Exige química fuerte."))
    assert "perros callejeros" in c["por_que_calza"]
    assert c["ojo_con"] == "Exige química fuerte."
    assert c["calce"] == "alto"
    assert "Medicina veterinaria" in c["oficios"]


def test_el_contexto_tolera_una_familia_sin_ojo_con():
    assert fam.contexto_de_familia(_familia())["ojo_con"] is None


# ---------------------------------------------------------------------------
# El vector · caché por firma y degradación
# ---------------------------------------------------------------------------


def _con_proveedor(monkeypatch, vector=None, falla=False, guardado=None):
    """Dobla la FRONTERA (el proveedor de embeddings y la caché), no el servicio."""
    llamadas = {"n": 0}

    async def _embeber_uno(texto):
        llamadas["n"] += 1
        if falla:
            raise RuntimeError("el proveedor se cayó")
        return vector or [0.1] * 1536

    from app.services import embeddings as emb

    monkeypatch.setattr(emb, "embeber_uno", _embeber_uno)

    sesion = MagicMock()
    sesion.execute.return_value.mappings.return_value.first.return_value = guardado
    monkeypatch.setattr("app.db.database.SessionLocal", lambda: sesion)
    return llamadas, sesion


def test_se_pide_el_vector_y_se_guarda(monkeypatch):
    llamadas, sesion = _con_proveedor(monkeypatch)
    db = _db({"career_families": [_familia()]})
    v = asyncio.run(fam.vector_de_familia(db, _USUARIO, 0))
    assert v and len(v) == 1536
    assert llamadas["n"] == 1
    assert sesion.commit.called, "sin commit el vector se recalcula en cada visita"


def test_con_la_firma_igual_no_se_le_pide_nada_al_proveedor(monkeypatch):
    """Es el punto entero de la caché: una dependencia de red menos en el
    camino crítico de una pantalla que se abre todo el tiempo."""
    texto = fam.texto_de_familia(_familia())
    guardado = {"firma": fam._firma(texto), "emb": "[" + ",".join(["0.5"] * 4) + "]"}
    llamadas, _ = _con_proveedor(monkeypatch, guardado=guardado)
    db = _db({"career_families": [_familia()]})
    v = asyncio.run(fam.vector_de_familia(db, _USUARIO, 0))
    assert v == [0.5, 0.5, 0.5, 0.5]
    assert llamadas["n"] == 0


def test_si_el_modelo_reescribio_la_familia_el_vector_se_rehace(monkeypatch):
    """El perfil se regenera cada 24h y el modelo reescribe las familias. Sin
    esto, el catálogo se seguiría ordenando por la familia del día anterior."""
    guardado = {"firma": "firma-de-otra-familia", "emb": "[0.9,0.9]"}
    llamadas, _ = _con_proveedor(monkeypatch, guardado=guardado)
    db = _db({"career_families": [_familia()]})
    asyncio.run(fam.vector_de_familia(db, _USUARIO, 0))
    assert llamadas["n"] == 1


def test_si_el_proveedor_falla_se_usa_el_vector_viejo(monkeypatch):
    """Un orden de ayer ordena muchísimo mejor que ningún orden."""
    guardado = {"firma": "vieja", "emb": "[0.3,0.3]"}
    _con_proveedor(monkeypatch, falla=True, guardado=guardado)
    db = _db({"career_families": [_familia()]})
    assert asyncio.run(fam.vector_de_familia(db, _USUARIO, 0)) == [0.3, 0.3]


def test_si_falla_y_no_hay_nada_viejo_devuelve_none(monkeypatch):
    """None hace que el endpoint caiga al vector del perfil · nunca a vacío."""
    _con_proveedor(monkeypatch, falla=True, guardado=None)
    db = _db({"career_families": [_familia()]})
    assert asyncio.run(fam.vector_de_familia(db, _USUARIO, 0)) is None


def test_un_indice_inexistente_no_le_pide_nada_al_proveedor(monkeypatch):
    llamadas, _ = _con_proveedor(monkeypatch)
    db = _db({"career_families": [_familia()]})
    assert asyncio.run(fam.vector_de_familia(db, _USUARIO, 4)) is None
    assert llamadas["n"] == 0


def test_la_cache_usa_su_propia_sesion(monkeypatch):
    """⚠️ No es un detalle de estilo · está medido.

    Guardar exige un commit, y un commit expira todos los objetos ORM de esa
    sesión. Quien llama ya cargó fichas del catálogo antes de pedir el vector:
    con el commit sobre SU sesión, SQLAlchemy las vuelve a pedir una por una a
    Neon y la petición se cuelga. Mismo caso documentado en `vector_del_perfil`.
    """
    _, propia = _con_proveedor(monkeypatch)
    db = _db({"career_families": [_familia()]})
    asyncio.run(fam.vector_de_familia(db, _USUARIO, 0))
    assert propia.commit.called
    assert not db.commit.called, "commiteó sobre la sesión de quien llama"
    assert propia.close.called, "la sesión propia se queda abierta"


# ---------------------------------------------------------------------------
# El refuerzo RIASEC se apaga dentro de una familia
# ---------------------------------------------------------------------------


def test_el_peso_de_afinidad_se_puede_apagar_sin_perder_la_trazabilidad():
    """Medido: con el refuerzo puesto, 3 de los 6 primeros de "Salud y cuidado
    animal" se volvían medicina HUMANA, porque el código Social del estudiante
    premia "Salud y Medicina" sobre "Agricultura y Veterinaria" — que sólo es
    afín al código Realista, y por tanto puntúa 0 para un perfil S-I-A.

    Pero `afinidad` tiene que seguir viajando: es la trazabilidad con la que un
    asesor explica un resultado (ver el docstring de `Resultado`).
    """
    from app.services.areas import SALUD
    from app.services.busqueda_programas import _a_resultado

    fila = {"id": uuid4(), "nombre": "Veterinary Assistant", "institucion": "X",
            "pais": "Canadá", "ciudad": None, "nivel": "diploma",
            # La constante, no la cadena a mano: un fixture con un área que el
            # vocabulario no tiene da afinidad 0 y el test deja de probar nada.
            "area": SALUD, "duracion": None, "codigo_oficial": None,
            "url_fuente": None, "program_id": None, "confianza": "publicado",
            "oferta_slug": None, "oferta_nombre": None, "sim": 0.5}

    con = _a_resultado(fila, ["S", "I", "A"])
    sin = _a_resultado(fila, ["S", "I", "A"], peso_afinidad=0.0)

    assert con.afinidad > 0, "el caso de prueba no ejercita nada si la afinidad es 0"
    assert sin.afinidad == con.afinidad, "la trazabilidad se perdió"
    assert sin.puntaje == sin.similitud, "el refuerzo siguió pesando"
    assert con.puntaje > sin.puntaje
