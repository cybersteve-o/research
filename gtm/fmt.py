"""Zahlenformate für die Ausgabe — an einer Stelle, nicht in jedem Modul neu.

Deutsche Schreibweise: Punkt als Tausendertrenner, Komma als Dezimalzeichen.
Das ist keine Kosmetik. Eine Oberfläche, die „42.000.000 €“ neben „42,000,000 €“
zeigt, lässt den Leser zu Recht fragen, welche der beiden Zahlen er glauben soll.
"""

from __future__ import annotations


def eur(value: float) -> str:
    """Ganze Euro: ``42.000.000 €``"""
    return f"{value:,.0f} €".replace(",", ".")


def mio(value: float, digits: int = 2) -> str:
    """Millionen mit Dezimalkomma: ``42,00 Mio €``"""
    english = f"{value / 1_000_000:,.{digits}f}"      # 42,000.00
    integer, _, fraction = english.partition(".")
    integer = integer.replace(",", ".")
    return (f"{integer},{fraction}" if fraction else integer) + " Mio €"


def pct(value: float, digits: int = 0) -> str:
    """Anteil als Prozent mit Dezimalkomma: ``73 %`` / ``7,5 %``"""
    return f"{value * 100:.{digits}f}".replace(".", ",") + " %"
