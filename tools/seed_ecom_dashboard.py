"""Load the explicitly fictional legacy dashboard fixture; --direct writes only to your configured database."""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--direct', action='store_true', help='Write the test fixture to an explicitly configured demo database')
    args = parser.parse_args()
    payload = json.loads((ROOT / 'tools/ecom_seed.json').read_text(encoding='utf8'))
    if args.direct:
        from utils.ecom_dashboard_service import save_board_state
        save_board_state(payload)
        print('Synthetic fixture saved to configured demo database.')
    else:
        print('Synthetic fixture ready: tools/ecom_seed.json. No database was accessed.')

if __name__ == '__main__':
    main()
