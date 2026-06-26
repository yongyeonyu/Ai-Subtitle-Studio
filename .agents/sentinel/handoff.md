# Sentinel Handoffs Index

- `.agents/sentinel/handoffs/20260626-221500-timing-lock-support-risk-review.md`
- `.agents/sentinel/handoffs/20260626-215623-watchdog-handoff-probe.md`
- `.agents/sentinel/handoffs/20260626-211503-watchdog-handoff-probe.md`
- `.agents/sentinel/handoffs/20260626-203500-nas-50-split-protocol-risk-review.md`
- `.agents/sentinel/handoffs/20260626-203104-watchdog-handoff-probe.md`
- `.agents/sentinel/handoffs/20260626-180300-heydealer-benchmark-risk-review.md`
- `.agents/sentinel/handoffs/20260626-180142-watchdog-handoff-probe.md`
- `.agents/sentinel/handoffs/20260626-143500-cayenne-e2e-validation-checklist.md`
- `.agents/sentinel/handoffs/20260626-143259-watchdog-handoff-probe.md`
- `.agents/sentinel/handoffs/20260626-130000-playback-display-risk-review.md`
- `.agents/sentinel/handoffs/20260626-121900-cayenne-timing-improvement-risk-review.md`
- `.agents/sentinel/handoffs/20260626-121741-watchdog-handoff-probe.md`
- `.agents/sentinel/handoffs/20260626-095500-nle-baseline-remaining-gap-review.md`
- `.agents/sentinel/handoffs/20260626-095301-watchdog-handoff-probe.md`
- `.agents/sentinel/handoffs/20260626-095157-watchdog-handoff-probe.md`
- `.agents/sentinel/handoffs/20260626-085500-nle-completion-audit-gap-review.md`
- `.agents/sentinel/handoffs/20260626-085419-watchdog-handoff-probe.md`
- `.agents/sentinel/handoffs/20260626-083751-x5-source-app-proof-blocker-review.md`
- `.agents/sentinel/handoffs/20260626-083622-watchdog-handoff-probe.md`
- `.agents/sentinel/handoffs/20260626-082519-nle-app-command-save-reload-compatibility-gap.md`
- `.agents/sentinel/handoffs/20260626-082444-watchdog-handoff-probe.md`
- `.agents/sentinel/handoffs/20260626-081702-nle-render-export-parity-risk.md`
- `.agents/sentinel/handoffs/20260626-081618-watchdog-handoff-probe.md`
- `.agents/sentinel/handoffs/20260626-081028-editor-readiness-owner-map.md`
- `.agents/sentinel/handoffs/20260626-080728-nle-closeout-doc-consistency-review.md`
- `.agents/sentinel/handoffs/20260626-024301-watchdog-handoff-probe.md`
- `.agents/sentinel/handoffs/20260626-021011-qa-runner-fixture-repair-risk.md`
- `.agents/sentinel/handoffs/20260626-020348-watchdog-handoff-probe.md`
- `.agents/sentinel/handoffs/20260626-015100-save-reload-compatibility.md`
- `.agents/sentinel/handoffs/20260626-014600-nle-render-plan-parity.md`
- `.agents/sentinel/handoffs/20260626-014100-roughcut-sidecar-review.md`
- `.agents/sentinel/handoffs/20260626-013400-nle-validation-gap.md`
- `.agents/sentinel/handoffs/20260626-013110-roughcut-nle-map.md`
- `.agents/sentinel/handoffs/20260626-012612-watchdog-handoff-probe.md` - watchdog handoff probe; file handoff visible, index pointer normalized by Dex after delayed prepend.

Expected packet path:

- `.agents/sentinel/handoffs/*.md`

Protocol:

- Each completed Jammini support slice should write a new timestamped handoff file.
- The first line of each handoff file should be `DEX_REVIEW_READY`.
- This index should be prepended with a single pointer to the newest handoff without overwriting prior entries.
