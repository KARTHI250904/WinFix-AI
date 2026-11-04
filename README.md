# WinFix AI — Version 1.0.0 (Production Release)

**Offline AI-Powered Windows Troubleshooting Assistant & Personal Tutor**

WinFix AI is a production-ready, offline-first Windows troubleshooting application designed to help users diagnose, understand, repair, and verify Windows problems safely and deterministically.

---

## 🚀 Quick Start

### 1. Installation & Environment Setup
```powershell
# Activate your Python virtual environment
.venv\Scripts\Activate.ps1

# Install requirements
pip install -r requirements.txt
```

### 2. Pre-Flight Health Check & Setup
```powershell
python winfix_launcher.py --check-only
```

### 3. Launch WinFix AI
```powershell
python winfix_launcher.py
```
Open your browser to `http://localhost:8501`.

---

## 🌟 5 Operating Modes

1. **🔍 Diagnostic & Repair Assistant**: Interactive, conversational troubleshooting with factual evidence collection and verified, user-confirmed repairs.
2. **🎓 Personal Tutor Mode**: Educational mentor providing plain-language explanations, symptom analysis, and knowledge base guidance without automatic repairs.
3. **🤖 Autopilot Mode**: Multi-step bounded autonomous troubleshooting with cryptographic plan hashing and strict precondition validation.
4. **📷 Screenshot Diagnostics**: Visual inspection of Windows error dialogs and settings with in-memory privacy preservation.
5. **🎤 Voice Diagnostics**: Hands-free spoken troubleshooting with offline local speech-to-text and automated PII sanitization.

---

## 🛡️ Core Security Architecture

```text
User Request (Text / Voice / Screenshot)
                   ↓
Input Validation & Privacy Sanitization
                   ↓
Agent Core / Personal Tutor / Autopilot
                   ↓
Local Knowledge Base (SQLite / FTS5)
                   ↓
Structured Tool Request Formulation
                   ↓
Central Tool Registry (59 Allowlisted Tools)
                   ↓
SafetyEngine (Risk Assessment & Parameter Validation)
                   ↓
Cryptographic Confirmation Token (MEDIUM Risk)
                   ↓
Deterministic Windows Tool Execution (Direct Win32)
                   ↓
Post-Repair Verification Handlers
                   ↓
SQLite Audit Trail & Educational Synthesis
```

### Strict Invariants
* **`LLM != Windows Shell`**: Zero shell execution, zero arbitrary PowerShell, zero `eval`/`exec`, 0 prohibited AST primitives.
* **Tool Catalog**: Exactly 59 tools (49 SAFE, 10 MEDIUM, 0 HIGH, 0 duplicates, 0 aliases).
* **Fail-Closed Safety**: Any unexpected failure, schema mismatch, or crash immediately blocks further execution without risking system instability.

---

## 📊 Quality & Test Coverage

* **Regression & Production Tests**: **480 / 480 passing (100%)**
* **Security Boundaries**: Verified across 15+ attack vectors and injection tests
* **Offline Operation**: 100% functional without internet connectivity

---

## 📚 Documentation Links

* [Installation Guide](file:///c:/Users/karth/OneDrive/Desktop/WinFix-AI/INSTALLATION.md)
* [User Guide](file:///c:/Users/karth/OneDrive/Desktop/WinFix-AI/USER_GUIDE.md)
* [Troubleshooting Guide](file:///c:/Users/karth/OneDrive/Desktop/WinFix-AI/TROUBLESHOOTING.md)
* [Security Architecture](file:///c:/Users/karth/OneDrive/Desktop/WinFix-AI/SECURITY.md)
* [System Architecture](file:///c:/Users/karth/OneDrive/Desktop/WinFix-AI/ARCHITECTURE.md)
* [Release Notes v1.0.0](file:///c:/Users/karth/OneDrive/Desktop/WinFix-AI/RELEASE.md)
