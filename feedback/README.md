# User feedback

This is the durable, sanitized record of what users experienced. Implementation
tasks live in the [app issue index](https://github.com/LightningEg/Lightning/blob/main/issues/INDEX.md).

## Intake and triage

1. Keep raw submissions and private attachments in their existing private source.
   Do not commit identities, emails, phone/account numbers, device/session IDs,
   private links or screenshots of real financial data.
2. Create `feedback/YYYY-MM-DD-subject.md` from [the feedback template](../templates/feedback.md).
   Give observations stable IDs within the record and describe the screen/build,
   observed behavior, expected behavior and evidence using sample data. Keep any
   retained sample screenshots under feedback/YYYY-MM-DD-subject/evidence/ and
   link them from the record and implementation item.
3. Group repeated observations under a theme. Count observations separately from
   distinct respondents; do not infer people from sessions or repeated tickets.
4. Investigate each observation: defect, request, existing behavior, not
   reproduced or conflicts with an adopted rule. Link confirmed work to an
   existing issue, or create one; do not maintain a second backlog here.
5. Append dated dispositions and verification links. Keep the sanitized record
   after the implementation issue is deleted. Replace links to deleted issue
   files with commit-pinned references before closing the work.

## Records

No historical submissions have been imported into this structure. Earlier
processed feedback survives in Git history, the changelog and regression tests;
this catalogue does not imply that those observations were lost or re-reviewed.
Add a dated link here for every new record. Do not reconstruct respondent counts
or historical verdicts without evidence.

The [feedback-review procedure](https://github.com/LightningEg/Lightning/blob/main/skills/feedback-review/SKILL.md)
owns investigation and implementation. Reports contain audit findings; this
directory contains user observations.
