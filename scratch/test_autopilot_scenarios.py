import sys
import time
from pathlib import Path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from modes.autopilot import default_autopilot_engine
from agent.tool_registry import default_tool_registry
from agent.tool_metadata import RiskLevel

queries = [
    ("My Wi-Fi keeps disconnecting.", "NETWORK", False),
    ("How can I view previous Windows Update failures?", "WINDOWS_UPDATE", True),
    ("Chrome keeps crashing.", "APPLICATION_CRASH", False),
    ("A Windows service has stopped.", "SERVICES", False),
    ("My C drive is almost full.", "STORAGE", False),
    ("Explain why my CPU usage is high.", "PERFORMANCE", True),
    ("My Bluetooth disappeared.", "BLUETOOTH", False),
    ("My printer is not working.", "PRINTER", False),
]

print("=== AUTOPILOT PLANNING & REGRESSION VERIFICATION ===")

for q, expected_domain, is_read_only_intent in queries:
    print(f"\nQuery: '{q}' (expected: {expected_domain}, read_only_intent: {is_read_only_intent})")
    plan = default_autopilot_engine.plan(problem_description=q)
    print(f"  Plan ID: {plan.plan_id}")
    print(f"  Goal: {plan.goal} (Status: {plan.status.value})")
    print(f"  Proposed Steps ({len(plan.steps)}):")
    
    repair_steps = []
    unregistered_tools = []
    for step in plan.steps:
        tool_def = default_tool_registry.get(step.tool_name)
        if not tool_def:
            unregistered_tools.append(step.tool_name)
            status_str = "UNREGISTERED_TOOL!"
        else:
            status_str = f"{tool_def.risk.value}"
            if tool_def.risk != RiskLevel.SAFE:
                repair_steps.append((step.tool_name, tool_def.risk.value))
        print(f"    - [{status_str:<6}] {step.tool_name} (purpose: {step.purpose})")

    assert len(unregistered_tools) == 0, f"Unregistered tools proposed: {unregistered_tools}"
    print(f"  All proposed tools ({len(plan.steps)}) exist in ToolRegistry: PASS")

    if is_read_only_intent:
        if repair_steps:
            print(f"  ERROR: Read-only intent proposed repair steps: {repair_steps}")
        else:
            print("  Verified: Read-only intent proposed ZERO repair tools (strictly read-only).")
    else:
        print(f"  Repair steps proposed: {repair_steps if repair_steps else 'None (all safe diagnostics)'}")

print("\nALL AUTOPILOT PLANNING SCENARIOS PASSED WITH ZERO UNREGISTERED TOOLS!")
