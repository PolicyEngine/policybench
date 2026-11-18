# Committed wording amendments: the 14 release 20261014 dropped

`annotations/us_full_run_20260612_policyengine_4_16_1_populace/us_wording-amendments.json`
lists the wording amendments board releases from dashboard-data-20260930 on
made to published audit text: the case, the field (a row annotation, a case
note, or a decision's reasoning in the adjudication record), the exact old
text and its replacement. Each release that made amendments appended them as
one block. Release dashboard-data-20261006's whole-field rewrites are in two
other records (`docs/release_20261006/annotation_rewrites.json` and
`reference_audit/2026-10-05-medicaid-031-annotations/rewrites.json`): its 342
on audit text are on cases release 20261010 re-judged, and its 9 on the
reference explanations stay published, since the drivers hold that file to
the base release's bytes. `policybench/wording_amendments.py` says which of
the record's entries are in force and whether the committed files publish
them, and gives the next board release the restoration of the 14 that no
release since dashboard-data-20261014 has published.

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
rule (it held the reference explanations and the adjudication record to the
base, but not the two text files). So it published the 14 passages' old
text, and the freeze copied the record forward unchanged. Release 20261013b's
own tests of its committed text stop running once the pointer names a later
release.

Release dashboard-data-20261027 rebuilt the same text from the same verdicts.
Release dashboard-data-20261111's carry (`carry_kept_wording`,
`docs/fable52/design.md`) carries each kept case's text from release
20261027's committed files, so it carried the old text too, as
`committed_amendments` in `scripts/freeze_fable52.py` notes. No other entry
of the record, and none of release 20261006's 351 rewrites, was dropped:
each is published at its own release. Compared release to release, the text
of a case the later release kept changed only through release 20261006's
rewrites, the 14, and the adjudication sentences new decisions appended.

## The invariant

A row annotation or case note amendment is in force from its release until a
later release re-judges its case; the new verdict then replaces the text it
corrected. A reasoning amendment stays in force while the adjudication record
holds the decision: a re-judge changes a decision's reasoning only through
listed amendments (`verify_adjudication_record` in the freezes), and the case
note's adjudication sentence restates the reasoning. While an amendment is in
force, the committed files must publish its new text and not its old: a row
annotation in its row; a case note amendment in the note's body, the text
before any adjudication sentence; a reasoning amendment in the adjudication
record and in the sentence. The payload's cells carry the same texts.

`superseding_releases` reads each release's re-judged cases from its
`judge_provenance.json`, registered and pinned by sha256 in `RELEASES`.
Later entries of the same target can rewrite part of an entry's new text, so
`entry_state` undoes them, last first, before testing it. An amendment that
cuts words has its new text inside its old; `holds` counts each outside the
other. The test is presence in the target's text, not position: a target
whose row, note or decision is gone reads MISSING, and an old text that an
unrelated later edit puts back in the same field reads BOTH. Both fail safe.

`tests/test_wording_amendments.py` holds the working tree's committed row
annotations, case notes, adjudication record and snapshot to every amendment
in force, except the entries `known_dropped` names for the release the app's
pointer names: the 14 for releases 20261014, 20261027 and 20261111, a closed
list the tests pin, and none for any later release. The registry test
requires every release that moves the pointer, appends amendments or commits
a `judge_provenance.json` to be listed in `RELEASES`, and every listed
provenance file to match its pin, so the next board release fails the tests
if it leaves the 14 dropped or drops any other amendment in force.

The tests check that with release 20261111's data from git: a Hypothesis
property puts back the old text of any of the 414 row and note amendments in
force that no later entry rewrites and requires `dropped_amendments` to name
it and `restore_frames` to give the files back; undoing the whole chain of
each of the 414 targets in force flags it; and reverting each of the 17
decisions' reasoning, in the record or only in the sentence, is caught.

## The restoration, for the next board release

The 14 are pinned by content (`DROPPED_BY_20261014_SHA256`), so an edit to
the record cannot change what is restored. Restoring them on release
20261111's committed files gives each of the ten targets the text release
20261013b committed, byte for byte, and changes nothing else; in the payload
it rewrites `annotation` or the body of `caseAnnotation` in 18 cells and no
other field. No score, statistic or rank moves: nothing that computes one
reads annotation text, and the reverse change, release 20261014's, moved no
incumbent's `modelStats` or heatmap row.

The next release's driver, forked from `scripts/finish_fable52.py` with
release 20261111 as its base, takes the restoration through the carry:

1. `base_annotation_frames` restores the 14 on the base's committed files:
   `restore_frames(rows, notes, dropped_by_20261014(record))`, all 14
   restored, with the record read at `BASE_COMMIT` as the driver reads its
   other base files. The carry then gives every kept case the restored text,
   and `kept_annotation_problems` holds triage, export and the freeze to it.
2. `prepare_inputs` writes the restored text when it copies the two
   annotation files into the bundle (`restore_csv_texts`, which writes them as
   triage does), so a full `--early` rehearsal, which runs check (a) on the
   copied files, carries the restoration too.
3. Check (a), `base_restoration_problems`, compares the scope export's cells
   with `restore_payload(live, entries, reopened=reopened)` instead of
   `live`, in `_build_payload_in_scratch`, which export and the freeze's
   rebuild both call. A case the release re-opens keeps its new verdict's
   text; `restore_payload` skips it, and check (a) exempts its text fields
   anyway.
4. The record is not changed: the 14 entries are already in it. The freeze's
   `committed_amendments` note about them is dropped.
5. The release adds itself to `RELEASES`, with its block size and its pinned
   judge provenance. `known_dropped` gives it none, so the tests hold its
   committed files and snapshot to all 14. The restoration tests read
   release 20261111's files from git and need no change.

`tests/test_wording_amendments.py` runs steps 1 and 3 through the Fable 5.2
driver's functions: with the restored base, triage's frames are the restored
files and the kept-case gate passes them; a release that carries the base
without the restoration fails that gate on each of the ten targets. Against
the restored base payload, check (a) passes an export carrying the
restoration, flags the one cell of an export missing one restored row, and
flags all 18 cells of an export missing all of it. It does not run the
next driver, which does not exist yet.

Publishing the restoration changes published text on kept cells, so it ships
only on the maintainer's go. The release note would say: "Restores the
corrected wording of 14 annotation passages on five cases, which release
dashboard-data-20261014 had reverted to their earlier text. No score or rank
changes."
