"""Quick check: Queripel tolerance results."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.storage.database import Database
from src.filtering.hard_gates import check_all_gates
from src.config_loader import load_config

config = load_config()
db = Database()
conn = db.conn

rows = conn.execute(
    "SELECT p.* FROM properties p WHERE p.address LIKE '%Queripel%' AND p.status = 'active'"
).fetchall()

for row in rows:
    prop = dict(row)
    enr_row = conn.execute(
        "SELECT * FROM enrichment_data WHERE property_id = ?", (prop["id"],)
    ).fetchone()
    enrichment = dict(enr_row) if enr_row else {}
    passed, gates = check_all_gates(prop, enrichment, config)
    sc_gate = [g for g in gates if g.gate_name == "service_charge"][0]
    print(
        f"#{prop['id']} SC=£{prop['service_charge_pa']} → "
        f"passed={sc_gate.passed}, verify={sc_gate.needs_verification}, "
        f"reason={sc_gate.reason}"
    )
    print(f"  Overall passed={passed}")
