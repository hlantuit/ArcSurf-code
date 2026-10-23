"""Solve the 1:2.5M map's projection from the graticule (q2500_fit.py output).
Control points = labelled meridians x parallels (84N ... 48N every 4 deg, outermost radius
= 48N as labelled). For each candidate equidistant conic (Krassowsky, lon_0 = 100E) over a
grid of standard parallels, fit a similarity page->projection and keep the lowest RMS;
report the implied scale. Longitudes: the east group of labels runs past 180 (168, 174
right of the 180 meridian are 192E, 186E)."""
import json
import sys

sys.path.insert(0, '/albedo/work/user/hlantuit/arctic_surficial/scripts')
import surflib as S  # noqa: E402,F401  (PROJ fix)
import numpy as np  # noqa: E402
import pyproj  # noqa: E402

G = json.load(open('/albedo/work/user/hlantuit/arctic_surficial/work/q2500/graticule_fit_input.json'))
apex = np.array(G['apex'])
mer = sorted(G['meridians'], key=lambda m: m['angle'])
a180 = next(m['angle'] for m in mer if m['lon'] == 180)
for m in mer:                                   # unwrap: left of 180 (smaller angle) is past the date line
    if m['angle'] < a180 and m['lon'] < 180:
        m['lon'] = 360 - m['lon']
rho = sorted(np.array([p['rho'] for p in []] or [1117.6, 1624.1, 2130.4, 2636.6, 3142.6, 3648.3, 4153.7, 4658.9, 5163.7, 5668.2]))
lats = [84 - 4 * i for i in range(len(rho))]
page, ll = [], []
for m in mer:
    t = np.radians(m['angle'])
    for r, la in zip(rho, lats):
        page.append(apex + r * np.array([np.cos(t), np.sin(t)]))
        ll.append((m['lon'], la))
page, ll = np.array(page), np.array(ll)
page[:, 1] *= -1                                # page y runs down


def fit(lat1, lat2, lon0=100.0):
    crs = pyproj.CRS.from_proj4(f'+proj=eqdc +lat_1={lat1} +lat_2={lat2} +lat_0=60 +lon_0={lon0} +ellps=krass +units=m +no_defs')
    E, N = pyproj.Transformer.from_crs(4284, crs, always_xy=True).transform(ll[:, 0], ll[:, 1])
    # similarity page -> (E, N): complex least squares  z = s*e^{i phi} w + c
    w = page[:, 0] + 1j * page[:, 1]; z = E + 1j * N
    A = np.c_[w, np.ones_like(w)]
    coef, *_ = np.linalg.lstsq(A, z, rcond=None)
    res = np.abs(A @ coef - z)
    return float(np.sqrt((res ** 2).mean())), float(np.abs(coef[0])), float(np.degrees(np.angle(coef[0]))), res


best = None
for l1 in np.arange(30, 75, 1.0):
    for l2 in np.arange(l1 + 1, 86, 1.0):
        r, s, ph, _ = fit(l1, l2)
        if best is None or r < best[0]:
            best = (r, l1, l2, s, ph)
r, l1, l2, s, ph = best
for l1_ in np.arange(l1 - 1, l1 + 1.01, 0.1):          # refine
    for l2_ in np.arange(l2 - 1, l2 + 1.01, 0.1):
        if l2_ <= l1_:
            continue
        rr, ss, pp, _ = fit(round(l1_, 2), round(l2_, 2))
        if rr < best[0]:
            best = (rr, round(l1_, 2), round(l2_, 2), ss, pp)
r, l1, l2, s, ph = best
_, _, _, res = fit(l1, l2)
print(f'best eqdc lat_1={l1} lat_2={l2} lon_0=100: rms {r:.0f} m, max {res.max():.0f} m over {len(res)} points; '
      f'{s:.1f} m/pt -> 1:{s / 0.000352778:,.0f}; rotation {ph:.3f} deg')
for cand in ((47, 62), (52, 72), (54, 74), (45, 70), (48, 72)):
    rr, ss, _, _ = fit(*cand)
    print(f'   check lat_1/lat_2 {cand}: rms {rr:.0f} m, scale 1:{ss / 0.000352778:,.0f}')
json.dump(dict(proj=f'+proj=eqdc +lat_1={l1} +lat_2={l2} +lat_0=60 +lon_0=100 +ellps=krass +units=m +no_defs',
               rms_m=r, max_m=float(res.max()), m_per_pt=s, rotation_deg=ph, n_points=len(res)),
          open('/albedo/work/user/hlantuit/arctic_surficial/work/q2500/projection.json', 'w'), indent=1)
