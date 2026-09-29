# Contributing to Aureate Empyrean

Empyrean Nexus is free software under AGPL-3.0-or-later. Contributions are welcome from independent developers, including authors of community modules and forks. Contributions to this repository are expected under the same license; do not submit code you do not have permission to contribute. No CLA is introduced by this document.

We encourage an **upstream-first** approach: propose generally useful fixes and improvements upstream so the wider community benefits. Forking, experimentation, modification and redistribution remain legitimate. You do not need upstream approval to maintain a fork. Do not falsely label independent releases as official; see [branding](docs/branding.md).

Before a substantial change, explain the problem, the smallest useful behavior and relevant trust boundaries. Domain-specific features belong in independent modules. Avoid speculative abstractions, new orchestration services and dependencies without demonstrated need.

Follow [development](docs/development.md), run lint/tests/build and the Docker smoke test for runtime changes. Add denied-behavior tests for permissions, auth, routing or manifests. Document new protocol fields and migrations; preserve original author attribution. PR descriptions should state the behavior changed and evidence of verification, including limitations.

Keep discussions respectful and technical. No telemetry, secrets or real personal datasets in tests or issues. Report security weaknesses through the process in [SECURITY.md](SECURITY.md), rather than publishing sensitive exploit details immediately.
