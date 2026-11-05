# Local validation record — 2026-11-05

Historical synthetic-fixture results. Subsequent approved implementation and
**real Nexus + Mnemosyne** validation are recorded in [PILOT.md](PILOT.md).

Scope: isolated protocol fixture only. The production Nexus and all module
sources were read, not edited. Existing uncommitted changes were left intact.
No deployment, image build, live API call, login or credential access was used.

## Results

| Check | Result |
| --- | --- |
| `node --test docs/proposals/navigation-history/protocol.test.mjs` | 5 passed |
| `node --check docs/proposals/navigation-history/server.mjs` | Passed |
| `browser-proof.py`, Playwright 1.64.1, installed Chrome 157.0.8103.39, Windows, headless | 10 checks passed; no page script errors |
| Existing `npm test` | 19 passed |
| Existing targeted Python suites with UTF-8 enabled | 43 passed, 1 failed (existing Windows incompatibility below) |

The browser checks asserted visible child view **and** top-level URL/traversal:

1. Direct route with nested query/fragment, preserved bootstrap path, real opaque
   frame (`window.origin === 'null'`), blocked parent DOM access (`SecurityError`).
2. One top-level entry per internal action; no frame replacement in the same module.
3. Native browser Back/Forward restores internal views without history echo.
4. Duplicate intent creates no entry; replace correctly updates the current entry.
5. Reload restores from URL without relying on JavaScript state.
6. Cross-module Back/Forward restores both module and internal view, without an
   intermediate child-document history step.
7. Slow obsolete render cannot overwrite a newer view; multi-entry traversal works.
8. Stale revision, invalid route and foreign-source messages cannot change URL.
9. A legacy module without a handshake remains usable at its existing bootstrap
   path, including Back/Forward to/from a participating module.
10. Chrome CDP synthetic mouse Back/Forward buttons invoke native traversal and
    restore the view. These are browser-generated input events, not a test with
    physical mouse hardware.

The child fixture uses the same sandbox flags and response CSP as the production
gateway. The host fixture implements incremental frame preservation rather than
loading production `frontend/app.js`. Feature discovery is assumed for this
fixture; full old/new host negotiation, authenticated lifecycle, BFCache, real
module schemas and unsaved-editor recovery remain production acceptance gates.
Firefox/WebKit, physical mouse input and a real authenticated Nexus were not tested.

## Reproduce

From `G:/AureateEmpyrean/empyrean-nexus` in PowerShell:

```powershell
node --test docs/proposals/navigation-history/protocol.test.mjs
node --check docs/proposals/navigation-history/server.mjs

# Isolated tooling outside repository dependencies; installed Chrome required.
python -m pip install --target "$env:TEMP\nexus-navigation-proof-python" playwright==1.64.1
$env:PYTHONPATH = "$env:TEMP\nexus-navigation-proof-python"
python docs/proposals/navigation-history/browser-proof.py

# Existing repository checks (not fixture dependencies).
npm test
.\.venv\Scripts\python.exe -X utf8 -m pytest -q tests/test_navigation.py tests/test_application.py tests/test_nexus.py
```

The browser runner starts `server.mjs` on `127.0.0.1:19439`, uses a temporary
Chrome profile, and closes the browser and server in cleanup. To choose another
port set `NEXUS_PROOF_PORT`. Production package files and dependency lockfiles
are unchanged. To inspect manually, run `node docs/proposals/navigation-history/server.mjs`
and visit `/app/modules/fixture-alpha`; stop with Ctrl+C.

## Existing test limitations encountered

`tests/test_application.py::test_locale_preserved` fails inside the unchanged
`backend/nexus/app.py:427` because `os.statvfs` is unavailable on Windows.
This route failure is unrelated to the isolated fixture, which imports no Nexus
backend code. The initial run without `-X utf8` also failed the existing stylesheet
test because the Windows cp1250 default could not decode UTF-8 CSS; that test
passed with UTF-8 enabled. No test was skipped, patched or mocked to hide either
result. The remaining Starlette/httpx deprecation warning is existing tooling.

## Decision

The core parent-history / opaque-child restoration mechanism is locally validated
in Chrome. The proposal is ready for architectural review and a default-off host
integration step. This is **not** a completed production migration or cross-browser
sign-off. Follow the gates in [the proposal](README.md) before changing modules.
