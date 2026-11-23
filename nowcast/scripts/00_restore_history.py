#!/usr/bin/env python3
"""Restore the nowcast run history (nowcast_agg, nowcast_cpi, nowcast_leaf: our own daily outputs, i.e. the track record) from the archive into a database that lacks them.
A no-op locally, where the database persists; essential in GitHub Actions, where each run starts from an empty database and the history lives on the `data` branch.
Usage: python scripts/00_restore_history.py [--dir archive]"""
import argparse

from lib_common import ARCHIVE, connect
from lib_vintage import restore_runs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dir', default=str(ARCHIVE))
    a = ap.parse_args()
    loaded = restore_runs(connect(), a.dir)
    print('restored run history:', loaded if loaded else 'nothing to restore (tables exist or no archived runs)')


if __name__ == '__main__':
    main()
