---
name: env-powershell-encoding
description: Never edit repo files with PowerShell Get-Content/Set-Content on this machine - it mangles UTF-8 into CP1250 mojibake and adds a BOM
metadata:
  type: feedback
---

Never rewrite a source file with `(Get-Content x -Raw) -replace ... | Set-Content x`
on this machine. Use the Edit/Write tools instead.

**Why:** this is a Czech-locale Windows box, so Windows PowerShell 5.1 decodes
files with **CP1250**, not UTF-8. A read/replace/write round-trip silently turns
every non-ASCII character into mojibake (`—` becomes `â€"`, `→` becomes `â†'`,
`×` becomes `Ã—`) and `Set-Content -Encoding utf8` prepends a UTF-8 BOM. Both
survive into the commit and pollute the diff. This actually happened while
repairing `backend/tests/test_broker.py` — the source comments there are full of
em dashes and arrows, so a "12-line" edit produced a 44-line diff.

**How to apply:** for any multi-site rename across a file, use Edit with
`replace_all`, or several targeted Edit calls. If a PowerShell rewrite has
already happened, repair it by reading the raw bytes, stripping a leading
`EF BB BF`, then `utf8.GetString(cp1250.GetBytes(text))` and writing back with
`New-Object System.Text.UTF8Encoding($false)` — and verify with `git diff --numstat`
that the line count matches the edit you intended.
