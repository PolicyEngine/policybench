# Committed wording amendments: the 14 release 20261014 dropped

`annotations/us_full_run_20260612_policyengine_4_16_1_populace/us_wording-amendments.json`
lists every wording-only amendment a board release made to published
annotation text: the case, the field (a row annotation, a case note, or a
decision's reasoning in the adjudication record), the exact old text and its
replacement. Each release that made amendments appended them as one block.
`policybench/wording_amendments.py` says which entries are in force and
whether the committed files publish them, and gives the next board release
the restoration of the 14 that no release since dashboard-data-20261014 has
published.

## What happened

Release dashboard-data-20261013b re-judged five cases and amended 14 passages
of their text: six on `scenario_015` `head_medicaid_eligible`, three on
`scenario_015` `federal_refundable_credits`, two each on `scenario_014` and
`scenario_086` `federal_refundable_credits`, and one on `scenario_045` `snap`
(record entries 856 to 869, ten targets: four case notes and six row
annotations). Its committed files and snapshot publish them.

Release dashboard-data-20261014 (#221) kept those five cases. Its driver,
`scripts/finish_argon.py`, rebuilt every case's text from the seed's
verdicts, which hold the judge's wording from before the amendments, and
replayed only its own stage's amendments, which `load_amendments` limits to
cases it re-judged. None of its gates compared a kept case's text with the
base release's committed files: export's scope check holds the incumbents'
`modelStats`, and the freeze rebuilds the annotation files by triage's own
rule. So it published the 14 passages' old text, and the freeze copied the
record forward unchanged.

Release dashboard-data-20261027 rebuilt the same text from the same verdicts.
Release dashboard-data-20261111's carry (`carry_kept_wording`,
`docs/fable52/design.md`) carries each kept case's text from release
20261027's committed files, so it carried the old text too, as its review's
Q8 and `committed_amendments` in `scripts/freeze_fable52.py` record. No other
entry of the record, and none of release 20261006's 351 rewrites, was
dropped: every one is published at its own release and stays published until
a later release re-judges its case.

## The invariant

An amendment is in force from its release until a later release re-judges
its case; the new verdict then replaces the text it corrected. While it is in
force, the committed files must publish its new text and not its old.
`superseding_releases` reads each release's re-judged cases from its
`judge_provenance.json`, registered in `RELEASES`. Later entries of the same
target can rewrite part of an entry's new text, so `entry_state` undoes them,
last first, before testing it. An amendment that cuts words has its new text
inside its old; `holds` counts each outside the other.

`tests/test_wording_amendments.py` holds the committed row annotations, case
notes, adjudication record and snapshot to every amendment in force, except
the entries `known_dropped` names for the release the app's pointer names:
the 14 for releases 20261014, 20261027 and 20261111, and none for any other.
The registry test requires every release that moves the pointer, appends
amendments or commits a `judge_provenance.json` to be listed in `RELEASES`,
so the next board release cannot pass with the 14 still dropped or with any
other amendment dropped. A Hypothesis property draws any of the 413
amendments in force that a release could drop by publishing the old text (no
later entry rewrites them; ten of the 14 among them), puts its old text back,
and requires
`dropped_amendments` to name it and `restore_frames` to give back the files.

## The restoration, for the next board release

The 14 are pinned by content (`DROPPED_BY_20261014_SHA256`), so an edit to
the record cannot change what is restored. Restoring them on release
20261111's committed files gives each of the ten targets the text release
20261013b committed, byte for byte, and changes nothing else; in the payload
it rewrites `annotation` or `caseAnnotation` in 18 cells and no other field.
No score, statistic or rank moves.

The next release's driver, forked from `scripts/finish_fable52.py` with
release 20261111 as its base, takes the restoration through the carry:

1. `base_annotation_frames` restores the 14 on the base's committed files:
   `restore_frames(rows, notes, dropped_by_20261014(load_record()))`, all 14
   restored. The carry then gives every kept case the restored text, and
   `kept_annotation_problems` holds triage, export and the freeze to it.
2. Check (a), `base_restoration_problems`, compares the scope export's cells
   with `restore_payload(live, entries, reopened=reopened)` instead of
   `live`, in the export and in the freeze's rebuild alike. A case the
   release re-opens keeps its new verdict's text; `restore_payload` skips it,
   and check (a) exempts its text fields anyway.
3. The record is not changed: the 14 entries are already in it.
4. The release adds itself to `RELEASES`. `known_dropped` gives it none, so
   the test holds its committed files and snapshot to all 14.

`tests/test_wording_amendments.py` runs this path through the Fable 5.2
driver: with the restored base, triage's frames are the restored files and
the kept-case gate passes them; a release that carries the base without the
restoration fails that gate on each of the ten targets, and check (a) against
the unrestored base flags the 18 cells.

Publishing the restoration changes published text on kept cells, so it ships
only on the maintainer's go. The release note would say: "Restores the
corrected wording of 14 annotation passages on five cases, which release
dashboard-data-20261014 had reverted to their earlier text. No score or rank
changes."
