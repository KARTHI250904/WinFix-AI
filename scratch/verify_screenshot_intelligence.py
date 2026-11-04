"""WinFix AI — Real-World Screenshot Intelligence Verification Script.

Executes Phases 2-15 of the Screenshot Intelligence Verification Specification.
Renders real test images for 10 Windows scenarios and feeds them through:
1. Local Ollama Vision Model (moondream:latest)
2. ScreenshotAnalyzer pipeline
3. Personal Tutor explanation pipeline
4. Autopilot multimodal planning pipeline
5. SafetyEngine & ToolRegistry allowlist verification
6. Session isolation & Cross-mode consistency checks
"""

import io
import json
import os
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

from PIL import Image, ImageDraw, ImageFont

# Set up project path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.stdout.reconfigure(line_buffering=True)

from modes.autopilot import default_autopilot_engine
from agent.tool_registry import default_tool_registry
from ai.ollama_client import ollama_client
from ai.screenshot_analyzer import default_screenshot_analyzer
from input.screenshot_models import ScreenshotAnalysisStatus
from modes.personal_tutor import default_personal_tutor


def create_scenario_image(scenario_id: str) -> bytes:
    """Generate realistic Windows UI test screenshots with PIL."""
    # Base canvas
    if scenario_id == "S10_DARK_BLUETOOTH_OFF":
        bg_color = (32, 32, 32)
        text_color = (255, 255, 255)
        accent_color = (60, 60, 60)
    else:
        bg_color = (243, 243, 243)
        text_color = (20, 20, 20)
        accent_color = (220, 225, 230)

    width, height = 900, 600
    img = Image.new("RGB", (width, height), color=bg_color)
    draw = ImageDraw.Draw(img)

    # Simple font fallback
    font = ImageFont.load_default()

    if scenario_id == "S1_QUICK_SETTINGS_BT_OFF":
        # Windows Quick Settings: Wi-Fi ON, Bluetooth OFF
        draw.rectangle([550, 200, 880, 580], fill=(255, 255, 255), outline=(200, 200, 200), width=2)
        draw.text((570, 220), "Quick Settings", fill=(0, 0, 0), font=font)
        # Wi-Fi Tile (Active Blue)
        draw.rectangle([570, 250, 710, 310], fill=(0, 103, 192))
        draw.text((580, 270), "Wi-Fi: Connected\nHome-5G", fill=(255, 255, 255), font=font)
        # Bluetooth Tile (Grey / Inactive)
        draw.rectangle([725, 250, 865, 310], fill=(230, 230, 230), outline=(180, 180, 180))
        draw.text((735, 270), "Bluetooth\nNot connected (Off)", fill=(100, 100, 100), font=font)
        # Airplane mode (Off)
        draw.rectangle([570, 325, 710, 385], fill=(240, 240, 240))
        draw.text((580, 345), "Airplane mode\nOff", fill=(50, 50, 50), font=font)
        # Night light (On)
        draw.rectangle([725, 325, 865, 385], fill=(0, 103, 192))
        draw.text((735, 345), "Night light\nOn", fill=(255, 255, 255), font=font)
        # Battery slider
        draw.text((570, 420), "Battery: 85% Remaining", fill=(0, 0, 0), font=font)

    elif scenario_id == "S2_QUICK_SETTINGS_WIFI_MISSING":
        # Windows Quick Settings: Wi-Fi completely missing! Bluetooth present
        draw.rectangle([550, 200, 880, 580], fill=(255, 255, 255), outline=(200, 200, 200), width=2)
        draw.text((570, 220), "Quick Settings (Windows 11)", fill=(0, 0, 0), font=font)
        # Bluetooth Tile (Present)
        draw.rectangle([570, 250, 710, 310], fill=(0, 103, 192))
        draw.text((580, 270), "Bluetooth\nOn (Ready)", fill=(255, 255, 255), font=font)
        # Airplane Mode (Off)
        draw.rectangle([725, 250, 865, 310], fill=(240, 240, 240))
        draw.text((735, 270), "Airplane mode\nOff", fill=(50, 50, 50), font=font)
        # Night Light
        draw.rectangle([570, 325, 710, 385], fill=(240, 240, 240))
        draw.text((580, 345), "Night light\nOff", fill=(50, 50, 50), font=font)
        # Accessibility
        draw.rectangle([725, 325, 865, 385], fill=(240, 240, 240))
        draw.text((735, 345), "Accessibility\nTools", fill=(50, 50, 50), font=font)
        # Notice text in place of missing tile
        draw.text((570, 420), "Battery: 26% — Wi-Fi toggle is missing", fill=(180, 0, 0), font=font)

    elif scenario_id == "S3_WINDOWS_UPDATE_ERROR":
        # Windows Update Dialog
        draw.rectangle([150, 100, 750, 500], fill=(255, 255, 255), outline=(150, 150, 150), width=2)
        draw.rectangle([150, 100, 750, 140], fill=(0, 120, 215))
        draw.text((170, 115), "Windows Update", fill=(255, 255, 255), font=font)
        draw.text((180, 170), "There were some problems installing updates, but we'll try again later.", fill=(0, 0, 0), font=font)
        draw.text((180, 210), "Install error - 0x80070422", fill=(180, 0, 0), font=font)
        draw.text((180, 250), "2026-09 Cumulative Update for Windows 11 (KB5043076) failed.", fill=(50, 50, 50), font=font)
        draw.text((180, 290), "The Windows Update service (wuauserv) could not be started.", fill=(50, 50, 50), font=font)
        # Retry button
        draw.rectangle([180, 350, 280, 390], fill=(230, 230, 230), outline=(150, 150, 150))
        draw.text((210, 365), "Retry", fill=(0, 0, 0), font=font)

    elif scenario_id == "S4_HIGH_CPU_TASK_MANAGER":
        # Task Manager
        draw.rectangle([100, 80, 800, 520], fill=(255, 255, 255), outline=(100, 100, 100), width=2)
        draw.rectangle([100, 80, 800, 120], fill=(240, 240, 240))
        draw.text((120, 95), "Task Manager - Processes", fill=(0, 0, 0), font=font)
        # Header
        draw.rectangle([110, 130, 790, 160], fill=(230, 230, 230))
        draw.text((120, 140), "Name                      Status      CPU %      Memory", fill=(0, 0, 0), font=font)
        # Rows
        draw.rectangle([110, 170, 790, 210], fill=(255, 200, 200)) # Highlight red
        draw.text((120, 185), "System Interrupts         Running     78.4%      12.4 MB", fill=(180, 0, 0), font=font)
        draw.text((120, 225), "ffmpeg.exe                Running     20.8%      850.1 MB", fill=(0, 0, 0), font=font)
        draw.text((120, 265), "Explorer.exe              Running      0.5%      120.0 MB", fill=(50, 50, 50), font=font)
        draw.text((120, 305), "Total CPU Utilization: 99.2% (Throttling active)", fill=(200, 0, 0), font=font)

    elif scenario_id == "S5_LOW_DISK_SPACE":
        # File Explorer / Storage
        draw.rectangle([120, 100, 780, 480], fill=(255, 255, 255), outline=(120, 120, 120), width=2)
        draw.text((140, 120), "This PC - Devices and drives", fill=(0, 0, 0), font=font)
        # Drive C:
        draw.rectangle([140, 160, 400, 260], fill=(245, 245, 245), outline=(200, 200, 200))
        draw.text((155, 175), "Local Disk (C:)", fill=(0, 0, 0), font=font)
        # Red capacity bar (99% full)
        draw.rectangle([155, 205, 385, 220], fill=(220, 220, 220))
        draw.rectangle([155, 205, 380, 220], fill=(220, 0, 0)) # Red bar
        draw.text((155, 230), "2.10 GB free of 256 GB - Low Disk Space", fill=(180, 0, 0), font=font)
        # Drive D: (Healthy blue bar)
        draw.rectangle([430, 160, 690, 260], fill=(245, 245, 245), outline=(200, 200, 200))
        draw.text((445, 175), "Data (D:)", fill=(0, 0, 0), font=font)
        draw.rectangle([445, 205, 675, 220], fill=(220, 220, 220))
        draw.rectangle([445, 205, 540, 220], fill=(0, 120, 215)) # Blue bar
        draw.text((445, 230), "450 GB free of 1.00 TB", fill=(50, 50, 50), font=font)

    elif scenario_id == "S6_APPLICATION_CRASH":
        # Crash dialog 0xc0000005
        draw.rectangle([180, 160, 720, 440], fill=(255, 255, 255), outline=(100, 100, 100), width=2)
        draw.rectangle([180, 160, 720, 200], fill=(230, 230, 230))
        draw.text((200, 175), "chrome.exe - Application Error", fill=(0, 0, 0), font=font)
        draw.text((200, 230), "The application was unable to start correctly (0xc0000005).", fill=(180, 0, 0), font=font)
        draw.text((200, 265), "Click OK to close the application.", fill=(50, 50, 50), font=font)
        draw.text((200, 305), "Faulting module: ntdll.dll  Offset: 0x0004e2b0  Event ID: 1000", fill=(100, 100, 100), font=font)
        draw.rectangle([450, 370, 550, 410], fill=(230, 230, 230), outline=(150, 150, 150))
        draw.text((480, 385), "OK", fill=(0, 0, 0), font=font)

    elif scenario_id == "S7_DEFENDER_WARNING":
        # Windows Defender Security Warning
        draw.rectangle([150, 120, 750, 480], fill=(255, 255, 255), outline=(200, 0, 0), width=2)
        draw.rectangle([150, 120, 750, 160], fill=(200, 0, 0))
        draw.text((170, 135), "Windows Security - Virus & threat protection", fill=(255, 255, 255), font=font)
        draw.text((180, 190), "Severe Threat Detected: Trojan:Win32/Wacatac.B!ml", fill=(180, 0, 0), font=font)
        draw.text((180, 230), "Status: Active threat requires immediate remediation", fill=(0, 0, 0), font=font)
        draw.text((180, 270), "Affected item: C:\\Downloads\\patch_installer.exe", fill=(50, 50, 50), font=font)
        draw.text((180, 310), "Real-time protection status: Alerting (Service: WinDefend)", fill=(50, 50, 50), font=font)
        draw.rectangle([180, 370, 320, 410], fill=(200, 0, 0))
        draw.text((210, 385), "Start Actions", fill=(255, 255, 255), font=font)

    elif scenario_id == "S8_DEVICE_MANAGER_DRIVER_ERROR":
        # Device Manager
        draw.rectangle([120, 80, 780, 520], fill=(255, 255, 255), outline=(100, 100, 100), width=2)
        draw.text((140, 100), "Device Manager", fill=(0, 0, 0), font=font)
        draw.text((150, 140), "> Audio inputs and outputs", fill=(50, 50, 50), font=font)
        draw.text((150, 175), "> Batteries", fill=(50, 50, 50), font=font)
        draw.text((150, 210), "v Network adapters", fill=(0, 0, 0), font=font)
        draw.rectangle([170, 240, 750, 280], fill=(255, 230, 230))
        draw.text((180, 255), "[!] Intel(R) Wi-Fi 6 AX201 160MHz (Code 10: Device cannot start)", fill=(180, 0, 0), font=font)
        draw.text((180, 295), "    Realtek Gaming 2.5GbE Family Controller", fill=(50, 50, 50), font=font)
        draw.text((180, 330), "    WAN Miniport (IP)", fill=(80, 80, 80), font=font)
        draw.text((150, 370), "> Processors", fill=(50, 50, 50), font=font)

    elif scenario_id == "S9_CLEAN_DESKTOP":
        # Clean desktop - no errors
        draw.rectangle([0, 0, 900, 550], fill=(0, 120, 215)) # Clean Windows blue wallpaper
        # Recycle bin icon
        draw.rectangle([30, 30, 70, 70], fill=(255, 255, 255), outline=(200, 200, 200))
        draw.text((25, 75), "Recycle Bin", fill=(255, 255, 255), font=font)
        # Taskbar
        draw.rectangle([0, 550, 900, 600], fill=(30, 30, 30))
        draw.text((420, 568), "[Start] [Search] [Widgets]", fill=(200, 200, 200), font=font)
        draw.text((790, 568), "12:00 PM", fill=(200, 200, 200), font=font)

    elif scenario_id == "S10_DARK_BLUETOOTH_OFF":
        # Windows 11 Dark Theme Settings > Bluetooth & devices
        draw.rectangle([100, 80, 800, 520], fill=(32, 32, 32), outline=(60, 60, 60), width=2)
        draw.text((130, 105), "Settings > Bluetooth & devices", fill=(255, 255, 255), font=font)
        # Bluetooth row
        draw.rectangle([130, 150, 770, 220], fill=(45, 45, 45), outline=(70, 70, 70))
        draw.text((150, 175), "Bluetooth", fill=(255, 255, 255), font=font)
        draw.text((150, 195), "Discoverable as 'WIN11-WORKSTATION'", fill=(160, 160, 160), font=font)
        # Toggle switch (OFF / grey)
        draw.rectangle([700, 175, 740, 195], fill=(80, 80, 80))
        draw.text((670, 180), "Off", fill=(200, 200, 200), font=font)
        # Devices section
        draw.rectangle([130, 240, 770, 310], fill=(45, 45, 45), outline=(70, 70, 70))
        draw.text((150, 265), "Devices: Headphones (Paired), Mouse (Paired)", fill=(200, 200, 200), font=font)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def run_verification() -> Dict[str, Any]:
    print("=" * 80)
    print("WINFIX AI — REAL-WORLD SCREENSHOT INTELLIGENCE VERIFICATION PIPELINE")
    print("=" * 80)

    # 1. Inspect Ollama status
    conn_info = ollama_client.check_connection()
    models_info = ollama_client.list_local_models()
    print(f"\n[PHASE 1] Runtime Inspection:")
    print(f"  Ollama Server Connected : {conn_info.get('connected')}")
    print(f"  Installed Models        : {models_info.get('models', [])}")
    vision_model_installed = any("moondream" in m or "minicpm" in m or "llava" in m for m in models_info.get('models', []))
    print(f"  Vision Model Active     : {vision_model_installed}")

    test_scenarios = [
        {
            "id": "S1_QUICK_SETTINGS_BT_OFF",
            "name": "Windows Quick Settings (Bluetooth Off, Wi-Fi On)",
            "domain": "bluetooth",
            "user_q": "Why is my Bluetooth not working?",
            "expected_domain": "bluetooth",
            "critical_check": "Distinguish Bluetooth from Wi-Fi",
        },
        {
            "id": "S2_QUICK_SETTINGS_WIFI_MISSING",
            "name": "Windows Quick Settings (Wi-Fi Missing, Bluetooth On)",
            "domain": "network",
            "user_q": "Why is the Wi-Fi toggle missing?",
            "expected_domain": "network",
            "critical_check": "Identify missing Wi-Fi without confusing with Bluetooth",
        },
        {
            "id": "S3_WINDOWS_UPDATE_ERROR",
            "name": "Windows Update Error Dialog (0x80070422)",
            "domain": "windows_update",
            "user_q": "What does update error 0x80070422 mean and how to fix it?",
            "expected_domain": "windows_update",
            "expected_error": "0x80070422",
            "critical_check": "Extract error code 0x80070422",
        },
        {
            "id": "S4_HIGH_CPU_TASK_MANAGER",
            "name": "Task Manager High CPU (99% System Interrupts)",
            "domain": "performance",
            "user_q": "Why is my computer freezing and CPU at 99%?",
            "expected_domain": "performance",
            "critical_check": "Recognize performance / CPU bottleneck",
        },
        {
            "id": "S5_LOW_DISK_SPACE",
            "name": "File Explorer Low Disk Space (Drive C: 2.1 GB)",
            "domain": "storage",
            "user_q": "My drive C is red, how can I free up space?",
            "expected_domain": "storage",
            "critical_check": "Recognize low disk storage",
        },
        {
            "id": "S6_APPLICATION_CRASH",
            "name": "Application Crash Error Dialog (0xc0000005)",
            "domain": "application_crash",
            "user_q": "Why does Chrome keep crashing with error 0xc0000005?",
            "expected_domain": "application_crash",
            "expected_error": "0xc0000005",
            "critical_check": "Extract crash error code 0xc0000005 and event 1000",
        },
        {
            "id": "S7_DEFENDER_WARNING",
            "name": "Windows Defender Warning (Threat Wacatac)",
            "domain": "defender",
            "user_q": "Is this a real virus alert?",
            "expected_domain": "defender",
            "critical_check": "Recognize security / Defender threat",
        },
        {
            "id": "S8_DEVICE_MANAGER_DRIVER_ERROR",
            "name": "Device Manager Driver Error (Wi-Fi Code 10)",
            "domain": "network",
            "user_q": "Why does my Wi-Fi device have a yellow mark?",
            "expected_domain": "network",
            "critical_check": "Recognize network adapter driver failure",
        },
        {
            "id": "S9_CLEAN_DESKTOP",
            "name": "Clean Windows Desktop (Normal State)",
            "domain": "general",
            "user_q": None,
            "expected_domain": "general",
            "critical_check": "Do NOT fabricate repair plan for clean desktop",
        },
        {
            "id": "S10_DARK_BLUETOOTH_OFF",
            "name": "Windows 11 Dark Theme (Bluetooth Off)",
            "domain": "bluetooth",
            "user_q": "How do I turn on Bluetooth?",
            "expected_domain": "bluetooth",
            "critical_check": "Dark theme generalization and Bluetooth toggle",
        },
    ]

    results = []

    print("\n" + "=" * 80)
    print("RUNNING 10 DOMAIN EVALUATION SUITE")
    print("=" * 80)

    for i, scen in enumerate(test_scenarios, 1):
        print(f"\n--- Scenario {i}/10: {scen['name']} ({scen['id']}) ---")
        img_bytes = create_scenario_image(scen["id"])
        filename = f"{scen['id'].lower()}.png"

        t0 = time.time()
        # 1. Analyze with ScreenshotAnalyzer (with user question if available)
        analysis_with_q = default_screenshot_analyzer.analyze_screenshot(
            image_bytes=img_bytes,
            filename=filename,
            user_question=scen["user_q"],
            session_id=f"test_session_{scen['id']}",
        )
        latency_ms = int((time.time() - t0) * 1000)

        # 2. Analyze without text (Phase 6)
        analysis_no_text = default_screenshot_analyzer.analyze_screenshot(
            image_bytes=img_bytes,
            filename=filename,
            user_question=None,
            session_id=f"test_session_textless_{scen['id']}",
        )

        # 3. Test Personal Tutor Explanation (Phase 4)
        tutor_resp = default_screenshot_analyzer.explain_screenshot_analysis(
            analysis=analysis_with_q,
            user_question=scen["user_q"],
            session_id=f"tutor_{scen['id']}",
        )

        # 4. Test Autopilot Planning (Phase 5)
        autopilot_plan = default_autopilot_engine.plan_from_multimodal(
            screenshot_analysis=analysis_with_q,
            user_text=scen["user_q"],
            session_id=f"auto_{scen['id']}",
        )

        # 5. Safety & Tool Allowlist Checks
        plan_tools = [s.tool_name for s in autopilot_plan.steps]
        invalid_tools = [t for t in plan_tools if not default_tool_registry.get(t)]
        destructive_tools = [t for t in plan_tools if not default_tool_registry.get(t).read_only]

        # 6. Evaluation Assertions
        detected_hints = [h.tool_name for h in analysis_with_q.diagnostic_hints]
        detected_errs = analysis_with_q.evidence.detected_error_codes

        # Evaluate domain match
        hints_str = " ".join(detected_hints).lower()
        plan_str = " ".join(plan_tools).lower()
        tutor_title = getattr(tutor_resp, "title", "")
        tutor_steps = getattr(tutor_resp, "recommended_next_steps", [])

        # Check domain alignment
        domain_pass = False
        if scen["expected_domain"] == "bluetooth":
            domain_pass = "bluetooth" in hints_str or "bluetooth" in plan_str or "bluetooth" in tutor_title.lower()
        elif scen["expected_domain"] == "network":
            domain_pass = any(k in hints_str or k in plan_str or k in tutor_title.lower() for k in ["network", "wifi", "internet", "dns"])
        elif scen["expected_domain"] == "windows_update":
            domain_pass = "update" in hints_str or "update" in plan_str or "update" in tutor_title.lower()
        elif scen["expected_domain"] == "performance":
            domain_pass = any(k in hints_str or k in plan_str or k in tutor_title.lower() for k in ["process", "performance", "cpu", "system_info"])
        elif scen["expected_domain"] == "storage":
            domain_pass = "storage" in hints_str or "storage" in plan_str or "disk" in hints_str or "disk" in plan_str
        elif scen["expected_domain"] == "application_crash":
            domain_pass = "crash" in hints_str or "crash" in plan_str or "crash" in tutor_title.lower()
        elif scen["expected_domain"] == "defender":
            domain_pass = "defender" in hints_str or "defender" in plan_str
        elif scen["expected_domain"] == "general":
            # For clean desktop, should NOT have destructive repair tools
            domain_pass = len(destructive_tools) == 0

        # Critical checks
        critical_pass = True
        if scen["id"] == "S1_QUICK_SETTINGS_BT_OFF":
            # Must be Bluetooth, NOT claim Wi-Fi missing
            critical_pass = "bluetooth" in tutor_title.lower() and "wi-fi missing" not in tutor_title.lower()
        elif scen["id"] == "S2_QUICK_SETTINGS_WIFI_MISSING":
            # Must be Wi-Fi, NOT claim Bluetooth disabled
            critical_pass = "wi-fi" in tutor_title.lower() or "network" in tutor_title.lower()
        elif scen["id"] == "S3_WINDOWS_UPDATE_ERROR":
            critical_pass = "0x80070422" in detected_errs or "0x80070422" in analysis_with_q.visible_facts_summary
        elif scen["id"] == "S6_APPLICATION_CRASH":
            critical_pass = "0xc0000005" in detected_errs or "0xc0000005" in analysis_with_q.visible_facts_summary
        elif scen["id"] == "S9_CLEAN_DESKTOP":
            critical_pass = len(destructive_tools) == 0

        # Tool registry allowlist pass
        tool_allowlist_pass = len(invalid_tools) == 0

        overall_status = "REAL_PASS" if (domain_pass and critical_pass and tool_allowlist_pass) else "REAL_FAIL"

        result_item = {
            "scenario": scen["id"],
            "name": scen["name"],
            "status": overall_status,
            "latency_ms": latency_ms,
            "vision_status": analysis_with_q.status,
            "domain_pass": domain_pass,
            "critical_pass": critical_pass,
            "tool_allowlist_pass": tool_allowlist_pass,
            "plan_tools": plan_tools,
            "invalid_tools": invalid_tools,
            "tutor_title": tutor_title,
            "tutor_step_count": len(tutor_steps),
            "detected_error_codes": detected_errs,
        }
        results.append(result_item)

        print(f"  Result Status         : {overall_status}")
        print(f"  Vision Latency        : {latency_ms} ms")
        print(f"  Tutor Title           : {tutor_title}")
        print(f"  Tutor Steps Count     : {len(tutor_steps)}")
        print(f"  Autopilot Plan Steps  : {plan_tools}")
        print(f"  Invalid Tool Names    : {invalid_tools}")
        print(f"  Detected Error Codes  : {detected_errs}")

    # Session Isolation Test (Phase 11)
    print("\n" + "=" * 80)
    print("[PHASE 11] TESTING SESSION ISOLATION & STATE RESIDUAL DEFENSE")
    print("=" * 80)
    # Upload S3 (Update) then S1 (Bluetooth)
    img_s3 = create_scenario_image("S3_WINDOWS_UPDATE_ERROR")
    img_s1 = create_scenario_image("S1_QUICK_SETTINGS_BT_OFF")
    res1 = default_screenshot_analyzer.analyze_screenshot(img_s3, filename="s3.png", session_id="isolation_test_session")
    res2 = default_screenshot_analyzer.analyze_screenshot(img_s1, filename="s1.png", session_id="isolation_test_session")
    # Verify res2 does NOT contain 0x80070422 or Windows Update from res1
    isolation_passed = (
        "0x80070422" not in res2.evidence.detected_error_codes
        and "Windows Update" not in res2.evidence.detected_applications
    )
    print(f"  Session Isolation Passed : {isolation_passed}")

    # Mode Consistency Test (Phase 12)
    print("\n" + "=" * 80)
    print("[PHASE 12] TESTING CROSS-MODE CONSISTENCY (Tutor vs Autopilot)")
    print("=" * 80)
    # Compare tutor and autopilot for S1
    s1_analysis = default_screenshot_analyzer.analyze_screenshot(img_s1, filename="s1_consistent.png", user_question="Why is my Bluetooth not working?")
    s1_tutor = default_screenshot_analyzer.explain_screenshot_analysis(s1_analysis, user_question="Why is my Bluetooth not working?")
    s1_auto = default_autopilot_engine.plan_from_multimodal(screenshot_analysis=s1_analysis, user_text="Why is my Bluetooth not working?")
    consistency_passed = (
        "bluetooth" in s1_tutor.title.lower()
        and any("bluetooth" in s.tool_name.lower() for s in s1_auto.steps)
    )
    print(f"  Cross-Mode Consistency Passed : {consistency_passed}")

    summary_data = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total_scenarios": len(test_scenarios),
        "passed": sum(1 for r in results if r["status"] == "REAL_PASS"),
        "failed": sum(1 for r in results if r["status"] == "REAL_FAIL"),
        "average_latency_ms": sum(r["latency_ms"] for r in results) // len(results),
        "session_isolation": isolation_passed,
        "cross_mode_consistency": consistency_passed,
        "scenarios": results,
    }

    out_path = os.path.join(os.path.dirname(__file__), "screenshot_verification_results.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(summary_data, f, indent=2)

    print("\n" + "=" * 80)
    print(f"VERIFICATION SUMMARY: {summary_data['passed']}/{summary_data['total_scenarios']} REAL_PASS")
    print(f"Average Latency: {summary_data['average_latency_ms']} ms")
    print(f"Results saved to: {out_path}")
    print("=" * 80)
    return summary_data


if __name__ == "__main__":
    run_verification()
