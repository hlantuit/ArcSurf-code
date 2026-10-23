"""Positional agreement across seams, BEFORE warping: for each boundary crossing on
sheet A, the distance along the edge to the nearest crossing on sheet B with the same
broad-class transition. The median of these, per seam, measures how well the two
independent sheets agree in position at the edge (raster-vs-vector seams are the test of
the raster georeferencing away from its control, which is only the frame).
Null space: agreement at the EDGE only; the interior of a raster sheet is not tested."""
import sys
sys.path.insert(0, '/albedo/work/user/hlantuit/arctic_surficial/scripts')
import surflib as S  # noqa: E402
import numpy as np  # noqa: E402
import shapely  # noqa: E402
import seam  # noqa: E402
import seam_russia as SR  # noqa: E402
from ingest_russia import RASTER_SHEETS  # noqa: E402

sheets = [s for s in SR.PDF_SHEETS if SR.src_path(s)]
frames = {s: SR.frame(s) for s in sheets}
U = {s: seam.band_snap(SR.load(s), frames[s], datum=4284, band=200.0, exact=True)[0] for s in sheets}
for A, B, box in SR.shared_edges(frames):
    edge = SR.edge_line(*box)
    ca, _ = seam.crossings(U[A][shapely.dwithin(U[A].geometry.values, edge, 3000)], edge, 'broad')
    cb, _ = seam.crossings(U[B][shapely.dwithin(U[B].geometry.values, edge, 3000)], edge, 'broad')
    if ca.empty or cb.empty:
        continue
    d = []
    for _, r in ca.iterrows():
        m = cb[((cb.left == r.left) & (cb.right == r.right))]
        if len(m):
            d.append(np.abs(m.pos - r.pos).min())
    d = np.array(d)
    kind = '+'.join('R' if s in RASTER_SHEETS else 'V' for s in (A, B))
    if len(d):
        print(f'{kind} {A:24s}| {B:24s} crossings {len(ca):3d}/{len(cb):3d}  matched-transition offsets: '
              f'median {np.median(d):6.0f} m  p75 {np.percentile(d, 75):6.0f} m  within 250 m: {(d < 250).mean():.0%}')
