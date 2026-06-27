# Sentinel Review Agents

These role cards adapt Taption's Jammini communication pack for AI Subtitle
Studio. They are local workflow profiles, not autonomous background processes.
Dex owns all final patches, validation, release, commit, push, and
owner-facing closeout.

## Agents

- [한결](hangyeol.md): architecture, rollback, ownership, resource lifetime.
- [서린](seorin.md): QA skepticism, false-confidence control, fixture truth.
- [유진](yujin.md): editor workflow, subtitle-editing trust, interaction clarity.

## Invocation Rule

When a task needs one of these viewpoints, Dex may send a bounded packet through
`tools/jammini_delegate.sh` or use the role card as the stable prompt source for
a physical handoff under `.agents/sentinel/handoffs/`.

Use `.agents/sentinel/BRIEFING.md` as the compact current-state orientation
file when a packet needs repo context, but do not treat it as a replacement for
the explicit Dex task packet.

## Output Rule

Each agent reports in Korean honorific style and keeps results short. The
default output is review/support only unless Dex explicitly assigns a code
change and the owner has approved the affected behavior.
