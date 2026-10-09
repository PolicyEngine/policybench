"""The diagnosis judge's prompt template, by version.

Every audit prompt (:func:`policybench.audit.render_case_prompt`) is one of
these headers followed by the case. A version's text never changes once a
verdict has been judged on it: a release carries a seed verdict forward only
when its case re-renders to the exact bytes the judge read, so the renderer
must still produce every version a carried verdict was judged on. Changing
the template means adding a version.

- **v1**, the only template before versions were added (2026-10-09), so
  every verdict judged before then, through release dashboard-data-20261006
  and the Claude Haiku 5.5 release's judges. It tells the judge that the
  reference pipeline "has survived an adversarial review program" and that
  "the few real bugs found were fixed before this run".
  That is not so: release dashboard-data-20261006's exclusion record stops
  scoring 28 outputs for engine defects, and the 2026-10-05 reference
  adversary found four more.
- **v2**, v1 without that claim. New cases and re-opened cases use it.

Each verdict's provenance sidecar (``verdict.meta.json``) records the version
of the prompt it was judged on as ``judge_template_version``. A sidecar
without the field, or a verdict without a sidecar, predates the versions and
was judged on v1.

Dependency-free, so the audit runners can read a prompt's version.
"""

from __future__ import annotations

from collections.abc import Mapping

# The sidecar field recording the version a verdict was judged on.
TEMPLATE_VERSION_FIELD = "judge_template_version"
# The version of a verdict whose sidecar does not record one.
UNRECORDED_TEMPLATE_VERSION = 1
# The version new and re-opened cases are rendered with.
CURRENT_TEMPLATE_VERSION = 2

_V1 = """\
You are diagnosing why AI models missed a PolicyEngine reference value on a \
US/UK tax-and-benefit estimation benchmark. The models answered from \
parametric knowledge with no tools; PolicyEngine's microsimulation is the \
reference.

The reference value and its derivation are generated directly from the \
engine's computation trace, and the reference pipeline has survived an \
adversarial review program: every wrong-reference hypothesis raised by \
earlier audits was adjudicated against primary sources, and the few real \
bugs found were fixed before this run. Treat the reference and its \
derivation as correct. Your job is NOT to re-litigate the reference — it is \
to explain each model's mistake decisively.

For every wrong model, write a `diagnosis`: 1-3 definitive sentences naming \
the exact rule, eligibility pathway, deduction, threshold, or computation \
step that model missed or misapplied, grounded in its own stated reasoning. \
Be specific — "treated the 138% FPL MAGI limit as the only Medicaid pathway \
and never applied the aged/disabled income test, which deducts the Medicare \
Part B premium from countable income" — not generic ("got the income \
calculation wrong"). If the model gave no usable reasoning, derive the \
mistake from its answer: state what the correct derivation yields and what \
shortcut the model's number is consistent with.

Hedging is forbidden in `diagnosis` and `rationale`, and these phrasings \
are mechanically rejected: "plausible"; "not enough evidence"; \
"insufficient evidence/information"; "cannot/unable to \
determine/verify/confirm/tell"; "difficult/hard to verify"; "may be/have"; \
"might be/have"; "possibly"; "perhaps"; "unclear"; "the reference \
is/appears/seems correct" or any other verdict on the reference. Write \
definitively around them (e.g. "excess shelter costs are deductible", not \
"may be deducted"). Doubt \
about the reference belongs ONLY in reference_suspect + \
reference_bug_hypothesis, and requires a concrete contradiction: the \
derivation conflicts with a specific statute, regulation, or published \
parameter you can name, or contradicts its own arithmetic. Absent that, set \
reference_suspect=false and diagnose from the reference as ground truth.

failure_source meanings:
- llm_error: the model reasoned or computed incorrectly (the usual case).
- prompt_ambiguity: the question is genuinely ambiguous; a careful expert \
could read it more than one way. Name the two readings.
- reference_model_issue_fixed / reference_data_issue_fixed: the reference \
value looks wrong (PolicyEngine logic / underlying data). Use with \
reference_suspect=true and a concrete contradiction.
- parse_contract_failure: the model's answer was missing or unparseable, not a \
substantive error.
- budget_exhausted_at_ceiling: the provider length-terminated every retry through \
its maximum allowed completion budget.
- needs_review: genuinely cannot tell; name precisely what information is \
missing.

Output ONLY the JSON verdict matching the schema. Do not run any commands; all \
information you need is below.
"""

# The claim v2 drops: the clause ends v1's second paragraph's first sentence.
V1_REVIEW_CLAIM = (
    ", and the reference pipeline has survived an adversarial review program: "
    "every wrong-reference hypothesis raised by earlier audits was adjudicated "
    "against primary sources, and the few real bugs found were fixed before "
    "this run"
)
if _V1.count(V1_REVIEW_CLAIM) != 1:
    raise AssertionError("v1 states the review claim exactly once")
_V2 = _V1.replace(V1_REVIEW_CLAIM, "", 1)

JUDGE_TEMPLATE_HEADERS: dict[int, str] = {1: _V1, 2: _V2}


def template_header(version: int) -> str:
    """The header a prompt of ``version`` begins with."""
    if type(version) is not int or version not in JUDGE_TEMPLATE_HEADERS:
        raise ValueError(
            f"no judge template version {version!r}; the versions are "
            f"{sorted(JUDGE_TEMPLATE_HEADERS)}"
        )
    return JUDGE_TEMPLATE_HEADERS[version]


def template_version_of(prompt: str | bytes) -> int | None:
    """The version whose header begins ``prompt``, or None if none does.

    No header is a prefix of another, so at most one matches.
    """
    if isinstance(prompt, bytes):
        try:
            prompt = prompt.decode("utf-8")
        except UnicodeDecodeError:
            return None
    for version, header in JUDGE_TEMPLATE_HEADERS.items():
        if prompt.startswith(header):
            return version
    return None


def recorded_template_version(meta: Mapping | None) -> int | None:
    """The version a verdict's sidecar records it was judged on.

    No sidecar (None), or one without the field, means v1. A value that names
    no version (null, a string, a boolean, an unknown number) gives None: the
    verdict's template is unknown.
    """
    if meta is None or TEMPLATE_VERSION_FIELD not in meta:
        return UNRECORDED_TEMPLATE_VERSION
    value = meta[TEMPLATE_VERSION_FIELD]
    if type(value) is int and value in JUDGE_TEMPLATE_HEADERS:
        return value
    return None
