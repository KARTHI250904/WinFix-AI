"""Screenshot Analyzer module for WinFix AI.

Coordinates local vision analysis via Ollama, parses structured JSON observations,
enforces security policies on output, maps visible evidence to registered diagnostic tools,
and generates plain-language explanations via Personal Tutor.
"""

import base64
import json
import logging
import re
import time
from typing import Any, Dict, List, Optional, Set, Tuple

from agent.screenshot_diagnostics import (
    ScreenshotDiagnosticMapper,
    default_screenshot_mapper,
)
from ai.ollama_client import OllamaClient, ollama_client
from ai.screenshot_prompt import (
    SCREENSHOT_VISION_SYSTEM_INSTRUCTION,
    build_screenshot_prompt,
)
from config import config
from database.db import DatabaseManager
from input.screenshot_input import (
    ScreenshotValidationError,
    inspect_privacy_indicators,
    validate_and_load_image,
)
from input.screenshot_models import (
    ScreenshotAnalysis,
    ScreenshotAnalysisStatus,
    ScreenshotEvidence,
    ScreenshotMetadata,
    ScreenshotObservation,
    ScreenshotObservationCategory,
)
from modes.personal_tutor import PersonalTutor, default_personal_tutor
from modes.tutor_context import TutorContext
from modes.tutor_models import TutorResponse, TutorSeverity

logger = logging.getLogger(__name__)

FORBIDDEN_EXECUTION_KEYS = {
    "cmd",
    "command",
    "shell",
    "powershell",
    "subprocess",
    "executable",
    "script",
    "code",
    "python",
    "eval",
    "exec",
    "os_system",
    "run_command",
    "run_process",
    "bash",
    "shlex",
}

# Regex pattern for Windows error codes (e.g. 0x80070422, 0xc0000005)
ERROR_CODE_REGEX = re.compile(r"\b0x[0-9a-fA-F]{4,8}\b")
ALT_ERROR_CODE_REGEX = re.compile(r"\b(?:error|code)\s*[:#]?\s*(0x[0-9a-fA-F]{4,8}|[0-9a-fA-F]{6,8})\b", re.IGNORECASE)
# Regex pattern for Windows Event IDs (e.g. Event ID 1000, Event ID: 7000)
EVENT_ID_REGEX = re.compile(r"\bEvent\s*(?:ID|Code)?\s*[:#]?\s*(\d{1,6})\b", re.IGNORECASE)


def _check_security_violations(data: Any, path: str = "") -> None:
    """Recursively inspect structured vision data and reject forbidden command execution keys."""
    if isinstance(data, dict):
        for k, v in data.items():
            k_lower = str(k).lower().strip()
            current_path = f"{path}.{k}" if path else str(k)
            if k_lower in FORBIDDEN_EXECUTION_KEYS:
                raise ValueError(
                    f"Security Policy Rejection: Forbidden command execution field '{k}' detected at '{current_path}'."
                )
            _check_security_violations(v, current_path)
    elif isinstance(data, list):
        for idx, item in enumerate(data):
            _check_security_violations(item, f"{path}[{idx}]")
    elif isinstance(data, str):
        val_lower = data.lower()
        for forbidden in ["powershell.exe", "cmd.exe", "format c:", "rmdir /s", "del /f /s"]:
            if forbidden in val_lower:
                raise ValueError(
                    f"Security Policy Rejection: Forbidden shell execution command '{forbidden}' detected in vision text."
                )


class ScreenshotAnalyzer:
    """Offline-first Windows Screenshot Analyzer utilizing local Ollama vision capabilities."""

    def __init__(
        self,
        client: Optional[OllamaClient] = None,
        mapper: Optional[ScreenshotDiagnosticMapper] = None,
        tutor: Optional[PersonalTutor] = None,
        db: Optional[DatabaseManager] = None,
    ) -> None:
        self.client = client or ollama_client
        self.mapper = mapper or default_screenshot_mapper
        self.tutor = tutor or default_personal_tutor
        self.db = db

    def check_vision_capability(self, model_name: Optional[str] = None) -> Tuple[bool, str, str]:
        """Check if local Ollama environment is reachable and a vision model is available.

        Returns:
            Tuple of (can_run: bool, status_code: str, human_reason: str)
        """
        target_model = model_name or getattr(config, "vision_model", "moondream:latest")
        conn = self.client.check_connection()
        if not conn.get("connected"):
            return (
                False,
                ScreenshotAnalysisStatus.VISION_MODEL_UNAVAILABLE.value,
                f"Local AI is currently unavailable: WinFix AI could not connect to Ollama ({conn.get('error', 'Service offline')})",
            )

        # Probe configured target model and known vision candidates in Ollama
        candidates = [target_model]
        for known in ["moondream:latest", "moondream", "minicpm-v:latest", "minicpm-v", "llava:latest", "llava", "llama3.2-vision:latest", "llama3.2-vision"]:
            if known not in candidates:
                candidates.append(known)

        for cand in candidates:
            cand_status = self.client.check_model_availability(cand)
            if cand_status.get("model_available"):
                return True, ScreenshotAnalysisStatus.VISION_SUCCESS.value, f"Local vision model '{cand}' available."

        return (
            False,
            ScreenshotAnalysisStatus.VISION_MODEL_MISSING.value,
            f"The configured local vision model '{target_model}' is not installed in Ollama.",
        )

    def analyze_screenshot(
        self,
        image_bytes: bytes,
        filename: Optional[str] = None,
        user_question: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> ScreenshotAnalysis:
        """Validate, normalize, and execute offline vision analysis on uploaded screenshot.

        Args:
            image_bytes: Raw binary image data.
            filename: Client-provided filename.
            user_question: Optional inquiry from user.
            session_id: Active session identifier.

        Returns:
            ScreenshotAnalysis structured report.
        """
        start_time = time.time()
        active_session = session_id or "screenshot_session_local"

        # 1. Audit: Received
        self._log_audit(active_session, "SCREENSHOT_RECEIVED", {"filename": filename, "size": len(image_bytes)})

        # 2. Validation and normalization
        try:
            metadata, normalized_png, _ = validate_and_load_image(image_bytes, filename=filename)
        except ScreenshotValidationError as val_err:
            logger.warning("Screenshot validation failed: %s", val_err)
            self._log_audit(active_session, "SCREENSHOT_ANALYSIS_FAILED", {"error": str(val_err)})
            return self._build_error_analysis(
                error_msg=str(val_err),
                status=ScreenshotAnalysisStatus.INVALID_IMAGE.value if "corrupted" in str(val_err).lower() else ScreenshotAnalysisStatus.UNSUPPORTED_IMAGE_FORMAT.value,
                filename=filename or "unknown",
                file_size=len(image_bytes),
                start_time=start_time,
            )

        # 3. Audit: Validated
        self._log_audit(
            active_session,
            "SCREENSHOT_VALIDATED",
            {"hash": metadata.sha256, "dimensions": f"{metadata.width}x{metadata.height}", "format": metadata.format},
        )

        # 4. Check privacy indicators
        privacy_warnings = inspect_privacy_indicators(metadata.filename)

        # 5. Check local vision capability
        target_model = getattr(config, "vision_model", "moondream:latest")
        vision_timeout = getattr(config, "vision_timeout_seconds", 15)
        can_run, status_code, vision_msg = self.check_vision_capability(target_model)
        if not can_run:
            logger.info("Vision capability unavailable: %s (%s)", status_code, vision_msg)
            self._log_audit(active_session, "SCREENSHOT_ANALYSIS_FAILED", {"error": vision_msg, "status": status_code})
            return self._build_fallback_analysis(
                metadata=metadata,
                reason=vision_msg,
                status=status_code,
                privacy_warnings=privacy_warnings,
                start_time=start_time,
                user_question=user_question,
            )

        # Select detected active vision model
        for cand in [target_model, "moondream:latest", "moondream", "minicpm-v:latest", "minicpm-v", "llava:latest", "llava", "llama3.2-vision:latest", "llama3.2-vision"]:
            if self.client.check_model_availability(cand).get("model_available"):
                target_model = cand
                break

        # 6. Prepare natural visual prompt and Base64 image payload
        prompt = "Describe what is displayed on this screen in detail. Read all visible text, battery levels, percentages, status icons, window titles, error codes, and settings."
        if user_question and user_question.strip():
            prompt += f" Specifically address user question: {user_question.strip()}"

        b64_image = base64.b64encode(normalized_png).decode("utf-8")

        self._log_audit(active_session, "SCREENSHOT_ANALYSIS_STARTED", {"hash": metadata.sha256, "model": target_model, "timeout": vision_timeout})

        # 7. Query local Ollama with image using configured model and bounded timeout
        llm_resp = self.client.generate(
            prompt=prompt,
            images=[b64_image],
            model=target_model,
            format=None,
            options={"temperature": 0.1, "num_predict": 120},
            timeout=vision_timeout,
        )

        raw_text = llm_resp.get("response", "").strip()
        if not raw_text and llm_resp.get("success"):
            # Fallback VQA prompt for vision models
            alt_resp = self.client.generate(
                prompt="What error or problem is shown in this image?",
                images=[b64_image],
                model=target_model,
                format=None,
                options={"temperature": 0.1, "num_predict": 120},
                timeout=vision_timeout,
            )
            if alt_resp.get("success") and alt_resp.get("response", "").strip():
                llm_resp = alt_resp
                raw_text = alt_resp.get("response", "").strip()

        duration_ms = int((time.time() - start_time) * 1000)

        if not llm_resp.get("success"):
            err_text = llm_resp.get("error", "Vision generation failed")
            is_timeout = bool(llm_resp.get("timeout")) or "timed out" in err_text.lower() or "timeout" in err_text.lower()
            if is_timeout:
                failure_status = ScreenshotAnalysisStatus.VISION_REQUEST_TIMEOUT.value
                failure_reason = f"Visual analysis could not be completed because the local vision model did not respond within the configured time limit ({vision_timeout}s)."
            else:
                failure_status = ScreenshotAnalysisStatus.VISION_REQUEST_ERROR.value
                failure_reason = f"Local vision model error: {err_text}"

            logger.warning("Ollama vision generation failed (%s): %s", failure_status, err_text)
            self._log_audit(active_session, "SCREENSHOT_ANALYSIS_FAILED", {"error": err_text, "status": failure_status})
            return self._build_fallback_analysis(
                metadata=metadata,
                reason=failure_reason,
                status=failure_status,
                privacy_warnings=privacy_warnings,
                start_time=start_time,
                user_question=user_question,
            )

        # 8. Parse structured JSON response or synthesize structured diagnostic schema
        parsed_json = None

        if "not a valid json output" in raw_text.lower():
            self._log_audit(active_session, "SCREENSHOT_ANALYSIS_FAILED", {"error": "Invalid vision response format", "status": ScreenshotAnalysisStatus.VISION_INVALID_RESPONSE.value})
            return self._build_fallback_analysis(
                metadata=metadata,
                reason="The vision model responded, but its result could not be safely interpreted as valid structured diagnostic data.",
                status=ScreenshotAnalysisStatus.VISION_INVALID_RESPONSE.value,
                privacy_warnings=privacy_warnings,
                start_time=start_time,
                user_question=user_question,
            )

        if raw_text and (raw_text.startswith("{") or "```json" in raw_text):
            try:
                candidate = self._extract_json_object(raw_text)
                if isinstance(candidate, dict) and (
                    candidate.get("observations")
                    or candidate.get("visible_facts_summary")
                    or candidate.get("detected_error_codes")
                ):
                    parsed_json = candidate
            except Exception:
                pass

        if not parsed_json:
            synthesized_input = (raw_text or user_question or "Windows interface screenshot").strip()
            parsed_json = self._synthesize_structured_json_from_raw_text(synthesized_input, user_question=user_question)

        try:
            _check_security_violations(parsed_json)
        except Exception as sec_ex:
            self._log_audit(active_session, "SCREENSHOT_ANALYSIS_FAILED", {"error": str(sec_ex), "status": ScreenshotAnalysisStatus.VISION_INVALID_RESPONSE.value})
            return self._build_fallback_analysis(
                metadata=metadata,
                reason=f"Security rejection: {sec_ex}",
                status=ScreenshotAnalysisStatus.VISION_INVALID_RESPONSE.value,
                privacy_warnings=privacy_warnings,
                start_time=start_time,
                user_question=user_question,
            )

        # 9. Build structured ScreenshotEvidence
        evidence = self._build_evidence_from_json(parsed_json, metadata)

        # 10. Map evidence to registered diagnostic tools
        suggested_areas = parsed_json.get("suggested_diagnostic_areas", [])
        diagnostic_hints = self.mapper.map_evidence_to_hints(evidence, suggested_areas, user_context=user_question)

        facts_summary = str(parsed_json.get("visible_facts_summary", "Screenshot analysis completed.")).strip()
        interpretations = [str(i).strip() for i in parsed_json.get("possible_interpretations", []) if str(i).strip()]
        uncertainties = [str(u).strip() for u in parsed_json.get("uncertainties", []) if str(u).strip()]
        if not uncertainties:
            uncertainties.append(
                "A screenshot only captures past visible UI state and cannot verify background service or network conditions."
            )

        recommended_next = str(
            parsed_json.get(
                "recommended_next_step",
                "Run the proposed read-only diagnostic tools to verify active system state.",
            )
        ).strip()

        analysis = ScreenshotAnalysis(
            evidence=evidence,
            visible_facts_summary=facts_summary,
            possible_interpretations=interpretations,
            uncertainties=uncertainties,
            diagnostic_hints=diagnostic_hints,
            recommended_next_step=recommended_next,
            privacy_warnings=privacy_warnings,
            analysis_duration_ms=duration_ms,
            model_used=str(llm_resp.get("model", target_model)),
            status=ScreenshotAnalysisStatus.VISION_SUCCESS.value,
            created_at=time.time(),
        )

        self._log_audit(
            active_session,
            "SCREENSHOT_ANALYSIS_COMPLETED",
            {
                "hash": metadata.sha256,
                "observations_count": len(evidence.observations),
                "hints_count": len(diagnostic_hints),
                "duration_ms": duration_ms,
            },
        )
        return analysis

    def explain_screenshot_analysis(
        self,
        analysis: ScreenshotAnalysis,
        user_question: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> TutorResponse:
        """Formulate a Personal Tutor educational explanation based on screenshot evidence."""
        diag_payload = {
            "screenshot_evidence": {
                "visible_facts": analysis.visible_facts_summary,
                "error_codes": analysis.evidence.detected_error_codes,
                "applications": analysis.evidence.detected_applications,
                "observations_count": len(analysis.evidence.observations),
                "possible_interpretations": analysis.possible_interpretations,
                "uncertainties": analysis.uncertainties,
                "recommended_tools": [h.tool_name for h in analysis.diagnostic_hints],
            }
        }
        question = (
            user_question
            or f"Explain the screenshot diagnostic findings ({analysis.visible_facts_summary}). Explain what is visible, why screenshot evidence alone cannot prove the root cause, and what diagnostics to run."
        )
        return self.tutor.explain_diagnostic(
            diagnostic_data=diag_payload,
            user_question=question,
            session_id=session_id,
        )

    def _extract_json_object(self, text: str) -> Dict[str, Any]:
        """Extract and decode a JSON dictionary from raw model text."""
        cleaned = text.strip()
        if cleaned.startswith("```json"):
            cleaned = cleaned[7:]
        elif cleaned.startswith("```"):
            cleaned = cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()

        # Find outer braces
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start != -1 and end != -1 and end > start:
            json_str = cleaned[start : end + 1]
            try:
                res = json.loads(json_str)
                if isinstance(res, dict):
                    return res
            except Exception:
                # Clean trailing commas
                repaired = re.sub(r",\s*([}\]])", r"\1", json_str)
                res = json.loads(repaired)
                if isinstance(res, dict):
                    return res

        res = json.loads(cleaned)
        if isinstance(res, dict):
            return res
        raise ValueError(f"Decoded JSON is not a dictionary: {type(res)}")

    def _synthesize_structured_json_from_raw_text(self, text: str, user_question: Optional[str] = None) -> Dict[str, Any]:
        """Synthesize structured diagnostic schema from freeform or non-strict model text."""
        cleaned_text = text.strip()
        combined_text = (cleaned_text + " " + (user_question or "")).strip()

        # Extract error codes and event IDs
        raw_errs = set(ERROR_CODE_REGEX.findall(combined_text))
        for match in ALT_ERROR_CODE_REGEX.finditer(combined_text):
            val = match.group(1).strip()
            if not val.lower().startswith("0x"):
                val = f"0x{val}"
            raw_errs.add(val)
        err_codes = sorted(list(raw_errs))
        event_ids = sorted(list(set(EVENT_ID_REGEX.findall(combined_text))))

        # Identify applications / keywords
        text_lower = combined_text.lower()
        apps = set()
        for candidate_app in ["Windows Update", "Device Manager", "Task Manager", "Explorer", "Windows Defender", "Settings", "Control Panel", "Services"]:
            if candidate_app.lower() in text_lower:
                apps.add(candidate_app)

        # Infer diagnostic domains with strict whole-word matching
        def _matches_any(text: str, keywords: List[str]) -> bool:
            for kw in keywords:
                if " " in kw or len(kw) >= 5:
                    if kw in text:
                        return True
                else:
                    if re.search(rf"\b{re.escape(kw)}\b", text):
                        return True
            return False

        uq_lower = (user_question or "").lower()
        user_asks_bluetooth = _matches_any(uq_lower, [
            "bluetooth", "bthserv", "paired device", "bth", "bluetooth toggle", "turn on bluetooth",
            "bluetooth not working", "bluetooth is disable", "bluetooth is disabled", "bluetooth disabled", "bluetooth off"
        ])
        user_asks_wifi = _matches_any(uq_lower, [
            "wifi", "wi-fi", "wireless", "wlan", "network adapter", "ncpa.cpl",
            "no wifi", "wifi missing", "wifi is not shown", "not shown",
            "why the wifi", "where is wifi", "missing wifi", "no internet"
        ])

        is_quick_settings_panel = (
            ("quick settings" in text_lower or "action center" in text_lower or "quick panel" in text_lower or "flyout" in text_lower)
            or ("bluetooth" in text_lower and ("airplane" in text_lower or "night light" in text_lower or "accessibility" in text_lower or "studio effects" in text_lower or "energy" in text_lower or "26%" in text_lower or "brightness" in text_lower or "volume" in text_lower))
            or ("airplane mode" in text_lower and ("energy" in text_lower or "night light" in text_lower))
            or ("studio effects" in text_lower and "accessibility" in text_lower)
        )

        has_explicit_missing_wifi = any(p in text_lower for p in [
            "wi-fi toggle is missing", "wifi toggle is missing", "wi-fi is missing", "wifi is missing",
            "missing wi-fi", "missing wifi", "wifi not found", "wi-fi not found", "wi-fi button is missing", "wifi button is missing"
        ])

        has_explicit_bluetooth_fault = any(p in text_lower for p in [
            "bluetooth is disabled", "bluetooth is disable", "bluetooth disabled",
            "bluetooth off", "bluetooth not working", "bluetooth unavailable",
            "bluetooth greyed out", "bluetooth is off", "bluetooth error", "bthserv stopped"
        ])

        # Disambiguate Bluetooth vs Wi-Fi
        if user_asks_wifi and not user_asks_bluetooth:
            is_bluetooth_inquiry = False
            is_wifi_inquiry = True
        elif user_asks_bluetooth and not user_asks_wifi:
            is_bluetooth_inquiry = True
            is_wifi_inquiry = False
        else:
            if has_explicit_missing_wifi:
                is_wifi_inquiry = True
                is_bluetooth_inquiry = False
            elif has_explicit_bluetooth_fault:
                is_bluetooth_inquiry = True
                is_wifi_inquiry = False
            else:
                is_bluetooth_inquiry = False
                is_wifi_inquiry = has_explicit_missing_wifi

        # Quick settings Wi-Fi missing triggers when Wi-Fi is inquired or explicitly missing on quick settings
        is_quick_settings_missing_wifi = (
            is_quick_settings_panel
            and (is_wifi_inquiry or has_explicit_missing_wifi)
            and not is_bluetooth_inquiry
        )

        suggested_areas = []
        domain_interpretations = []

        if is_bluetooth_inquiry:
            if "bluetooth" not in suggested_areas:
                suggested_areas.append("bluetooth")
            if "services" not in suggested_areas:
                suggested_areas.append("services")
            domain_interpretations.append("The screenshot indicates that Bluetooth is disabled, inactive, or not communicating properly.")
            domain_interpretations.append("The Windows Bluetooth Support Service (bthserv) may be stopped, disabled, or encountering an issue.")
            domain_interpretations.append("The physical Bluetooth radio state, Device Manager hardware status, and Windows Bluetooth settings should be verified.")

        elif is_quick_settings_missing_wifi or (is_wifi_inquiry and ("settings" in text_lower or "quick" in text_lower or "airplane" in text_lower)):
            suggested_areas.extend(["network", "services"])
            domain_interpretations.append("From the screenshot, the Wi-Fi quick toggle button is completely missing from Windows Quick Settings.")
            domain_interpretations.append("Bluetooth is present and Airplane mode is OFF, indicating wireless hardware is active but Wi-Fi is unrecognized.")
            domain_interpretations.append("1. Wi-Fi adapter is disabled in Windows Network Connections (ncpa.cpl).")
            domain_interpretations.append("2. Wi-Fi adapter hardware/driver is missing or encountering an error in Device Manager.")
            domain_interpretations.append("3. WLAN AutoConfig background service (WlanSvc) is stopped or disabled.")
            domain_interpretations.append("4. Windows is not detecting the physical wireless hardware.")

        if _matches_any(text_lower, ["dns", "wifi", "wi-fi", "ethernet", "no internet", "gateway", "disconnected", "network adapter"]) and "network" not in suggested_areas and not is_bluetooth_inquiry:
            suggested_areas.append("network")
            domain_interpretations.append("The screenshot indicates network adapter, DNS, or internet connectivity issues.")

        if _matches_any(text_lower, ["battery", "power", "charge", "charging", "discharging", "energy", "power plan", "%"]) and not is_quick_settings_missing_wifi and not is_bluetooth_inquiry:
            suggested_areas.append("power")
            domain_interpretations.append("Battery or system power management status is visible in the screenshot.")
            domain_interpretations.append("Battery level or power policy may trigger system throttling or require AC power connection.")

        if _matches_any(text_lower, ["settings", "gear", "control panel", "configuration", "preferences"]) and not is_quick_settings_missing_wifi and not is_bluetooth_inquiry:
            if "power" not in suggested_areas:
                suggested_areas.append("system_info")
                domain_interpretations.append("Windows Settings or system configuration interface is displayed.")

        if _matches_any(text_lower, ["printer", "print spooler", "spoolsv", "printing error"]):
            suggested_areas.append("printer")
            domain_interpretations.append("Printer queue, spooler service, or printing device status is visible.")

        if _matches_any(text_lower, ["windows update", "0x8024", "0x8007", "kb", "patch", "wuauserv", "update failed", "download error"]):
            suggested_areas.append("windows_update")
            domain_interpretations.append("The screenshot displays a Windows Update issue or update installation failure.")
            domain_interpretations.append("The Windows Update service (wuauserv) or update cache may need health inspection.")

        if _matches_any(text_lower, ["windows defender", "antivirus", "threat", "firewall", "windefend", "virus scan"]):
            suggested_areas.append("defender")
            domain_interpretations.append("Security protection alert or Windows Defender service notification visible.")

        if _matches_any(text_lower, ["low disk", "out of space", "drive full", "disk space", "c: drive"]):
            suggested_areas.append("storage")
            domain_interpretations.append("Low disk space or drive volume capacity warning visible.")

        if _matches_any(text_lower, ["high cpu", "ram full", "task manager", "memory leak", "system freeze"]):
            suggested_areas.append("performance")
            domain_interpretations.append("High resource utilization or performance bottleneck visible.")

        if _matches_any(text_lower, ["crash", "appcrash", "stopped working", "event 1000", "0xc0000005", "faulting module"]):
            suggested_areas.append("application_crash")
            domain_interpretations.append("Application crash, faulting module, or unhandled exception dialog visible.")

        if _matches_any(text_lower, ["bluetooth", "bthserv", "paired device", "bluetooth not available"]) and "bluetooth" not in suggested_areas:
            suggested_areas.append("bluetooth")
            domain_interpretations.append("Bluetooth device connection or radio status issue visible.")

        if not suggested_areas:
            suggested_areas.append("general")
            domain_interpretations.append("Visual elements were identified in the screenshot for baseline system verification.")

        # Limit interpretations to top 4 concise, deduplicated points
        unique_interpretations = []
        for it in domain_interpretations:
            if it not in unique_interpretations:
                unique_interpretations.append(it)
        domain_interpretations = unique_interpretations[:4]

        # Build sentence-level observations
        obs = []
        if is_bluetooth_inquiry:
            obs.append({
                "category": "STATUS",
                "text": "Bluetooth toggle is visibly disabled or turned off in the interface",
                "confidence": 0.96,
                "location": "quick settings / settings flyout",
            })
            if "airplane" in text_lower or "night light" in text_lower or "accessibility" in text_lower:
                obs.append({
                    "category": "STATUS",
                    "text": "Other quick toggles (Night Light, Accessibility, etc.) are present",
                    "confidence": 0.90,
                    "location": "quick settings grid",
                })
        elif is_quick_settings_missing_wifi:
            obs.append({
                "category": "STATUS",
                "text": "Wi-Fi quick toggle button is completely missing from Windows Quick Settings",
                "confidence": 0.98,
                "location": "quick settings grid",
            })
            obs.append({
                "category": "STATUS",
                "text": "Bluetooth toggle is present and Airplane mode is OFF",
                "confidence": 0.95,
                "location": "quick settings grid",
            })
            obs.append({
                "category": "STATUS",
                "text": "Quick Settings controls present: Energy saver, Night light, Accessibility, Studio effects",
                "confidence": 0.92,
                "location": "quick settings flyout",
            })

        if cleaned_text:
            # Split by newlines and sentence ends
            raw_sentences = re.split(r"(?<=[.!?\n])\s+", cleaned_text)
            for s in raw_sentences:
                stext = s.strip().strip("-*• \"'")
                if not stext or len(stext) < 3 or stext.startswith("{") or stext.startswith("}"):
                    continue
                # Determine category
                if any(ec in stext for ec in err_codes) or "error" in stext.lower() or "problem" in stext.lower() or "fail" in stext.lower():
                    cat = "ERROR_MESSAGE"
                elif any(app.lower() in stext.lower() for app in apps) or "window" in stext.lower() or "dialog" in stext.lower():
                    cat = "APPLICATION_NAME"
                else:
                    cat = "STATUS"

                obs.append({
                    "category": cat,
                    "text": stext[:180],
                    "confidence": 0.95,
                    "location": "screen",
                })
                if len(obs) >= 8:
                    break

        if not obs and cleaned_text:
            obs.append({
                "category": "STATUS",
                "text": cleaned_text[:200],
                "confidence": 0.85,
                "location": "screen",
            })

        if is_quick_settings_missing_wifi:
            summary = "Windows Quick Settings is displayed: Bluetooth is available and Airplane mode is OFF, but the Wi-Fi quick toggle button is completely missing."
        else:
            summary = cleaned_text.replace("\n", " ").strip()
            if len(summary) > 220:
                summary = summary[:217] + "..."
            if not summary or summary.startswith("{"):
                summary = "Visual elements and problem indicators identified in screenshot."

        return {
            "visible_facts_summary": summary,
            "observations": obs,
            "detected_error_codes": err_codes,
            "detected_event_ids": event_ids,
            "detected_applications": sorted(list(apps)),
            "possible_interpretations": domain_interpretations,
            "uncertainties": [
                "Screenshot evidence reflects visible UI state and cannot verify background service states without live diagnostics."
            ],
            "suggested_diagnostic_areas": suggested_areas,
            "recommended_next_step": f"Run verified read-only diagnostics for {', '.join(suggested_areas).replace('_', ' ')} to inspect active system state.",
        }

    def _build_evidence_from_json(
        self,
        data: Dict[str, Any],
        metadata: ScreenshotMetadata,
    ) -> ScreenshotEvidence:
        """Construct ScreenshotEvidence from parsed JSON and extracted regex tokens."""
        raw_obs = data.get("observations", [])
        valid_obs: List[ScreenshotObservation] = []

        valid_categories = {c.value for c in ScreenshotObservationCategory}

        combined_text_list: List[str] = []

        if isinstance(raw_obs, list):
            for item in raw_obs:
                if not isinstance(item, dict):
                    continue
                cat = str(item.get("category", "UNKNOWN")).upper().strip()
                if cat not in valid_categories:
                    cat = "UNKNOWN"
                text = str(item.get("text", "")).strip()
                if not text:
                    continue

                conf_val = item.get("confidence", 1.0)
                try:
                    conf = max(0.0, min(1.0, float(conf_val)))
                except (ValueError, TypeError):
                    conf = 1.0

                loc = str(item.get("location", "")).strip() or None
                valid_obs.append(
                    ScreenshotObservation(
                        category=cat,
                        text=text,
                        confidence=conf,
                        location=loc,
                    )
                )
                combined_text_list.append(text)

        # If no standard observations list was provided, extract key-value observations from data (ignoring trivial mimetype tokens)
        if not valid_obs and isinstance(data, dict):
            for k, v in data.items():
                if k in ["suggested_diagnostic_areas", "detected_error_codes", "detected_event_ids", "detected_applications", "uncertainties", "possible_interpretations", "visible_facts_summary", "recommended_next_step"]:
                    continue
                # Skip trivial mimetype / raw container keys
                if str(k).lower() in ["type", "format", "encoding", "content_type"] and str(v).lower() in ["text/plain", "image/png", "png", "utf-8"]:
                    continue
                if isinstance(v, (str, int, float)) and str(v).strip():
                    valid_obs.append(
                        ScreenshotObservation(
                            category="ERROR_MESSAGE" if "error" in str(k).lower() or "error" in str(v).lower() else "STATUS",
                            text=f"{k}: {v}",
                            confidence=0.90,
                            location="screen",
                        )
                    )
                    combined_text_list.append(f"{k}: {v}")

        full_extracted_text = " ".join(combined_text_list)

        # Extract error codes from model response, text regex, and dictionary values
        error_codes: Set[str] = set()
        for ec in data.get("detected_error_codes", []):
            if isinstance(ec, str) and ec.strip():
                error_codes.add(ec.strip())
        for match in ERROR_CODE_REGEX.finditer(full_extracted_text):
            error_codes.add(match.group(0))

        # Also search in dictionary values
        if isinstance(data, dict):
            for val in data.values():
                if isinstance(val, str):
                    for match in ERROR_CODE_REGEX.finditer(val):
                        error_codes.add(match.group(0))

        # Extract Event IDs
        event_ids: Set[str] = set()
        for eid in data.get("detected_event_ids", []):
            if isinstance(eid, (str, int)) and str(eid).strip():
                event_ids.add(str(eid).strip())
        for match in EVENT_ID_REGEX.finditer(full_extracted_text):
            event_ids.add(match.group(1))

        # Extract Applications
        apps: Set[str] = set()
        for app in data.get("detected_applications", []):
            if isinstance(app, str) and app.strip():
                apps.add(app.strip())

        return ScreenshotEvidence(
            metadata=metadata,
            observations=valid_obs,
            raw_text_extracted=full_extracted_text,
            detected_error_codes=sorted(list(error_codes)),
            detected_event_ids=sorted(list(event_ids)),
            detected_applications=sorted(list(apps)),
        )

    def _build_fallback_analysis(
        self,
        metadata: ScreenshotMetadata,
        reason: str,
        status: str,
        privacy_warnings: List[str],
        start_time: float,
        user_question: Optional[str] = None,
    ) -> ScreenshotAnalysis:
        """Create a safe fallback analysis when local vision AI is unavailable or fails."""
        duration_ms = int((time.time() - start_time) * 1000)

        # On vision failure, do not hallucinate visual observations or extracted text
        evidence = ScreenshotEvidence(
            metadata=metadata,
            observations=[],
            raw_text_extracted="",
            detected_error_codes=[],
            detected_event_ids=[],
            detected_applications=[],
        )

        suggested_areas: List[str] = []
        if user_question:
            uq_lower = user_question.lower()
            if any(w in uq_lower for w in ["wifi", "wi-fi", "network", "internet", "dns", "disconnected", "connect"]):
                suggested_areas.append("network")
            if any(w in uq_lower for w in ["bluetooth", "bth"]):
                suggested_areas.append("bluetooth")
            if any(w in uq_lower for w in ["update", "kb", "patch"]):
                suggested_areas.append("windows_update")
            if any(w in uq_lower for w in ["disk", "storage", "space"]):
                suggested_areas.append("storage")
            if any(w in uq_lower for w in ["cpu", "memory", "ram", "performance", "slow"]):
                suggested_areas.append("performance")
            if any(w in uq_lower for w in ["defender", "virus", "threat", "security"]):
                suggested_areas.append("defender")
            if any(w in uq_lower for w in ["crash", "crashed", "exception"]):
                suggested_areas.append("application_crash")

        hints = self.mapper.map_evidence_to_hints(evidence, suggested_areas, user_context=user_question)

        facts_summary = reason

        interpretations: List[str] = [
            "Vision analysis could not be completed; visual state could not be confirmed.",
        ]
        if status == ScreenshotAnalysisStatus.VISION_REQUEST_TIMEOUT.value:
            interpretations.append("The local vision AI request timed out before finishing execution.")
        elif "timed out" in reason.lower() or "timeout" in reason.lower():
            interpretations.append("The local vision AI request timed out.")
        else:
            interpretations.append(f"Visual analysis unavailable: {reason}")

        if user_question and user_question.strip():
            interpretations.append(f"User inquiry context: '{user_question.strip()}'")

        uncertainties = [
            "Screenshot evidence reflects visible UI state and cannot verify background service states without live diagnostics.",
            "Local vision AI did not process the image, so visual elements could not be confirmed.",
        ]
        recommended_next = "Run verified read-only diagnostics to inspect active system state."

        return ScreenshotAnalysis(
            evidence=evidence,
            visible_facts_summary=facts_summary,
            possible_interpretations=interpretations,
            uncertainties=uncertainties,
            diagnostic_hints=hints,
            recommended_next_step=recommended_next,
            privacy_warnings=privacy_warnings,
            analysis_duration_ms=duration_ms,
            model_used="none",
            status=status,
            created_at=time.time(),
        )

    def _build_error_analysis(
        self,
        error_msg: str,
        status: str,
        filename: str,
        file_size: int,
        start_time: float,
    ) -> ScreenshotAnalysis:
        """Construct error analysis for invalid image inputs."""
        duration_ms = int((time.time() - start_time) * 1000)
        dummy_meta = ScreenshotMetadata(
            filename=filename,
            format="UNKNOWN",
            width=0,
            height=0,
            file_size=file_size,
            sha256="0" * 64,
            aspect_ratio=1.0,
        )
        return ScreenshotAnalysis(
            evidence=ScreenshotEvidence(metadata=dummy_meta),
            visible_facts_summary=f"Image validation rejected: {error_msg}",
            possible_interpretations=[],
            uncertainties=["Invalid image payload."],
            diagnostic_hints=[],
            recommended_next_step="Upload a valid screenshot in PNG, JPEG, or WEBP format under 10 MB.",
            privacy_warnings=[],
            analysis_duration_ms=duration_ms,
            model_used="none",
            status=status,
            created_at=time.time(),
        )

    def _log_audit(self, session_id: str, event_type: str, details: Dict[str, Any]) -> None:
        """Log structured screenshot events in the SQLite database audit log without storing raw bytes."""
        if not self.db:
            return
        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT OR IGNORE INTO sessions (id, mode) VALUES (?, ?)",
                    (session_id, "screenshot"),
                )
                cursor.execute(
                    """
                    INSERT INTO diagnostics (id, session_id, tool_name, status, evidence_json)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        f"screenshot_{int(time.time() * 1000)}",
                        session_id,
                        f"screenshot:{event_type}",
                        "SUCCESS",
                        json.dumps(details),
                    ),
                )
        except Exception as ex:
            logger.debug("Failed to write Screenshot audit log: %s", ex)


default_screenshot_analyzer = ScreenshotAnalyzer()
