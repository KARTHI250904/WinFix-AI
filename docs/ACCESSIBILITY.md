# WinFix AI — Accessibility Standards & Implementation (Phase 35)

## 1. Overview & Compliance Goal
WinFix AI ensures that Windows troubleshooting is accessible to all users, including those using screen readers, keyboard navigation, high-contrast modes, or with visual impairments.

---

## 2. Core Accessibility Pillars

### 2.1 Non-Color-Only Status Indicators
Colors are never the sole conveyor of meaning. Every status, badge, and alert includes unambiguous textual prefixes and standard symbols:
- `[SUCCESS] ✓`
- `[VERIFIED] ✓`
- `[PARTIALLY RESOLVED] ⚠️`
- `[CONFIRMATION REQUIRED] ⚠️`
- `[WARNING] ⚠️`
- `[ERROR] ✕`
- `[FAILED] ✕`
- `[UNRESOLVED] ⚠️`
- `[BLOCKED] 🚫`
- `[INFO] ℹ️`
- `[RUNNING] ⏳`
- `[RECOVERING] 🔄`
- `[READY] ●`

### 2.2 Accessible Action Buttons
Buttons pair clear action icons with explicit descriptive verbs and optional context hints:
- `🔍 Diagnose Problem`
- `🛡 Confirm & Apply Fix (Requires Administrator Privileges)`
- `🔄 Resume Safely (Re-check PC First)`
- `✕ Dismiss Guide`

### 2.3 Tabular and Diff Data Presentation
Before-and-after state comparisons and diagnostic breakdowns are formatted using standard markdown tables with explicit headers:
```markdown
| Component / Property | Before Repair | After Repair | Status Change |
| :--- | :--- | :--- | :--- |
| service_status | STOPPED | RUNNING | Changed |
| dns_check | FAIL | SUCCESS | Changed |
```

### 2.4 Keyboard Navigation & Layout Stability
- Streamlit inputs, radio selectors, and expandable drawers maintain stable focus order.
- High-contrast card containers (`border=True`) delineate functional sections without visual clutter.
- No auto-advancing carousels or unpredictable layout jumps.

---

## 3. Testing & Verification
- Unit test suite: `tests/test_phase35_ux.py` verifies prefix completeness, accessible table rendering, button labeling, and AST security compliance.
- Color contrast tested against WCAG 2.1 AA guidelines.
