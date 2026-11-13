"""One-time operator import; not part of the service package."""
from contextlib import closing
from datetime import datetime, timedelta
import json
from pathlib import Path
import sqlite3
from uuid import UUID

from hypermesh_contract_authority import Fulfill, Ledger, PROTOCOL, SIGNER


def import_contracts(source: Path, dsn: str) -> int:
    # Read the entire consistent source snapshot before touching the destination.
    with closing(sqlite3.connect(source.resolve().as_uri() + '?mode=ro', uri=True)) as old:
        old.execute('BEGIN')
        if old.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
            raise ValueError('Source integrity check failed')
        rows = old.execute('SELECT tenant,lease,id,request,record FROM contracts').fetchall()
    for tenant, lease, identity, request, record in rows:
        body = Fulfill.model_validate_json(request)
        value = json.loads(record)
        start, end = (datetime.fromisoformat(value[key]) for key in ('signed_at', 'until'))
        if (str(UUID(tenant)) != value['tenant_id'] or str(body.lease_id) != lease
                or value['lease_id'] != lease or str(UUID(identity)) != value['id']
                or value['protocol'] != PROTOCOL or value['signed_by'] != SIGNER
                or value['rail'] != 'self-use' or value['status'] != 'signed'
                or start.tzinfo is None or end.tzinfo is None or end-start != timedelta(hours=1)
                or value['meters'] != sorted(body.meters)
                or value['parties'] != [{'role': 'renter', 'subject': str(body.renter_subject)},
                                       {'role': 'host', 'subject': str(body.host_subject)}]):
            raise ValueError('Invalid source contract')
    ledger = Ledger(dsn)
    with ledger.connect() as db:
        # Excludes concurrent writes during the all-or-nothing import.
        db.execute('LOCK TABLE contracts IN EXCLUSIVE MODE')
        for row in rows:
            db.execute('INSERT INTO contracts VALUES (%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING', row)
            stored = db.execute('SELECT tenant,lease,id,request,record FROM contracts WHERE tenant=%s AND lease=%s', row[:2]).fetchone()
            if stored != row:
                raise ValueError('Destination conflicts with source contract')
    return len(rows)


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--connection-file', type=Path, required=True)
    args = parser.parse_args()
    import_contracts(args.source, args.connection_file.read_text().strip())
    print('Import committed')
