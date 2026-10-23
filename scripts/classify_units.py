#!/usr/bin/env python
"""
Rule-based classifier: a map unit's NAME (+ description) -> hclass / hclass2 /
texture / cover, for sources whose unit symbols are map-specific (Alaska DGGS and
USGS quadrangle maps, later the legacy GSC A-series/Open File sheets).

Rules are ordered and the FIRST match wins, so specific terms (glaciolacustrine,
glaciomarine, thaw-lake, rock glacier) come before the generic ones (lacustrine,
marine, glacier). Anything unmatched returns hclass 'Q' with note 'UNCLASSIFIED'
-- never a guess -- and the generated crosswalk CSV is meant to be reviewed.

Texture / cover only when the unit text says so explicitly.
"""
import re

RULES = [  # (regex on lowercased name+desc, hclass, hclass2, note)
    # water only when the NAME is a water term ('Water', 'Lakes', 'RIV' = river): a river named in a unit name dates or
    # places a deposit ('Drift of Sagavanirktok River age', 'Terrace deposits of Tok River alluvial fan') and had turned
    # ~1,000 km2 of Noatak/GeMS drift, outwash and glacial-lake units into water (merge-41 statistics, 2026-10-07)
    (r'^\W*(open\s+)?(water|lakes?|ponds?|rivers?|riv|streams?)(\s+(and|or)\s+(lakes?|ponds?|rivers?|streams?))?'
     r'(\s+bod(y|ies))?\W*$', 'H', '', 'water body'),
    # ice only when the text names ice and NO geology ('BEDROCK, GLACIER-SCOURED' had become 2,125 km2 of Noatak
    # "ice"; merge-42 ice audit, 2026-10-07)
    (r'^(?!.*(deposit|drift|till|moraine|bedrock|\brock\b|scour|outwash|sediment|gravel|sand)).*'
     r'(glacier ice|ice ?field|icecap|ice cap|perennial (snow|ice)|snow ?fields?|\bfirn\b|\bglaciers?\b)', 'I', '', ''),
    (r'rock glacier', 'C', '', 'rock glacier'),
    (r'glacio-?lacustrine|glacial[- ]lake|ice-dammed lake', 'GL', '', ''),
    (r'glacio-?marine|glaciomarine|glacio-?estuarine', 'GM', '', ''),
    (r'glacio-?fluvial|outwash|kame|esker|ice-contact|ice contact|sandur|proglacial (fan|delta|stream)', 'GF', '', ''),
    (r'thaw[- ]lake|thermokarst|\balas\b|drained[- ]lake|drained lake basin', 'K', 'L', ''),
    (r'yedoma|ice complex', 'Y', '', 'source names an ice complex'),
    (r'\btill\b|moraine|morainal|drift|drumlin|ground moraine|glacial deposits?', 'T', '', ''),
    (r'\bloess\b|eolian|aeolian|dune|wind-?blown|sand sheet', 'E', '', ''),
    (r'tidal|intertidal|salt ?marsh|beach|spit|barrier|estuar|lagoon|littoral|marine|coastal', 'M', '', ''),
    (r'delta', 'F', 'M', 'deltaic'),
    (r'alluvi|fluvial|flood[- ]?plain|flood deposits?|stream|terrace|fan deposits?|alluvial fan|channel|levee', 'F', '', ''),
    (r'lacustrine|lake deposits?|lake-bottom', 'L', '', ''),
    (r'peat|organic|bog|fen|muskeg|swamp|marsh', 'O', '', ''),
    (r'colluvi|solifluction|talus|scree|landslide|slump|debris[- ]flow|mass[- ]wasting|avalanche|rockfall|rock-fall|slope deposits?|mudflow|creep', 'C', '', ''),
    (r'residuum|residual|weathered bedrock|regolith|felsenmeer|blockfield|block field|grus|altiplanation', 'W', '', ''),
    (r'lava|volcanic|tephra|ash[- ](fall|flow)|cinder|pyroclastic', 'V', '', ''),
    (r'fill\b|mine tailings|tailings|anthropogenic|artificial|disturbed', 'X', '', ''),
    (r'bedrock|\brock\b|outcrop|sedimentary rocks?|igneous|metamorphic', 'R', '', ''),
]
TEX = [
    (r'\b(boulder|bouldery|blocky|rubble)\b', 'bouldery'),
    (r'\bgravel(ly)?\b(?!.*\bsand)', 'gravel'),
    (r'\bsand(y)?\b(?!.*\b(silt|clay|gravel))', 'sand'),
    (r'\b(silt|clay|mud)\b(?!.*\b(sand|gravel))', 'fines'),
    (r'\bdiamict', 'diamicton'),
    (r'\bpeat\b', 'organic'),
]
COV = [(r'\bveneer\b|thin (cover|mantle)|discontinuous', 'veneer'), (r'\bblanket\b|thick (cover|mantle)', 'blanket')]


def classify(name, desc=''):
    t = f'{name or ""} || {desc or ""}'.lower()
    head = (name or '').lower() or t
    hit = None
    for rx, h, h2, note in RULES:          # the NAME decides first ...
        if re.search(rx, head):
            hit = (h, h2, note, 'name')
            break
    if hit is None:
        for rx, h, h2, note in RULES:      # ... the description only if the name is silent
            if re.search(rx, t):
                hit = (h, h2, note, 'description')
                break
    # ice only where the unit NAME states it (e.g. Giesche 'Qti ice-rich thaw-lake deposits')
    ice = 'yes' if re.search(r'ice[- ]rich|massive ice|ground ice|ice[- ]wedge|yedoma|ice complex', head) else 'unknown'
    if hit is None:
        return dict(hclass='Q', hclass2='', texture='unknown', cover='unknown', ice_rich=ice,
                    xwalk_note='UNCLASSIFIED by rules - review')
    h, h2, note, where = hit
    tex = next((v for rx, v in TEX if re.search(rx, head)), 'unknown')
    cov = next((v for rx, v in COV if re.search(rx, t)), 'unknown')
    return dict(hclass=h, hclass2=h2, texture=tex, cover=cov, ice_rich=ice,
                xwalk_note=f'rule-classified from {where}' + (f'; {note}' if note else ''))


if __name__ == '__main__':
    for n in ['Alluvium', 'Thaw-lake deposits', 'Ice-rich thaw-lake deposits', 'Glaciolacustrine silt and clay',
              'Till of Itkillik II age', 'Beach deposits', 'Delta deposits', 'Rock glacier deposits',
              'Tidal flat deposits', 'Eolian sand', 'Talus', 'Bedrock', 'Qx unit', 'Lakes']:
        print(n, '->', classify(n))
