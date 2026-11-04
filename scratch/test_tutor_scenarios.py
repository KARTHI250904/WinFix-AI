import sys
import time
from pathlib import Path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from modes.personal_tutor import default_personal_tutor
from agent.tool_registry import default_tool_registry

queries = [
    ("My Wi-Fi keeps disconnecting.", "network"),
    ("My Bluetooth disappeared.", "bluetooth"),
    ("My computer is very slow.", "performance"),
    ("My C drive is almost full.", "storage"),
    ("Windows Update failed.", "windows_update"),
    ("Google Chrome keeps crashing.", "application_crash"),
    ("My Windows service has stopped.", "services"),
    ("My printer is not working.", "printer"),
]

print("=== PERSONAL TUTOR WORKFLOW VERIFICATION ===")

for q, expected_domain in queries:
    session = default_personal_tutor.create_troubleshooting_flow(user_question=q)
    print(f"\nQuery: '{q}'")
    print(f"  Detected Domain: {session.domain} (Expected: {expected_domain})")
    print(f"  Problem Statement: {session.problem_statement}")
    print(f"  Steps ({len(session.steps)}):")
    for s in session.steps:
        tool_def = default_tool_registry.get(s.tool_name)
        risk = tool_def.risk.value if tool_def else "UNKNOWN"
        print(f"    - [{risk:<6}] {s.tool_name} (requires_confirmation={s.requires_confirmation})")
    
    assert session.domain == expected_domain, f"Domain mismatch for '{q}': got {session.domain}, expected {expected_domain}"
    print(f"  Domain match: PASS")

print("\nALL 8 PERSONAL TUTOR SCENARIOS PASSED DOMAIN CLASSIFICATION & PLAN CREATION!")
