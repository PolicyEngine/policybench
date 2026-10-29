"""Saved no-tools evidence must agree with the report before any provider call."""

from __future__ import annotations

import hashlib
import io
import json
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.test_confirmatory_no_tools import Provider, nt, write_board_fixture

OPTIONAL_EVIDENCE = (
    "contract",
    "messages",
    "board_prompt_sha256",
    "sent_board_prompt_sha256",
)
REQUIRED_FIELDS = (
    "model",
    "arm",
    "prompt_version",
    "prompt_wording_sha256",
    "tool_notice_sha256",
    "tool_features",
    "calculate_tool_sha256",
    "variables",
    "turns",
    *OPTIONAL_EVIDENCE,
)


def full_record(board, model, engine, sid="h2"):
    """Rebuild the exact treatment pins and prompt through the real harness."""
    profile = nt.pilot.model_profile(
        model, arm="none", prompt_version=nt.PROMPT_VERSION
    )
    with nt.pilot.stating_engine(engine.split()[-1]):
        prompt, settings = nt.pilot.build_initial_request(
            board["scenarios"][sid], board["variables"][sid], profile
        )
    return {
        "scenario_id": sid,
        "model": model,
        "arm": "none",
        "status": "complete",
        "error": None,
        "prompt_version": nt.PROMPT_VERSION,
        "prompt_wording_sha256": nt.pilot.prompt_wording_sha256(profile),
        "tool_notice_sha256": hashlib.sha256(profile.notice.encode()).hexdigest(),
        **nt.pilot.profile_treatment(profile),
        "variables": list(board["variables"][sid]),
        "turns": [{"provider_resolved_model": profile.model_id.split("/")[-1]}],
        "predictions": {"snap": 1},
        "contract": profile.contract,
        "messages": [{"role": "user", "content": prompt}],
        "board_prompt_sha256": settings["_board_prompt_sha256"],
        "sent_board_prompt_sha256": settings["_sent_board_prompt_sha256"],
        "totals": {"cost_usd": 0.1},
        "attempts": [],
    }


def write_fixture_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload))


def save_records(saved, change_link=None):
    """Keep downstream byte hashes and link prefixes valid after one mutation."""

    def save(path, payload):
        text = json.dumps(payload)
        if saved.serialized.get(path) != text:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
            saved.serialized[path] = text

    links = []
    for n, payload in enumerate(saved.archives, 1):
        payload["attempts"] = deepcopy(links)
        path = saved.folder / "attempts" / f"h2-{n}.json"
        save(path, payload)
        try:
            link = nt.entry(path, payload, n, nt.sha256_file(path))
        except (AttributeError, TypeError, ValueError, KeyError):
            # Malformed turn evidence must reach the startup reader, rather
            # than fail while this fixture refreshes otherwise valid links.
            link = deepcopy(saved.original_links[n - 1])
            link["sha256"] = nt.sha256_file(path)
        if change_link is not None:
            change_link(link)
        links.append(link)
    for model, payload in saved.finals.items():
        payload["attempts"] = deepcopy(links) if model == nt.CHEAP[0] else []
        path = saved.root / model / "none/confirmatory/households/h2.json"
        save(path, payload)
    saved.original_links = links


@pytest.fixture(scope="module")
def treatment_templates(tmp_path_factory):
    """Build actual treatment templates once and retain the installed versions."""
    directory = tmp_path_factory.mktemp("saved-record-board")
    versions = nt.pilot._versions()
    baseline = directory / "baseline-exclusions.json"
    baseline.write_text('{"exclusions": []}\n')
    design = {
        "draw_order": ["h2", "outside"],
        "baseline_exclusions": {
            "path": str(baseline),
            "sha256": nt.sha256_file(baseline),
        },
        "no_tools": {
            "runs": "",
            "folder": "none",
            "stage": "confirmatory",
        },
    }
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(nt.pilot, "_versions", lambda: versions)
        write_board_fixture({"design": design}, directory / "board")
        design["draw_order"] = ["h2"]
        board = nt.pilot.load_board(Path(design["board"]))
        finals = {
            model: full_record(board, model, design["engine"]) for model in nt.CHEAP
        }
        yield design, finals


@pytest.fixture
def saved_records(tmp_path, treatment_templates):
    template, template_finals = treatment_templates
    design, finals = deepcopy(template), deepcopy(template_finals)
    design["no_tools"]["runs"] = str(tmp_path / "no-tools")
    archives = [deepcopy(finals[nt.CHEAP[0]]) for _ in range(2)]
    for payload in archives:
        payload.update(status="provider_error", error="APIConnectionError")
    root = Path(design["no_tools"]["runs"])
    folder = root / nt.CHEAP[0] / "none/confirmatory/households"
    saved = SimpleNamespace(
        design=design,
        root=root,
        folder=folder,
        finals=finals,
        archives=archives,
        original_links=[],
        serialized={},
        paths={"final": folder / "h2.json", "archive": folder / "attempts/h2-1.json"},
    )
    save_records(saved)
    return saved


def target_record(saved, reader):
    return saved.finals[nt.CHEAP[0]] if reader == "final" else saved.archives[0]


def no_reply(payload, truncated=False):
    payload["predictions"] = {"snap": None}
    payload["turns"] = (
        [{**payload["turns"][0], "truncated_and_retried": True}] if truncated else []
    )
    for key in OPTIONAL_EVIDENCE:
        payload.pop(key, None)


BAD_VALUES = {
    "model": "synthetic-other-model",
    "arm": "pe",
    "prompt_version": "v1",
    "prompt_wording_sha256": "wrong",
    "tool_notice_sha256": "wrong",
    "tool_features": [],
    "calculate_tool_sha256": "wrong",
    "variables": ["other"],
    "contract": "synthetic-other-contract",
    "board_prompt_sha256": "wrong",
    "sent_board_prompt_sha256": "wrong",
    "messages": {"content": "wrong"},
    "predictions": [],
    "turns": None,
}
MUTATIONS = (
    [f"missing:{field}" for field in REQUIRED_FIELDS]
    + [f"wrong:{field}" for field in BAD_VALUES]
    + [
        "malformed-turn",
        "missing-provider-model",
        "wrong-provider-model",
        "answer-without-completed-turn",
        "empty-messages",
        "malformed-message",
        "wrong-sent-prompt",
    ]
    + [f"fallback:{field}" for field in OPTIONAL_EVIDENCE]
)


def mutate_record(payload, mutation):
    kind, _, field = mutation.partition(":")
    if kind == "missing":
        payload.pop(field)
    elif kind == "wrong":
        payload[field] = deepcopy(BAD_VALUES[field])
    elif kind == "fallback":
        no_reply(payload)
        payload[field] = [] if field == "messages" else "wrong"
        if field == "messages":
            payload[field] = {"content": "wrong"}
    elif mutation == "malformed-turn":
        payload["turns"] = [None]
    elif mutation == "missing-provider-model":
        payload["turns"] = [{}]
    elif mutation == "wrong-provider-model":
        payload["turns"][0]["provider_resolved_model"] = "synthetic-other-model"
    elif mutation == "answer-without-completed-turn":
        payload["turns"] = []
    elif mutation == "empty-messages":
        payload["messages"] = []
    elif mutation == "malformed-message":
        payload["messages"] = [None]
    else:
        assert mutation == "wrong-sent-prompt"
        payload["messages"][0]["content"] = "synthetic other household"


def assert_boundary(saved, boundary, refuses, expected_spend=0.5):
    provider = Provider()
    try:
        if boundary == "startup":
            if refuses is not None:
                with pytest.raises(nt.StateError) as caught:
                    with nt.Stage(
                        saved.design,
                        board=None,
                        run_household=provider,
                        completion_for=lambda profile: None,
                        out=io.StringIO(),
                    ):
                        pytest.fail(
                            "unusable saved evidence must refuse before execution"
                        )
                assert str(refuses) in str(caught.value)
            else:
                with nt.Stage(
                    saved.design,
                    board=None,
                    run_household=provider,
                    completion_for=lambda profile: None,
                    out=io.StringIO(),
                ) as plan:
                    assert plan.spend.spent_usd == pytest.approx(expected_spend)
                    assert all(plan.standing(model, "h2") for model in nt.CHEAP)
        else:
            problems = nt.stage_problems(saved.design)
            if refuses is not None:
                assert any(str(refuses) in problem for problem in problems), problems
            else:
                assert problems == []
    finally:
        assert provider.calls == []


@pytest.mark.parametrize("reader", ["final", "archive"])
@pytest.mark.parametrize("boundary", ["startup", "preflight"])
@pytest.mark.parametrize("mutation", MUTATIONS)
def test_saved_treatment_refuses_with_path(saved_records, reader, boundary, mutation):
    saved = saved_records
    mutate_record(target_record(saved, reader), mutation)
    save_records(saved)
    assert_boundary(saved, boundary, saved.paths[reader])


@pytest.mark.parametrize("boundary", ["startup", "preflight"])
@pytest.mark.parametrize("number", [True, 1.0], ids=["boolean", "float"])
def test_saved_attempt_link_number_requires_integer(saved_records, boundary, number):
    saved = saved_records

    def replace_number(link):
        if link["n"] == 1:
            link["n"] = number

    save_records(saved, replace_number)
    assert_boundary(saved, boundary, saved.paths["final"])


@pytest.mark.parametrize("reader", ["final", "archive"])
@pytest.mark.parametrize("boundary", ["startup", "preflight"])
@pytest.mark.parametrize(
    "form", ["full", "fallback", "truncated-only", "input-message"]
)
def test_valid_saved_treatment_preserves_spend(saved_records, reader, boundary, form):
    saved = saved_records
    payload = target_record(saved, reader)
    if form in ("fallback", "truncated-only"):
        no_reply(payload, truncated=form == "truncated-only")
    elif form == "input-message":
        first = payload["messages"][0]
        first["input"] = first.pop("content")
    save_records(saved)
    assert_boundary(saved, boundary, None)


@pytest.mark.parametrize("boundary", ["startup", "preflight"])
@pytest.mark.parametrize("form", ["extra-key", "absent-null-status"])
def test_report_compatible_attempt_links_are_accepted(saved_records, boundary, form):
    saved = saved_records
    if form == "absent-null-status":
        no_reply(saved.archives[0])
        saved.archives[0].pop("status")

    def change_link(link):
        if form == "extra-key":
            link["synthetic_extra"] = True
        elif link["n"] == 1:
            link.pop("status")

    save_records(saved, change_link)
    assert_boundary(saved, boundary, None)


def add_board_household(saved, sid):
    board = nt.pilot.load_board(Path(saved.design["board"]))
    assert sid in board["scenarios"] and sid not in saved.design["draw_order"]
    return board


@pytest.mark.parametrize("boundary", ["startup", "preflight"])
def test_cheap_final_outside_draw_refuses_with_path(saved_records, boundary):
    saved = saved_records
    board = add_board_household(saved, "outside")
    payload = full_record(board, nt.CHEAP[0], saved.design["engine"], "outside")
    path = saved.folder / "outside.json"
    write_fixture_json(path, payload)
    assert_boundary(saved, boundary, path)


@pytest.mark.parametrize("boundary", ["startup", "preflight"])
def test_cheap_final_missing_predictions_refuses_with_path(saved_records, boundary):
    saved = saved_records
    payload = target_record(saved, "final")
    no_reply(payload)
    payload.pop("predictions")
    save_records(saved)
    assert_boundary(saved, boundary, saved.paths["final"])


@pytest.mark.parametrize("boundary", ["startup", "preflight"])
@pytest.mark.parametrize("reader", ["archive", "optional"])
def test_absent_predictions_without_reply_remain_accepted(
    saved_records, boundary, reader
):
    saved = saved_records
    if reader == "optional":
        board = nt.pilot.load_board(Path(saved.design["board"]))
        payload = full_record(board, "gpt-6-sol", saved.design["engine"])
        saved.finals["gpt-6-sol"] = payload
    else:
        payload = target_record(saved, "archive")
    no_reply(payload)
    payload.pop("predictions")
    save_records(saved)
    assert_boundary(
        saved, boundary, None, expected_spend=0.6 if reader == "optional" else 0.5
    )


@pytest.mark.parametrize("reader", ["final", "archive"])
@pytest.mark.parametrize("boundary", ["startup", "preflight"])
def test_saved_call_classification_failure_refuses_with_path(
    saved_records, reader, boundary
):
    saved = saved_records
    payload = target_record(saved, reader)
    payload["status"] = "complete"
    payload["turns"][0]["calls"] = [None]
    save_records(saved)
    assert_boundary(saved, boundary, saved.paths[reader])


@pytest.mark.parametrize("boundary", ["startup", "preflight"])
@pytest.mark.parametrize("number", [True, 1.0], ids=["boolean", "float"])
def test_archive_prefix_numeric_equality_remains_accepted(
    saved_records, boundary, number
):
    saved = saved_records
    second = saved.archives[1]
    second["attempts"][0]["n"] = number
    path = saved.folder / "attempts/h2-2.json"
    write_fixture_json(path, second)
    final = target_record(saved, "final")
    final["attempts"][1]["sha256"] = nt.sha256_file(path)
    write_fixture_json(saved.paths["final"], final)
    assert_boundary(saved, boundary, None)


@pytest.mark.parametrize("boundary", ["startup", "preflight"])
def test_nonobject_archive_prefix_refuses_with_path(saved_records, boundary):
    saved = saved_records
    second = saved.archives[1]
    second["attempts"][0] = None
    path = saved.folder / "attempts/h2-2.json"
    write_fixture_json(path, second)
    final = target_record(saved, "final")
    final["attempts"][1]["sha256"] = nt.sha256_file(path)
    write_fixture_json(saved.paths["final"], final)
    assert_boundary(saved, boundary, path)


@pytest.mark.parametrize("history", ["interrupted-archive", "rerunnable-final"])
def test_real_treatment_resume_preserves_attempts_and_spend(saved_records, history):
    saved = saved_records
    first = saved.paths["archive"]
    second = saved.folder / "attempts/h2-2.json"
    final = saved.paths["final"]
    prior_bytes = first.read_bytes()
    second.unlink()
    final.unlink()
    if history == "rerunnable-final":
        first.unlink()
        final.write_bytes(prior_bytes)
    board = nt.pilot.load_board(Path(saved.design["board"]))
    calls = []

    def fake_household(
        scenario, variables, tool_call, completion_fn, spend, *, profile
    ):
        calls.append((profile.name, scenario.id))
        assert variables == board["variables"][scenario.id]
        spend.add(0.1)
        return full_record(board, profile.name, saved.design["engine"], scenario.id)

    with nt.Stage(
        saved.design,
        board=None,
        models=[nt.CHEAP[0]],
        run_household=fake_household,
        completion_for=lambda profile: None,
        out=io.StringIO(),
    ) as plan:
        assert plan.spend.spent_usd == pytest.approx(0.3)
        assert plan.execute() == 0
        assert plan.spend.spent_usd == pytest.approx(0.4)
    assert calls == [(nt.CHEAP[0], "h2")]
    assert first.read_bytes() == prior_bytes
    assert not second.exists()
    payload = json.loads(final.read_text())
    assert payload["status"] == "complete"
    assert payload["attempts"] == [
        nt.entry(first, saved.archives[0], 1, nt.sha256_file(first))
    ]
    assert nt.stage_problems(saved.design) == []
