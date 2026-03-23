"""Check database state and run gates/scoring if needed."""
import sqlite3

conn = sqlite3.connect("data/property_search.db")

# List tables
tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
print("Tables:", tables)

# Check gate and score counts
print("gate_results:", conn.execute("SELECT COUNT(*) FROM gate_results").fetchone()[0])
print("scores:", conn.execute("SELECT COUNT(*) FROM scores").fetchone()[0])
print("active properties:", conn.execute("SELECT COUNT(*) FROM properties WHERE is_active=1").fetchone()[0])
print("enriched:", conn.execute("SELECT COUNT(*) FROM enrichment_data").fetchone()[0])

conn.close()
