import os
import sys
import tempfile
import sqlite3
import shutil
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import config
from database.db import DatabaseManager

db_path = config.config.database_path
print(f"=== DATABASE AUDIT: {db_path} ===")

# 1. PRAGMA integrity_check and foreign_key_check on production database
conn = sqlite3.connect(str(db_path))
cur = conn.cursor()

cur.execute("PRAGMA integrity_check;")
integrity = cur.fetchall()
print(f"PRAGMA integrity_check: {integrity}")

cur.execute("PRAGMA foreign_key_check;")
fk_check = cur.fetchall()
print(f"PRAGMA foreign_key_check violations: {len(fk_check)} {fk_check[:5] if fk_check else ''}")

# 2. Discover all tables, indexes, triggers, and views
cur.execute("SELECT type, name FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' ORDER BY type, name;")
schema_objects = cur.fetchall()
tables = [name for typ, name in schema_objects if typ == 'table']
indexes = [name for typ, name in schema_objects if typ == 'index']
triggers = [name for typ, name in schema_objects if typ == 'trigger']
views = [name for typ, name in schema_objects if typ == 'view']

print(f"\nDiscovered Objects in winfix.db:")
print(f"  Tables  : {len(tables)} -> {tables}")
print(f"  Indexes : {len(indexes)}")
print(f"  Triggers: {len(triggers)}")
print(f"  Views   : {len(views)}")

# Check row counts in key tables
print("\nRow counts in active tables:")
for tbl in tables:
    if not tbl.endswith('_fts') and not tbl.endswith('_fts_data') and not tbl.endswith('_fts_idx') and not tbl.endswith('_fts_docsize') and not tbl.endswith('_fts_config'):
        try:
            cur.execute(f"SELECT COUNT(*) FROM \"{tbl}\";")
            count = cur.fetchone()[0]
            print(f"  {tbl:<35}: {count} rows")
        except Exception as e:
            print(f"  {tbl:<35}: error ({e})")

conn.close()

# 3. Isolated CRUD and Transaction Audit on Temporary Database
print("\n=== ISOLATED DATABASE CRUD & TRANSACTION TESTING ===")
temp_dir = tempfile.mkdtemp(prefix="winfix_db_audit_")
try:
    temp_db_path = Path(temp_dir) / "test_audit.db"
    mgr = DatabaseManager(temp_db_path, schema_path=config.config.schema_path)
    mgr.init_db()
    
    with mgr.get_connection() as t_conn:
        t_cur = t_conn.cursor()
        t_cur.execute("PRAGMA integrity_check;")
        print("Temp DB Initialized. PRAGMA integrity_check:", t_cur.fetchone()[0])
        t_cur.execute("PRAGMA foreign_keys;")
        print("Foreign Keys Enforced:", t_cur.fetchone()[0] == 1)

    # Test Repository Operations
    from database.repositories import (
        SessionRepository,
        ProblemRepository,
        DiagnosticRepository,
        ToolExecutionRepository,
        SolutionRepository,
        FeedbackRepository,
        SettingsRepository,
    )

    # Session CRUD
    sess_repo = SessionRepository(mgr)
    sess_record = sess_repo.create(mode="tutor", status="active")
    sess_id = sess_record["id"]
    print(f"Created Session: {sess_id}")
    active_s = sess_repo.get(sess_id)
    assert active_s is not None, "Failed to read session"
    sess_repo.update(sess_id, status="COMPLETED")
    updated_s = sess_repo.get(sess_id)
    assert updated_s["status"] == "COMPLETED", "Failed to update session status"

    # Problem CRUD
    prob_repo = ProblemRepository(mgr)
    prob_record = prob_repo.create(session_id=sess_id, raw_input="Wi-Fi disconnecting", input_type="text", category="network")
    prob_id = prob_record["id"]
    print(f"Created Problem: {prob_id}")
    prob = prob_repo.get(prob_id)
    assert prob is not None and prob["raw_input"] == "Wi-Fi disconnecting"

    # Diagnostic CRUD
    diag_repo = DiagnosticRepository(mgr)
    diag_record = diag_repo.create(session_id=sess_id, tool_name="get_network_adapters_diagnostics", status="COMPLETED", evidence_json="{\"status\": \"ok\"}")
    diag_id = diag_record["id"]
    print(f"Created Diagnostic: {diag_id}")

    # Tool Execution CRUD
    exec_repo = ToolExecutionRepository(mgr)
    exec_record = exec_repo.create(
        session_id=sess_id,
        tool_name="get_network_adapters_diagnostics",
        risk_level="SAFE",
        requires_admin=False,
        success=True,
        duration_ms=25,
        result_json="{\"status\": \"ok\"}",
    )
    exec_id = exec_record["id"]
    print(f"Created Tool Execution: {exec_id}")

    # Settings CRUD
    set_repo = SettingsRepository(mgr)
    set_repo.set("offline_mode", "strict")
    val = set_repo.get("offline_mode")
    assert val == "strict", f"Settings CRUD mismatch: {val}"
    print(f"Settings CRUD verified: offline_mode={val}")

    # Transaction Rollback Test
    print("Testing Transaction Rollback on error...")
    try:
        with mgr.get_connection() as rb_conn:
            rb_cur = rb_conn.cursor()
            rb_cur.execute("INSERT INTO settings (key, value) VALUES ('test_rb', 'val1');")
            # Force an error
            rb_cur.execute("INSERT INTO settings (key, value) VALUES ('test_rb', 'val2_duplicate_key');")
    except sqlite3.IntegrityError:
        print("  IntegrityError caught as expected.")

    val_rb = set_repo.get("test_rb")
    assert val_rb is None, "Rollback failed! Key was persisted despite transaction failure."
    print("Verified: Transaction rollback works correctly (key was rolled back).")

    print("\nALL DATABASE TESTS PASSED SUCCESSFULLY!")

finally:
    shutil.rmtree(temp_dir, ignore_errors=True)
