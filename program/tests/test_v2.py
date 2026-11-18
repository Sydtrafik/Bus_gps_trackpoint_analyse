#!/usr/bin/env python3
"""
Tests for analyse_v2.2.py - syntetiske ture bygget i koden (små CSV'er i en midlertidig mappe).

Koer:  python -m pytest tests/test_v2.py       (hvis pytest findes)
       python tests/test_v2.py                 (ren python, ingen afhaengigheder ud over pandas/numpy/pyyaml)
Sæt PYTHONUTF8=1 i miljøet.

Geometri: bussen koerer langs en nord-syd-linje med 10 m (36 km/t) pr. sekund; ping hvert sekund.
Punkterne ligger praecist paa pings (p1=ping 60, p2=ping 120, p3=ping 180 i koerselsretningen),
saa koeretid p1->p2 = 60 s, p1->p3 = 120 s og hastighed ved punkt = 36.0 km/t.
"""
import importlib.util
import math
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import yaml

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent


def _load(name, fname):
    spec = importlib.util.spec_from_file_location(name, ROOT / fname)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


# Kan testes mod en anden version: set ANALYSE_FILE=analyse_v2.1.py (den forrige version)
import os  # noqa: E402
V2 = _load("analyse_v2_x", os.environ.get("ANALYSE_FILE", "analyse_v2.2.py"))

STEP = 10 / (6371000 * math.pi / 180)   # grader pr. 10 m i bredde
LAT0, LON = 55.48, 8.45
P2_LON = LON + 0.00001   # p2 ligger ca. 0,6 m ved siden af pings, så en stop-række paa p2 vinder entydigt
N_PINGS = 251
K1, K2, K3 = 60, 120, 180
BASE = datetime(2025, 8, 4, 8, 0, 0)

DETAILS_COLS = ['Turreference', 'Nr.', 'Stop-nummer', 'Stop-navn', 'Længdegrad (PLANLAGT)',
                'Breddegrad (PLANLAGT)', 'Ankomst-dato (REALTID)', 'Ankomst-tid (REALTID)',
                'Tid (REALTID) (+sekunder)', 'Projektion']


# -- Byggeklodser ------------------------------------------------------------------------

def _fmt(v):
    if v is None:
        return ''
    if isinstance(v, float):
        return f"{v:.9f}".replace('.', ',')
    return str(v)


def _ping(ref, nr, t, lat, proj=False):
    return {'Turreference': ref, 'Nr.': nr, 'Stop-nummer': None, 'Stop-navn': f'\tPegeredskab {nr}',
            'Længdegrad (PLANLAGT)': LON, 'Breddegrad (PLANLAGT)': lat,
            'Ankomst-dato (REALTID)': t.strftime('%Y-%m-%d'), 'Ankomst-tid (REALTID)': t.strftime('%H:%M:%S'),
            'Tid (REALTID) (+sekunder)': None, 'Projektion': 'X' if proj else None}


def _stop(ref, nr, t, lat, name, stop_nr=561044101, lon=LON):
    return {'Turreference': ref, 'Nr.': nr, 'Stop-nummer': stop_nr, 'Stop-navn': f'\t{name}',
            'Længdegrad (PLANLAGT)': lon, 'Breddegrad (PLANLAGT)': lat,
            'Ankomst-dato (REALTID)': t.strftime('%Y-%m-%d'), 'Ankomst-tid (REALTID)': None,
            'Tid (REALTID) (+sekunder)': t.strftime('%H:%M:%S'), 'Projektion': None}


def make_trip(ref, start, direction=1, with_end_stop=True, no_pings=False, stop_row_at_p2=False,
              proj_at_ping=None, tie_stop_at_p2_time=True):
    """Bygger raekkerne for én tur. direction 1 = stigende bredde, 2 = faldende."""
    rows = []
    first_stop, last_stop = ('StopA', 'StopB') if direction == 1 else ('StopB', 'StopA')
    lat_a = LAT0 - 0.0005
    lat_b = LAT0 + (N_PINGS - 1) * STEP + 0.0005
    lat_first, lat_last = (lat_a, lat_b) if direction == 1 else (lat_b, lat_a)
    nr = 1
    rows.append(_stop(ref, nr, start - timedelta(seconds=5), lat_first, first_stop)); nr += 1
    if no_pings:
        rows.append(_stop(ref, nr, start + timedelta(seconds=30), LAT0 + 0.001, 'StopMidt', 561044102)); nr += 1
    else:
        for i in range(N_PINGS):
            k = i if direction == 1 else (N_PINGS - 1 - i)
            rows.append(_ping(ref, nr, start + timedelta(seconds=i), LAT0 + k * STEP, proj=(i == proj_at_ping))); nr += 1
            if stop_row_at_p2 and k == K2:
                # stop-raekke med p2's koordinater og samme tidsstempel (planlagt position, realtidstid)
                rows.append(_stop(ref, nr, start + timedelta(seconds=i), LAT0 + K2 * STEP, 'StopMidt', 561044102, lon=P2_LON)); nr += 1
    if with_end_stop:
        rows.append(_stop(ref, nr, start + timedelta(seconds=N_PINGS + 5), lat_last, last_stop, 561044103))
    return rows


def write_details(path, rows, columns=DETAILS_COLS):
    with open(path, 'w', encoding='utf-8-sig', newline='') as f:
        f.write(';'.join(f'"\t{c}"' for c in columns) + '\n')
        for r in rows:
            vals = []
            for c in columns:
                v = r.get(c)
                s = _fmt(v)
                if c in ('Stop-navn',) or (isinstance(v, str) and v):
                    s = f'"{s}"' if s else ''
                vals.append(s)
            f.write(';'.join(vals) + '\n')


def write_list(path, trips):
    """trips: liste af (ref, retningsflag eller None). Header efterligner HAFAS (dublet-'Turnummer')."""
    with open(path, 'w', encoding='utf-8-sig', newline='') as f:
        f.write(';'.join(f'"\t{c}"' for c in ['Turnummer', 'Køredag', 'Turnummer', 'Retningsflag', 'Hitrate']) + '\n')
        for ref, d in trips:
            f.write(f'"\t{ref}";"\t2025-08-04";"\t{ref}";{"" if d is None else d};\n'.replace('"\t', '"\t'))


def build_dataset(tmp):
    """Standard-datasaet. Returnerer (details_path, list_path)."""
    rows, lst = [], []
    t = BASE

    def nxt():
        nonlocal t
        t = t + timedelta(minutes=20)
        return t

    rows += make_trip(1001, nxt(), 1);                          lst.append((1001, 1))   # normal, retning 1
    rows += make_trip(1002, nxt(), 2);                          lst.append((1002, 2))   # normal, retning 2
    rows += make_trip(1003, nxt(), 1);                          lst.append((1003, None))  # uden retningsflag
    rows += make_trip(1004, nxt(), 1, with_end_stop=False);     lst.append((1004, 1))   # uden slut-stop
    rows += make_trip(1005, nxt(), 1, no_pings=True);           lst.append((1005, 1))   # uden pings
    rows += make_trip(1006, nxt(), 1, stop_row_at_p2=True);     lst.append((1006, 1))   # stoprække matcher p2
    rows += make_trip(1007, nxt(), 1, proj_at_ping=K1);         lst.append((1007, 1))   # projektion ved p1
    d, l = Path(tmp) / 'Details.csv', Path(tmp) / 'List.csv'
    write_details(d, rows)
    write_list(l, lst)
    return d, l


def base_config(tmp, details, lst, points='many', extra=None):
    pts = {'p1': {'name': 'P1', 'lat': LAT0 + K1 * STEP, 'lon': LON},
           'p2': {'name': 'P2', 'lat': LAT0 + K2 * STEP, 'lon': P2_LON},
           'p3': {'name': 'P3', 'lat': LAT0 + K3 * STEP, 'lon': LON}}
    if points == 'many':
        order = {'direction_1': ['p1', 'p2', 'p3'], 'direction_2': ['p3', 'p2', 'p1']}
        dist = {'d1': {'name': 'Lang', 'from': 'p1', 'to': 'p3'}, 'd2': {'name': 'Kort', 'from': 'p1', 'to': 'p2'}}
    elif points == 'two':
        pts = {k: v for k, v in pts.items() if k in ('p1', 'p3')}
        order = {'direction_1': ['p1', 'p3'], 'direction_2': ['p3', 'p1']}
        dist = {'d1': {'name': 'Lang', 'from': 'p1', 'to': 'p3'}}
    elif points == 'one':
        pts = {'p2': pts['p2']}
        order = {'direction_1': ['p2'], 'direction_2': ['p2']}
        dist = None
    cfg = {
        'periods': {'A': {'name': 'Test', 'start': '2025-08-01', 'end': '2025-08-10'}},
        'data': {'Periode_A': {'details_csv': str(details), 'list_csv': str(lst)},
                 'output': str(Path(tmp) / 'out' / 'result.csv')},
        'points': pts, 'point_order': order,
        'stops': {'direction_1': {'start': 'StopA', 'end': 'StopB'},
                  'direction_2': {'start': 'StopB', 'end': 'StopA'}},
    }
    if dist:
        cfg['distances'] = dist
    if extra:
        cfg.update(extra)
    p = Path(tmp) / 'config.yaml'
    p.write_text(yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False), encoding='utf-8')
    return p


import logging


class _Capture(logging.Handler):
    def __init__(self):
        super().__init__()
        self.lines = []

    def emit(self, record):
        self.lines.append(record.getMessage())


_CAP = _Capture()
V2.logger.addHandler(_CAP)


def last_log():
    """Alt hvad v2 loggede i det seneste run_v2-kald (config-fejl opstaar før logfilen kan oprettes)."""
    return "\n".join(_CAP.lines)


def run_v2(cfg_path, *extra_args):
    _CAP.lines.clear()
    rc = V2.main(['--config', str(cfg_path), '--period', 'A', *extra_args])
    out = Path(yaml.safe_load(Path(cfg_path).read_text(encoding='utf-8'))['data']['output']).parent
    return rc, out


def read(out, name):
    return pd.read_csv(out / name, sep=';', encoding='utf-8')


def approx(a, b, tol=0.05):
    return abs(float(a) - float(b)) <= tol


# -- Tests -------------------------------------------------------------------------------

def test_many_points_known_values():
    with tempfile.TemporaryDirectory() as tmp:
        d, l = build_dataset(tmp)
        rc, out = run_v2(base_config(tmp, d, l, 'many'))
        assert rc == 0
        res = read(out, 'result.csv').set_index('Turreference')
        assert sorted(res.index) == [1001, 1002, 1006, 1007], list(res.index)
        for ref in (1001, 1002, 1006, 1007):
            assert res.loc[ref, 'Lang - køretid (sek)'] == 120, (ref, res.loc[ref, 'Lang - køretid (sek)'])
            assert res.loc[ref, 'Kort - køretid (sek)'] == 60, ref
            for p in ('P1', 'P2', 'P3'):
                assert approx(res.loc[ref, f'{p} - hastighed (km/t)'], 36.0), (ref, p)
                assert res.loc[ref, f'{p} - nærmeste afstand (m)'] < 1.0, (ref, p)
        assert list(res['Retning'].sort_index()) == [1, 2, 1, 1]
        assert (res['Log'].fillna('') == '').all()
        # Kolonner: Flag findes, Log uaendret
        cols = list(read(out, 'result.csv').columns)
        assert cols[-2:] == ['Log', 'Flag']


def test_rejection_reasons_and_quality_files():
    with tempfile.TemporaryDirectory() as tmp:
        d, l = build_dataset(tmp)
        rc, out = run_v2(base_config(tmp, d, l, 'many'))
        assert rc == 0
        rej = read(out, 'kasserede_ture.csv').set_index('Turreference')
        assert list(read(out, 'kasserede_ture.csv').columns)[:4] == ['Turreference', 'Køredag', 'Retning', 'Årsag']
        assert rej.loc[1003, 'Årsag'] == 'ingen_retningsflag'
        assert rej.loc[1004, 'Årsag'] == 'stop_ikke_fundet'
        assert rej.loc[1005, 'Årsag'] == 'ingen_gps_trackpoints'
        assert len(rej) == 3
        q = read(out, 'kvalitet.csv')
        assert (out / 'kvalitet.md').exists()

        def n(kat, aarsag='', punkt='', retning=None):
            s = q[(q['Kategori'] == kat) & (q['Årsag'].fillna('') == aarsag) & (q['Punkt'].fillna('') == punkt)]
            if retning is not None:
                s = s[s['Retning'].astype(str) == str(retning)]
            return int(s['Antal'].sum())
        assert n('ture_i_list') == 7
        assert n('ture_i_list', retning='ukendt') == 1
        assert n('ture_i_details') == 7
        assert n('beholdt') == 4
        assert n('kasseret', 'stop_ikke_fundet') == 1
        assert n('kasseret', 'ingen_retningsflag', retning='ukendt') == 1
        # nye flag: stoprække ved p2 (tur 1006), projektion ved p1 (tur 1007)
        assert n('flag', 'stoprække', 'p2') == 1
        assert n('flag', 'projektion', 'p1') == 1
        assert n('flag', 'afstand') == 0
        flags = read(out, 'result.csv').set_index('Turreference')['Flag']
        assert 'stoprække_p2' in str(flags.loc[1006])
        assert 'projektion_p1' in str(flags.loc[1007])
        assert str(flags.loc[1001]) in ('nan', '')


def test_two_points():
    with tempfile.TemporaryDirectory() as tmp:
        d, l = build_dataset(tmp)
        rc, out = run_v2(base_config(tmp, d, l, 'two'))
        assert rc == 0
        res = read(out, 'result.csv').set_index('Turreference')
        assert list(res.columns).count('Lang - køretid (sek)') == 1
        assert 'P2 - hastighed (km/t)' not in res.columns
        for ref in (1001, 1002):
            assert res.loc[ref, 'Lang - køretid (sek)'] == 120
            assert approx(res.loc[ref, 'P1 - hastighed (km/t)'], 36.0)
            assert approx(res.loc[ref, 'P3 - hastighed (km/t)'], 36.0)
        s = read(out, 'opsummering.csv')
        assert set(s['Type']) == {'køretid_sek', 'hastighed_kmh'}


def test_one_point_only_speed():
    with tempfile.TemporaryDirectory() as tmp:
        d, l = build_dataset(tmp)
        rc, out = run_v2(base_config(tmp, d, l, 'one'))
        assert rc == 0
        res = read(out, 'result.csv').set_index('Turreference')
        assert not any('køretid' in c for c in res.columns)
        assert approx(res.loc[1001, 'P2 - hastighed (km/t)'], 36.0)
        s = read(out, 'opsummering.csv')
        assert set(s['Type']) == {'hastighed_kmh'}
        assert approx(s[(s['Retning'] == 1)]['p50'].iloc[0], 36.0)


def test_missing_column_clear_error():
    with tempfile.TemporaryDirectory() as tmp:
        rows = make_trip(1001, BASE, 1)
        d = Path(tmp) / 'Details.csv'
        cols = [c for c in DETAILS_COLS if c not in ('Stop-navn', 'Projektion')]
        write_details(d, rows, columns=cols)
        l = Path(tmp) / 'List.csv'
        write_list(l, [(1001, 1)])
        rc, out = run_v2(base_config(tmp, d, l, 'many'))
        assert rc == 1
        log = last_log()
        assert 'PÅKRÆVEDE kolonner mangler: Stop-navn' in log, log
        assert 'valgfri kolonne mangler: Projektion' in log
        assert not (out / 'result.csv').exists()


def test_missing_date_chain_and_list_column():
    with tempfile.TemporaryDirectory() as tmp:
        rows = make_trip(1001, BASE, 1)
        d = Path(tmp) / 'Details.csv'
        cols = [c for c in DETAILS_COLS if c not in ('Ankomst-dato (REALTID)',)]
        write_details(d, rows, columns=cols)
        l = Path(tmp) / 'List.csv'
        l.write_text('"\tTurnummer";"\tKøredag"\n"\t1001";"\t2025-08-04"\n', encoding='utf-8')
        rc, out = run_v2(base_config(tmp, d, l, 'many'))
        assert rc == 1
        log = last_log()
        assert 'ingen af datokolonnerne findes' in log
        assert 'Retningsflag' in log


def test_defaults_are_logged():
    with tempfile.TemporaryDirectory() as tmp:
        d, l = build_dataset(tmp)
        rc, out = run_v2(base_config(tmp, d, l, 'many', extra={'speed_max_kmh': 80}))
        log = last_log()
        assert 'Standardværdier brugt' in log
        assert 'buffer_rows=50' in log
        assert 'stop_speed_kmh=4.0' in log
        assert 'speed_max_kmh=' not in log   # sat i config -> ikke blandt standarderne


def test_config_errors_in_danish():
    with tempfile.TemporaryDirectory() as tmp:
        d, l = build_dataset(tmp)
        p = base_config(tmp, d, l, 'many')
        cfg = yaml.safe_load(p.read_text(encoding='utf-8'))
        cfg['point_order']['direction_1'] = ['p1', 'p9']
        p.write_text(yaml.safe_dump(cfg, allow_unicode=True), encoding='utf-8')
        rc, out = run_v2(p)
        assert rc == 1
        log = last_log()
        assert "'p9'" in log and 'ikke er defineret' in log
        # ugyldig parameter
        cfg['point_order']['direction_1'] = ['p1', 'p2', 'p3']
        cfg['buffer_rows'] = 'mange'
        p.write_text(yaml.safe_dump(cfg, allow_unicode=True), encoding='utf-8')
        rc, out = run_v2(p)
        assert rc == 1
        assert "'buffer_rows' skal være et tal" in last_log()


def test_max_match_distance_flag_is_configurable():
    with tempfile.TemporaryDirectory() as tmp:
        d, l = build_dataset(tmp)
        # grænse under 0 m -> alle punkter flagges 'afstand' (afstand 0.0 er ikke > 0, så brug -1 via 0.0 og forskudt punkt)
        p = base_config(tmp, d, l, 'many')
        cfg = yaml.safe_load(p.read_text(encoding='utf-8'))
        cfg['points']['p1']['lon'] += 0.0002   # ca. 12,6 m til siden for linjen
        cfg['max_match_distance_m'] = 5
        p.write_text(yaml.safe_dump(cfg, allow_unicode=True), encoding='utf-8')
        rc, out = run_v2(p)
        assert rc == 0
        q = read(out, 'kvalitet.csv')
        s = q[(q['Kategori'] == 'flag') & (q['Årsag'] == 'afstand')]
        assert s['Antal'].sum() >= 1


def test_export_segments():
    with tempfile.TemporaryDirectory() as tmp:
        d, l = build_dataset(tmp)
        rc, out = run_v2(base_config(tmp, d, l, 'many'), '--export-segments')
        assert rc == 0
        seg = read(out, 'segmenter.csv')
        for c in ['Turreference', 'datetime', 'lat', 'lon', 'afstand_til_forrige_m', 'tid_til_forrige_s',
                  'hastighed_kmh', 'status', 'er_stoprække', 'Projektion']:
            assert c in seg.columns, c
        s1 = seg[seg['Turreference'] == 1001]
        mid = s1[s1['status'] == 'OK']
        assert len(mid) > 100
        assert (mid['hastighed_kmh'].sub(36.0).abs() < 0.05).all()
        assert (mid['tid_til_forrige_s'] == 1).all()
        assert set(seg[seg['Turreference'] == 1007]['Projektion'].fillna('')) >= {'X', ''}
        assert seg[seg['Turreference'] == 1006]['er_stoprække'].sum() >= 1
        # kasserede ture er ikke med
        assert not set(seg['Turreference']) & {1003, 1004, 1005}


def test_speed_classification_unit():
    import numpy as np
    P = dict(V2.DEFAULTS)
    P['speed_min_kmh'] = 0.0
    P = {k: (v if not isinstance(v, list) else v) for k, v in P.items()}
    lat = np.array([55.0, 55.0, 55.0 + 1 * STEP, 55.0 + 1.2 * STEP, 55.0 + 30 * STEP, 55.0 + 30 * STEP + 0.0001])
    lon = np.full(6, 8.0)
    t0 = np.datetime64('2025-08-04T10:00:00')
    dt = np.array([t0, t0 + np.timedelta64(1, 's'), t0 + np.timedelta64(2, 's'), t0 + np.timedelta64(3, 's'),
                   t0 + np.timedelta64(4, 's'), t0 + np.timedelta64(3, 's')], dtype='datetime64[ns]')
    is_stop = np.zeros(6, dtype=bool)
    status, dist, tdh, sp, rd, rdt = V2.calculate_speeds(lat, lon, dt, is_stop, P)
    names = V2.status_names(P)
    got = [names[s] for s in status]
    # 0: første; 1: samme position -> Stop; 2: 10 m/s=36 -> OK; 3: 2 m/1s=7.2 km/t -> OK;
    # 4: 29 m... (28.8*... ) = 28*10 m=288 m/1 s = ~1037 km/t -> over 80; 5: tid baglæns -> Tidsfejl
    assert got[0] == 'Ingen tidligere række'
    assert got[1] == 'Stop'
    assert got[2] == 'OK' and abs(sp[2] - 36.0) < 0.01
    assert got[3] == 'OK' and abs(sp[3] - 7.2) < 0.05
    assert got[4].startswith('Hastighed over')
    assert got[5] == 'Tidsfejl'
    # stop-raekker: current -> Stoppested, efter stop-raekke -> SkipEfterstop
    is_stop = np.array([0, 0, 1, 0, 0, 0], dtype=bool)
    status, *_ = V2.calculate_speeds(lat, lon, dt, is_stop, P)
    got = [names[s] for s in status]
    assert got[2] == 'Stoppested' and got[3] == 'SkipEfterstop'


# -- Ren-python-koersel ------------------------------------------------------------------

def _run_all():
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith('test_') and callable(f)]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"PASS {name}")
        except Exception as e:  # noqa
            failed += 1
            import traceback
            print(f"FAIL {name}: {type(e).__name__}: {e}")
            traceback.print_exc()
    print(f"\n{len(tests) - failed} af {len(tests)} tests bestået")
    return 1 if failed else 0


if __name__ == '__main__':
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
    sys.exit(_run_all())
