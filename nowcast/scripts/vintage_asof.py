#!/usr/bin/env python3
"""Read the vintage archive: a series as the archive knew it at the end of a run date.
Usage: python scripts/vintage_asof.py --source bls_cpi --series CUSR0000SA0 [--asof 2026-11-23] [--tail 12] [--dir archive]
Sources: bea:U20404, bea:U20405, bea:U20406, bea:T20804, bls_cpi, bls_ppi, fred."""
import argparse

from lib_common import ARCHIVE
from lib_vintage import state

ap = argparse.ArgumentParser()
ap.add_argument('--dir', default=str(ARCHIVE))
ap.add_argument('--asof', default=None, help='run date YYYY-MM-DD (default: latest)')
ap.add_argument('--source', required=True)
ap.add_argument('--series', required=True)
ap.add_argument('--tail', type=int, default=12)
a = ap.parse_args()
s = state(a.dir, a.asof, a.source, a.series).sort_values('date')
print(s.tail(a.tail).to_string(index=False) if len(s) else 'no such series in the archive')
