import sys
import time
from pathlib import Path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from agent.tool_registry import default_tool_registry
from agent.tool_metadata import RiskLevel

tools = default_tool_registry.list_tools()
print(f"Total registered tools discovered: {len(tools)}")

safe_tools = [t for t in tools if t.risk == RiskLevel.SAFE]
medium_tools = [t for t in tools if t.risk == RiskLevel.MEDIUM]
high_tools = [t for t in tools if t.risk == RiskLevel.HIGH]

print(f"SAFE tools: {len(safe_tools)}")
print(f"MEDIUM tools: {len(medium_tools)}")
print(f"HIGH tools: {len(high_tools)}")

print("\n--- AUDITING AND EXECUTING ALL 52 SAFE READ-ONLY TOOLS ---")
results = []
for i, tool in enumerate(safe_tools, 1):
    t_start = time.time()
    exc_error = None
    output = None
    try:
        kwargs = {}
        if tool.name == "get_service_status":
            kwargs = {"service_name": "wuauserv"}
        elif tool.name == "get_service_details":
            kwargs = {"service_name": "wuauserv"}
        elif tool.name == "get_process_details":
            import os
            kwargs = {"pid": os.getpid()}
        elif tool.name == "check_dns_resolution":
            kwargs = {"host": "127.0.0.1"}

        output = tool.handler(**kwargs)
        duration_ms = int((time.time() - t_start) * 1000)
        success = output.get("success", True) if isinstance(output, dict) else True
        results.append({
            "num": i,
            "name": tool.name,
            "domain": tool.domain,
            "success": success,
            "duration_ms": duration_ms,
            "error": output.get("error") if isinstance(output, dict) else None,
            "is_dict": isinstance(output, dict),
        })
        print(f"[{i:02d}/52] SAFE: {tool.name:<38} domain={tool.domain:<14} success={str(success):<5} ({duration_ms}ms)")
    except Exception as e:
        duration_ms = int((time.time() - t_start) * 1000)
        results.append({
            "num": i,
            "name": tool.name,
            "domain": tool.domain,
            "success": False,
            "duration_ms": duration_ms,
            "error": str(e),
            "is_dict": False,
        })
        print(f"[{i:02d}/52] SAFE: {tool.name:<38} domain={tool.domain:<14} EXCEPTION: {e} ({duration_ms}ms)")

passed_safe = [r for r in results if r["success"]]
failed_safe = [r for r in results if not r["success"]]
print(f"\nSAFE Tools Execution Summary: {len(passed_safe)} PASSED, {len(failed_safe)} FAILED/ERRORED out of {len(safe_tools)}")

print("\n--- ENUMERATING ALL 10 MEDIUM RISK TOOLS (NO DESTRUCTIVE REPAIRS EXECUTED) ---")
for j, tool in enumerate(medium_tools, 1):
    print(f"[{j:02d}/10] MEDIUM: {tool.name:<36} domain={tool.domain:<14} verification_tool={tool.verification_tool or 'NONE'}")
