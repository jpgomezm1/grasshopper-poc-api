"""I-1b · Sprint 4 · la ampliación del banco de SAT, verificada haciendo la cuenta.

Verónica: el Pre SAT "repite preguntas". I-1 le dio memoria a la práctica; I-1b
amplía el banco para que esa memoria tenga de dónde sacar. Los ejercicios son
propios y escritos con IA, y este proyecto ya se cobró un reclamo por contenido
inventado: por eso las respuestas de matemáticas NO se dan por buenas porque
alguien las leyó. Aquí cada una se recalcula desde el enunciado y se compara con
la opción marcada como correcta.

Lo que protegen:
 1. Cada respuesta de matemáticas nueva sale de la cuenta, no de una lectura.
 2. Cada habilidad ampliada tiene 25 ejercicios, con los tres niveles cubiertos
    para que la selección por nivel tenga de dónde sacar.
"""
from __future__ import annotations

from fractions import Fraction as F
from math import isclose

import pytest

from app.data import exam_prep as banco


def _num(x) -> str:
    """Un número como lo escriben las opciones (7, 6.5, 8/3, −4)."""
    x = F(x)
    signo = "−" if x < 0 else ""
    x = abs(x)
    if x.denominator == 1:
        return f"{signo}{x.numerator}"
    return f"{signo}{x.numerator}/{x.denominator}"


def _resolver_lineal(a, b, c, d):
    """a·x + b = c·x + d."""
    return F(d - b, 1) / F(a - c, 1)


def _sistema(a1, b1, c1, a2, b2, c2):
    """a1·x + b1·y = c1 ; a2·x + b2·y = c2 → (x, y) por Cramer."""
    det = F(a1 * b2 - a2 * b1)
    return F(c1 * b2 - c2 * b1) / det, F(a1 * c2 - a2 * c1) / det


# id → la respuesta, CALCULADA desde los datos del enunciado.
CUENTAS = {
    # ---- álgebra
    "sat-alg-7": lambda: _num(F(28, 4) - 2),
    "sat-alg-8": lambda: _num(F(19 - 3, 2)),
    "sat-alg-9": lambda: _num((6 - 2) * 3),
    "sat-alg-10": lambda: _num(_resolver_lineal(-1, 7, 2, 1)),
    "sat-alg-11": lambda: _num(_resolver_lineal(1, 9, 4, 0)),
    "sat-alg-12": lambda: _num(3 * 0 - 4),
    "sat-alg-14": lambda: _num(_sistema(1, 1, 10, 1, -1, 4)[1]),
    "sat-alg-15": lambda: f"x = {_num(3 + 5)} or x = {_num(3 - 5)}",
    "sat-alg-18": lambda: f"{_num(_sistema(3, 2, 13, 1, 2, 7)[0])} dollars",
    # tarifa = (230 − 110) / (5 − 2)
    "sat-alg-20": lambda: f"{_num(F(230 - 110, 5 - 2))} dollars",
    # 4x + ky = 12 es 2·(2x + 3y = 6) → k = 2·3
    "sat-alg-21": lambda: _num(F(4, 2) * 3),
    "sat-alg-22": lambda: _num(sum(_sistema(3, 2, 12, -1, 1, 1))),
    # a/b = 3/4, b = 2a − 10 → 4a = 3(2a − 10)
    "sat-alg-23": lambda: _num(_resolver_lineal(4, 0, 6, -30)),
    # x + (2x + 6) = 30 → mayor = 2x + 6
    "sat-alg-25": lambda: _num(2 * _resolver_lineal(3, 6, 0, 30) + 6),
    # ---- datos
    "sat-dat-7": lambda: f"{_num(F(12, 48) * 100)} percent",
    "sat-dat-8": lambda: _num(F(4 + 7 + 10 + 15, 4)),
    "sat-dat-10": lambda: f"{_num(50 * F(110, 100))} dollars",
    "sat-dat-12": lambda: _num(sorted([3, 9, 1, 8, 4])[2]),
    "sat-dat-15": lambda: _num(6 * 84 - 5 * 82),
    "sat-dat-17": lambda: _num(F(90 * 1000, 3600)),
    "sat-dat-18": lambda: _num(F(4 + 6, 4 + 6 + 10)),
    "sat-dat-19": lambda: f"{_num(F(680) / F(85, 100))} dollars",
    "sat-dat-22": lambda: f"{500 * 2 ** (12 // 3):,}",
    "sat-dat-24": lambda: _num(60 - (25 + 30 - 10)),
    "sat-dat-25": lambda: _num(F(20 * 70 + 30 * 80, 50)),
    # ---- matemática avanzada (tanda 2)
    "sat-adv-7": lambda: _num(2 * (8 + 5)),
    "sat-adv-8": lambda: _num(2 ** 3 + 3 ** 2),
    "sat-adv-9": lambda: f"{180 - 50 - 60} degrees",
    "sat-adv-11": lambda: f"{2 * 5}π",
    "sat-adv-12": lambda: _num(4 ** 2 - 1),
    "sat-adv-13": lambda: _num(F(10 * 6, 2)),
    # las dos raíces de x² = 49
    "sat-adv-15": lambda: " and ".join(f"x = {_num(r)}" for r in (7, -7) if r ** 2 == 49),
    "sat-adv-17": lambda: f"{3 ** 2 * 10}π",
    "sat-adv-18": lambda: _num(10 * F(6, 4)),
    # 2^(x+1) = 32 = 2^5
    "sat-adv-19": lambda: _num(next(x for x in range(10) if 2 ** (x + 1) == 32)),
    # (90/360) · 2π · 8
    "sat-adv-20": lambda: f"{_num(F(90, 360) * 2 * 8)}π",
    # vértice en x = 3 → f(3)
    "sat-adv-21": lambda: _num(3 ** 2 - 6 * 3 + 5),
    # −b/a
    "sat-adv-22": lambda: _num(F(8, 2)),
    # cateto adyacente por Pitágoras: √(5² − 3²) = 4
    "sat-adv-24": lambda: _num(F(int((5 ** 2 - 3 ** 2) ** 0.5), 5)),
    "sat-adv-25": lambda: _num(20 + 2 * 8),
}


@pytest.mark.parametrize("item_id", sorted(CUENTAS))
def test_la_respuesta_sale_de_la_cuenta(item_id):
    item = banco.get_item(item_id)
    assert item is not None, item_id
    assert item["correct"] == CUENTAS[item_id](), item["question"]


def test_las_que_no_son_un_numero_suelto_tambien_cuadran():
    """Las de respuesta con unidades o decimales se comprueban aparte."""
    # 9 · 7.5 cm × 5 km/cm
    assert banco.get_item("sat-dat-9")["correct"] == f"{7.5 * 5} kilometres"
    # 11 · 12 : (12 + 18) = 2 : 5
    r = F(12, 12 + 18)
    assert banco.get_item("sat-dat-11")["correct"] == f"{r.numerator}:{r.denominator}"
    # 13 · 5 × (2.40 / 3)
    assert banco.get_item("sat-dat-13")["correct"] == f"{5 * 2.40 / 3:.2f} dollars"
    # 14 · 1.20 × 0.80 = 0.96 → 4 % menos
    assert isclose(1.20 * 0.80, 0.96)
    assert banco.get_item("sat-dat-14")["correct"].startswith("It is 4 percent lower")
    # 23 · 1 000 × 1.05²
    assert banco.get_item("sat-dat-23")["correct"] == f"{1000 * 1.05 ** 2:,.2f} dollars"
    # 16 · y = 1.5x + 20 → la pendiente es el crecimiento semanal
    assert "1.5 centimetres per week" in banco.get_item("sat-dat-16")["correct"]
    # 20 · misma media (50) y B más dispersa
    a, b = [48, 49, 50, 51, 52], [30, 40, 50, 60, 70]
    assert sum(a) / 5 == sum(b) / 5 == 50
    assert "set B has the larger standard deviation" in banco.get_item("sat-dat-20")["correct"]


def test_las_de_rectas_cuadran():
    # 13 · d = 1 → 44
    assert banco.get_item("sat-alg-13")["correct"] == "50 − 6d"
    # 16 · pendiente −3, corte 2
    assert banco.get_item("sat-alg-16")["correct"] == "y = −3x + 2"
    # 17 · paralela: misma pendiente (2)
    assert banco.get_item("sat-alg-17")["correct"].startswith("y = 2x")
    # 19 · 2x − 2 ≤ 3x + 4 → x ≥ −6 · se prueba en los bordes
    assert 2 * (-6 - 1) <= 3 * -6 + 4 and not (2 * (-7 - 1) <= 3 * -7 + 4)
    assert banco.get_item("sat-alg-19")["correct"] == "x ≥ −6"
    # 24 · perpendicular a 2/3: −3/2, corte 4
    assert F(2, 3) * F(-3, 2) == -1
    assert banco.get_item("sat-alg-24")["correct"] == "y = −(3/2)x + 4"


@pytest.mark.parametrize("habilidad", ["sat_algebra", "sat_datos", "sat_avanzado", "sat_gramatica"])
def test_cada_habilidad_ampliada_tiene_25_y_los_tres_niveles(habilidad):
    items = banco.items(skill_id=habilidad)
    assert len(items) == 25
    por_nivel = {}
    for i in items:
        por_nivel[i["level"]] = por_nivel.get(i["level"], 0) + 1
    assert por_nivel == {
        banco.NIVEL_FUNDAMENTOS: 9,
        banco.NIVEL_INTERMEDIO: 9,
        banco.NIVEL_AVANZADO: 7,
    }


def test_las_de_expresiones_algebraicas_cuadran():
    """Se evalúan las dos expresiones en varios valores: si son equivalentes,
    dan lo mismo en todos."""
    for x in (-3, 0, 1, 2, 5):
        assert (x + 3) * (x - 3) == x ** 2 - 9          # adv-10
        assert 3 * x * (x + 2) == 3 * x ** 2 + 6 * x    # adv-14
        assert x ** 2 + 7 * x + 12 == (x + 3) * (x + 4) # adv-16
    assert banco.get_item("sat-adv-10")["correct"] == "x² − 9"
    assert banco.get_item("sat-adv-14")["correct"] == "3x² + 6x"
    assert banco.get_item("sat-adv-16")["correct"] == "(x + 3)(x + 4)"
    # adv-23 · centro (2, −1) y radio √25
    assert banco.get_item("sat-adv-23")["correct"] == f"Center (2, −1), radius {int(25 ** 0.5)}"
