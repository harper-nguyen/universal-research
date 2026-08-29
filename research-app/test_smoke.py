"""
Smoke tests for Universal Research App v0.1.1

Run from research-app/ directory:
    python test_smoke.py

Tests:
    1. Canonical SKILL.md exists and is loadable
    2. SKILL.md is non-empty and has expected structure
    3. app.py syntax is valid
    4. app.py loads SKILL.md from canonical path (../SKILL.md)
    5. app.py configures system_instruction with skill content
    6. app.py enables google_search grounding
    7. app.py has st.stop() guard if skill fails to load
"""

import os
import ast
import sys

PASS = "\033[92m  PASS\033[0m"
FAIL = "\033[91m  FAIL\033[0m"
results = []

def check(name, condition, detail=""):
    status = PASS if condition else FAIL
    print(f"{status}  {name}")
    if not condition and detail:
        print(f"       → {detail}")
    results.append(condition)

print("\n=== Universal Research App v0.1.1 — Smoke Tests ===\n")

# ── Test 1: Canonical SKILL.md exists ────────────────────────────────────────
app_dir = os.path.dirname(os.path.abspath(__file__))
canonical_skill = os.path.normpath(os.path.join(app_dir, "..", "SKILL.md"))
check(
    "Canonical SKILL.md exists at research/SKILL.md",
    os.path.isfile(canonical_skill),
    f"Expected: {canonical_skill}"
)

# ── Test 2: SKILL.md is readable and non-empty ───────────────────────────────
try:
    with open(canonical_skill, "r", encoding="utf-8") as f:
        skill_content = f.read()
    check("SKILL.md is readable and non-empty", bool(skill_content.strip()))
except Exception as e:
    check("SKILL.md is readable and non-empty", False, str(e))
    skill_content = ""

# ── Test 3: SKILL.md contains expected structural markers ────────────────────
required_markers = [
    "name: universal-research",
    "No Fabrication",
    "Final Quality Check",
    "Stopping Criteria",
]
for marker in required_markers:
    check(f"SKILL.md contains '{marker}'", marker in skill_content)

# ── Test 4: No stale SKILL.md copy in research-app/ ─────────────────────────
stale_copy = os.path.join(app_dir, "SKILL.md")
check(
    "No stale SKILL.md copy in research-app/",
    not os.path.isfile(stale_copy),
    f"Stale copy found at: {stale_copy} — remove it or add to .gitignore"
)

# ── Test 5: app.py syntax is valid ───────────────────────────────────────────
app_path = os.path.join(app_dir, "app.py")
try:
    with open(app_path, "r", encoding="utf-8") as f:
        app_source = f.read()
    ast.parse(app_source)
    check("app.py syntax is valid", True)
except SyntaxError as e:
    check("app.py syntax is valid", False, str(e))
    app_source = ""

# ── Test 6: app.py loads from canonical ../SKILL.md ─────────────────────────
check(
    "app.py loads SKILL.md from canonical path (../SKILL.md)",
    '"..", "SKILL.md"' in app_source or '"..", \'SKILL.md\'' in app_source,
    "get_skill_content() should resolve to ../SKILL.md"
)

# ── Test 7: system_instruction uses skill_content ────────────────────────────
check(
    "app.py injects SKILL.md as system_instruction",
    "system_instruction=skill_content" in app_source,
    "GenerateContentConfig must include system_instruction=skill_content"
)

# ── Test 8: google_search grounding is enabled ───────────────────────────────
check(
    "app.py enables google_search grounding",
    '"google_search"' in app_source,
    "tools must include {'google_search': {}}"
)

# ── Test 9: st.stop() guard if skill fails ───────────────────────────────────
check(
    "app.py calls st.stop() if skill fails to load",
    "st.stop()" in app_source and "if not skill_content" in app_source,
    "main() must guard against missing skill with st.stop()"
)

# ── Test 10: SKILL.md in .gitignore for research-app ─────────────────────────
gitignore_path = os.path.join(app_dir, ".gitignore")
try:
    with open(gitignore_path) as f:
        gitignore_content = f.read()
    check(
        "research-app/.gitignore blocks SKILL.md copy",
        "SKILL.md" in gitignore_content,
        ".gitignore should contain SKILL.md to prevent drift"
    )
except Exception:
    check("research-app/.gitignore blocks SKILL.md copy", False, ".gitignore not found")

# ── Summary ──────────────────────────────────────────────────────────────────
passed = sum(results)
total = len(results)
print(f"\n{'='*50}")
print(f"Results: {passed}/{total} passed")
if passed == total:
    print("\033[92m✓ All smoke tests passed. v0.1.1 is ready.\033[0m")
else:
    print(f"\033[91m✗ {total - passed} test(s) failed. Fix before release.\033[0m")
    sys.exit(1)
print("="*50 + "\n")
