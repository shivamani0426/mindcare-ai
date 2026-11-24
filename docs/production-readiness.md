# Unified production-readiness gate

MindCareAI remains an educational, non-diagnostic prototype. Do not tag v1.0.0 until all release gates are evidenced. Do not use real patient data in CI or demonstrations.

| Gate | Required evidence | Current checkpoint (2026-11-24) |
| --- | --- | --- |
| 01 Database protection | Encrypted production backup; private isolated restore; durable hosting or verified migration before expiry | Backup tooling exists; isolated rehearsal and synthetic CI added; actual backup and restore pending; free DB expires 2026-12-12 |
| 02 Security validation | Google and password login, session/CSRF, throttling, access revocation, password recovery and privacy audit | Existing tests and Google login on previous deployment verified; final security review pending |
| 03 Communication reliability | Authorized TURN relay; two real devices on different networks; bidirectional audio/video and consent revocation | Signaling tests and TURN configuration hooks exist; relay and live test pending |
| 04 Mobile optimization | Android Chrome and iOS Safari real-device journeys, viewport, touch and animation performance | Chromium browser tests exist; physical-device review pending |
| 05 Accessibility | Keyboard, focus, screen reader, contrast, large controls, reduced motion, elderly usability | Existing accessibility features; final audit pending |
| 06 Complete app testing | Patient and caregiver flows including negative authorization cases, reminders, family and games | Existing regression suites; final integrated testing pending |
| 07 Release | All gates evidenced, health, logs, rollback, data lifecycle documentation and release tag | Not released |

A synthetic recovery test is necessary but not sufficient: do not upload a production archive or its keys to CI. Keep all deployment secrets private. No plan upgrades, database migration, paid relay, or destructive changes without explicit authorization. See [backup and restore](backup-and-restore.md).
