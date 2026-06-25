# Sentinel Handoffs Index

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
