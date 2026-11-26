"""Tjekker, at pakkens Python-filer kan køre på Python 3.10 (den laveste version, testene kører med).

f-strings med backslash, genbrugte anførselstegn eller kommentarer i udtryksdelen virker først fra
Python 3.12 (PEP 701). På 3.12+ ser testen efter dem med tokenize, så de fanges før udgivelse, også
når man kun har en nyere Python lokalt. På 3.10 og 3.11 springes den over: der fejler filerne selv.

Kør: python -m pytest tests/test_python310.py -q
"""
import io
import sys
import tokenize
from pathlib import Path

import pytest

PK = Path(__file__).resolve().parent.parent
ROD = PK.parent

pytestmark = pytest.mark.skipif(
    sys.version_info < (3, 12), reason="tokenize kender kun f-string-tokens fra Python 3.12"
)


def _citat(tekst):
    s = tekst.lstrip("rRbBfFuU")
    for q in ('"""', "'''", '"', "'"):
        if s.startswith(q):
            return q
    return None


def fund_i(kilde):
    """Linjer i kilden med f-string-syntaks, der kræver Python 3.12+."""
    fund = []
    stak = []
    for t in tokenize.tokenize(io.BytesIO(kilde.encode("utf-8")).readline):
        if t.type == tokenize.FSTRING_START:
            if stak and _citat(t.string) == stak[-1]:
                fund.append((t.start[0], "indre f-string genbruger anførselstegn"))
            stak.append(_citat(t.string))
        elif t.type == tokenize.FSTRING_END:
            stak.pop()
        elif stak and t.type != tokenize.FSTRING_MIDDLE:
            if "\\" in t.string:
                fund.append((t.start[0], f"backslash i udtryk: {t.string}"))
            if t.type == tokenize.STRING and _citat(t.string) == stak[-1]:
                fund.append((t.start[0], f"streng genbruger anførselstegn: {t.string}"))
            if t.type == tokenize.COMMENT:
                fund.append((t.start[0], "kommentar i udtryk"))
    return fund


def test_tjekket_finder_kendte_fejl():
    assert fund_i('x = f"{a.replace(\'/\', \'\\\\/\')}"\n')
    assert fund_i("x = f\"{'a' + \"b\"}\"\n")
    assert not fund_i('y = "<\\\\/"\nx = f"{y} og {a!r:>4}"\n')


def test_alle_python_filer_kan_koere_paa_310():
    filer = sorted(p for p in ROD.rglob("*.py") if ".git" not in p.parts)
    assert len(filer) > 10
    fejl = [f"{f.relative_to(ROD)}:{n}: {hvad}" for f in filer for n, hvad in fund_i(f.read_text(encoding="utf-8"))]
    assert not fejl, "Kræver Python 3.12+:\n" + "\n".join(fejl)
