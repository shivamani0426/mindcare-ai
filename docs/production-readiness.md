# Unified production-readiness gate

MindCareAI remains an educational, non-diagnostic prototype. Do not tag v1.0.0 until all release gates are evidenced. Do not use real patient data in CI or demonstrations.

| Gate | Required evidence | Current checkpoint (2026-11-24) |
| --- | --- | --- |
| 01 Database protection | Encrypted production backup; private isolated restore; durable hosting or verified migration before expiry | Backup tooling exists; isolated rehearsal and synthetic CI added; actual backup and restore pending; free DB expires 2026-12-12 |
| 02 Security validation | Google and password login, session/CSRF, throttling, access revocation, password recovery and privacy audit | Google and email login passed user-reported production testing; recovery and session invalidation implemented, live email delivery and final privacy review pending |
| 03 Communication reliability | Authorized TURN relay; two real devices on different networks; bidirectional audio/video and consent revocation | User reported successful Wi-Fi/mobile-data calls; TURN-only relay evidence still pending |
| 04 Mobile optimization | Android Chrome and iOS Safari real-device journeys, viewport, touch and animation performance | Chromium Pixel 7 and WebKit iPhone 13 emulation passed 11 routes; user reported Android and iOS responsiveness passed |
| 05 Accessibility | Keyboard, focus, screen reader, contrast, large controls, reduced motion, elderly usability | User reported large text, contrast and reduced motion passed; assistive technology and elderly usability audit pending |
| 06 Complete app testing | Patient and caregiver flows including negative authorization cases, reminders, family and games | 84 backend tests, 236 browser checks, 11 emulated mobile routes and 11 user-reported manual checks passed on unified release |
| 07 Release | All gates evidenced, health, logs, rollback, data lifecycle documentation and release tag | Not released |

A synthetic recovery test is necessary but not sufficient: do not upload a production archive or its keys to CI. Keep all deployment secrets private. No plan upgrades, database migration, paid relay, or destructive changes without explicit authorization. See [backup and restore](backup-and-restore.md).

## Final validation record

User-reported production checks on the deployed unified build: Google login/logout, email/password login, patient/caregiver registration, caregiver linking/approval/revocation, all six games, reminders/voice, family photo upload/full screen, WhatsApp contacts, cross-network calls, Android/iOS responsiveness, and large text/high contrast/reduced motion. These are recorded as user-reported evidence, not independently witnessed results. Retest login and account recovery after the next security deployment. Production recovery, durable hosting, verified email delivery, TURN relay-only test, physical screen-reader usability, privacy and regulatory review remain outstanding. No production archive or credentials may enter GitHub or chat.
