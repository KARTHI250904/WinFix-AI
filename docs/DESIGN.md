# WinFix AI — UI/UX Design

## 1. Design Goal

WinFix AI must feel like a friendly, trustworthy computer technician sitting beside the user.

The interface is built for non-technical users first:
* No raw terminal outputs or error codes on primary screens.
* Clear, simple explanations of what is happening.
* Technical details preserved inside expandable sections for advanced users.

---

## 2. Main Screen Layout

```text
┌─────────────────────────────────────────────┐
│                                             │
│                 🛠 WinFix AI                │
│                                             │
│       Your offline Windows assistant        │
│                                             │
│   What is happening with your computer?     │
│                                             │
│ ┌─────────────────────────────────────────┐ │
│ │ Tell me what is wrong...                │ │
│ └─────────────────────────────────────────┘ │
│                                             │
│     🎤 Voice       📷 Screenshot            │
│                                             │
│                                             │
│  How would you like me to help?             │
│                                             │
│ ┌──────────────────┐ ┌────────────────────┐ │
│ │ 👨‍🏫 Tutor         │ │ ⚡ Autopilot        │ │
│ │                  │ │                    │ │
│ │ Teach me and     │ │ Diagnose and       │ │
│ │ explain it       │ │ fix it for me      │ │
│ └──────────────────┘ └────────────────────┘ │
│                                             │
│                 [ Start Diagnosis ]         │
│                                             │
└─────────────────────────────────────────────┘
```

---

## 3. Tutor Mode Experience

Tutor mode prioritizes education and user control:

* **What is happening:** Plain-language summary of the understood problem.
* **Why we are checking:** Plain explanation for each diagnostic check before it runs.
* **What we found:** Simple summary of empirical evidence collected.
* **Repair proposal:** Plain explanation of the proposed fix with risk level indicated.
* **Confirmation prompt:** Explicit user confirmation requested before every repair.
* **Elevation prompt (if needed):** Clear explanation if administrator privileges are required.
* **Verification result:** Clear report of verified outcomes.

---

## 4. Autopilot Mode Experience

Autopilot mode prioritizes speed and autonomy while maintaining strict safety:

* Shows a live progress stepper:
  ```text
  [✓] Understanding problem
  [✓] Checking network adapter
  [✓] Testing default gateway
  [⟳] Testing DNS resolution...
  [ ] Applying approved repair
  [ ] Verifying fix
  ```
* Automatically runs approved SAFE diagnostics and SAFE repairs.
* Pauses with an explicit prompt if a MEDIUM repair requires confirmation/elevation.
* Blocks HIGH-risk operations completely.
* Shows the final verified outcome card upon completion.

---

## 5. Standardized UI Cards

### 5.1 Diagnosis Card
```text
┌───────────────────────────────────────────┐
│ 🔍 Problem: Internet Connectivity        │
│ Status: Needs Attention  | Confidence: High│
├───────────────────────────────────────────┤
│ Likely Cause: DNS resolution failure      │
│                                           │
│ Evidence:                                 │
│  ✓ Wi-Fi adapter connected                │
│  ✓ Default gateway reachable              │
│  ✕ DNS lookup failed                      │
└───────────────────────────────────────────┘
```

### 5.2 Repair Card
```text
┌───────────────────────────────────────────┐
│ 🔧 Recommended Repair: Flush DNS Cache    │
├───────────────────────────────────────────┤
│ Why: Clears outdated website address data │
│ Risk Level: SAFE                          │
│ Administrator Required: No                │
│                                           │
│ [ Fix This Now ]  [ Explain More ] [ Cancel ]│
└───────────────────────────────────────────┘
```

### 5.3 Elevation Prompt Card (for MEDIUM Tools)
```text
┌───────────────────────────────────────────┐
│ 🛡 Administrator Permission Required      │
├───────────────────────────────────────────┤
│ Action: Restart Network Adapter           │
│ Reason: Windows requires elevated rights  │
│ to reset network hardware adapters.       │
│                                           │
│ [ Allow & Continue ]          [ Cancel ]  │
└───────────────────────────────────────────┘
```

### 5.4 Outcome Cards

* **Success Card:**
  ```text
  🎉 Problem Resolved
  ✓ DNS cache cleared
  ✓ DNS lookup verified
  ✓ Internet connectivity restored
  ```
* **Failure Card:**
  ```text
  ⚠️ Problem Not Fully Resolved
  The DNS repair completed, but internet connectivity is still unavailable.
  Next Recommended Step: Check router and gateway configuration.
  [ Continue Diagnosis ]
  ```

---

## 6. Progressive Disclosure: Expandable Technical Details

Every diagnosis and repair card includes a collapsible drawer:

```text
▼ Technical Details (Click to Expand)
  Tool: check_dns
  Exit Code: 0
  Query Target: 8.8.8.8
  Latency: 28ms
  DNS Server: 192.168.1.1
  Raw JSON Output: { ... }
```

This allows non-technical users to enjoy a clutter-free experience while developers and power users have full diagnostic transparency.
