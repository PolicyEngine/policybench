"""AI-alone evaluation using LiteLLM (no tools provided)."""

import json
from pathlib import Path
import re
import time

import pandas as pd
import litellm
from litellm import completion, completion_cost

from policybench.config import MODELS, PROGRAMS
from policybench.prompts import make_no_tools_prompt
from policybench.scenarios import Scenario

MAX_RETRIES = 2
RETRY_BASE_DELAY = 2
REQUEST_TIMEOUT_SECONDS = 20
CHECKPOINT_EVERY_ROWS = 25
DEFAULT_MAX_COMPLETION_TOKENS = 64
EXTENDED_MAX_COMPLETION_TOKENS = 256
GEMINI_JSON_MAX_COMPLETION_TOKENS = 512
ANSWER_FUNCTION_NAME = "submit_answer"
ANSWER_TOOL = {
    "type": "function",
    "function": {
        "name": ANSWER_FUNCTION_NAME,
        "description": "Submit the final numeric answer for the benchmark.",
        "parameters": {
            "type": "object",
            "properties": {
                "answer": {
                    "type": "number",
                    "description": "Final numeric answer for the requested policy quantity.",
                }
            },
            "required": ["answer"],
            "additionalProperties": False,
        },
    },
}
NON_RETRYABLE_ERRORS = (
    litellm.AuthenticationError,
    litellm.BadRequestError,
    litellm.ContextWindowExceededError,
    litellm.InvalidRequestError,
    litellm.PermissionDeniedError,
    litellm.UnsupportedParamsError,
    litellm.UnprocessableEntityError,
)
MODEL_FATAL_ERRORS = (
    litellm.AuthenticationError,
    litellm.BadRequestError,
    litellm.ContextWindowExceededError,
    litellm.InvalidRequestError,
    litellm.NotFoundError,
    litellm.PermissionDeniedError,
    litellm.UnsupportedParamsError,
    litellm.UnprocessableEntityError,
)
STANDALONE_NUMBER_RE = re.compile(
    r"^\$?-?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?$"
)
ANSWER_JSON_RE = re.compile(
    r'["\']answer["\']\s*:\s*["\']?(-?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?)',
    re.IGNORECASE,
)


def _format_error(error: Exception) -> str:
    return f"{type(error).__name__}: {str(error).replace(chr(10), ' ')[:500]}"


def _should_retry(error: Exception) -> bool:
    return not isinstance(error, NON_RETRYABLE_ERRORS)


def _get_usage_value(obj, key: str):
    if obj is None:
        return None
    if isinstance(obj, dict):
        return obj.get(key)
    return getattr(obj, key, None)


def _extract_usage_metadata(response, model_id: str, messages: list[dict], content: str) -> dict:
    usage = getattr(response, "usage", None)
    prompt_tokens_details = _get_usage_value(usage, "prompt_tokens_details")
    completion_tokens_details = _get_usage_value(usage, "completion_tokens_details")
    reasoning_tokens = _get_usage_value(usage, "reasoning_tokens")
    if reasoning_tokens is None:
        reasoning_tokens = _get_usage_value(completion_tokens_details, "reasoning_tokens")

    estimated_cost_usd = _get_usage_value(usage, "cost")
    if estimated_cost_usd is None:
        try:
            estimated_cost_usd = completion_cost(
                completion_response=response,
                model=model_id,
                messages=messages,
                completion=content,
            )
        except Exception:
            estimated_cost_usd = None

    return {
        "prompt_tokens": _get_usage_value(usage, "prompt_tokens"),
        "completion_tokens": _get_usage_value(usage, "completion_tokens"),
        "total_tokens": _get_usage_value(usage, "total_tokens"),
        "reasoning_tokens": reasoning_tokens,
        "cached_prompt_tokens": _get_usage_value(prompt_tokens_details, "cached_tokens"),
        "estimated_cost_usd": estimated_cost_usd,
    }


def _parse_standalone_number(text: str) -> float | None:
    cleaned = text.strip()
    if not cleaned or not STANDALONE_NUMBER_RE.fullmatch(cleaned):
        return None
    return float(cleaned.replace(",", "").replace("$", ""))


def _completion_controls(model_id: str) -> dict:
    if model_id.startswith("gemini/"):
        return {"max_completion_tokens": GEMINI_JSON_MAX_COMPLETION_TOKENS}
    if model_id.startswith("gpt-5"):
        return {"max_completion_tokens": EXTENDED_MAX_COMPLETION_TOKENS}
    if model_id.startswith("claude-"):
        return {"max_completion_tokens": EXTENDED_MAX_COMPLETION_TOKENS}
    return {"max_completion_tokens": DEFAULT_MAX_COMPLETION_TOKENS}


def _answer_contract_for_model(model_id: str) -> str:
    if model_id.startswith("gemini/"):
        return "json"
    return "tool"


def _completion_request_kwargs(
    scenario: Scenario,
    variable: str,
    model_id: str,
) -> tuple[list[dict], dict]:
    answer_contract = _answer_contract_for_model(model_id)
    prompt = make_no_tools_prompt(
        scenario,
        variable,
        answer_contract=answer_contract,
    )
    messages = [{"role": "user", "content": prompt}]
    request_kwargs = {
        "model": model_id,
        "messages": messages,
        "caching": True,
        "timeout": REQUEST_TIMEOUT_SECONDS,
        **_completion_controls(model_id),
    }
    if answer_contract == "tool":
        request_kwargs.update(
            {
                "tools": [ANSWER_TOOL],
                "tool_choice": {
                    "type": "function",
                    "function": {"name": ANSWER_FUNCTION_NAME},
                },
            }
        )
    else:
        request_kwargs["response_format"] = {"type": "json_object"}
    return messages, request_kwargs


def extract_number(text: str) -> float | None:
    """Extract a numeric value from the answer contract or numeric-only fallback."""
    if not text:
        return None
    answer_match = ANSWER_JSON_RE.search(text)
    if answer_match is not None:
        json_value = _parse_standalone_number(answer_match.group(1))
        if json_value is not None:
            return json_value

    full_match = _parse_standalone_number(text)
    if full_match is not None:
        return full_match

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return None
    return _parse_standalone_number(lines[-1])


def _get_tool_call_function(tool_call):
    if tool_call is None:
        return None
    if isinstance(tool_call, dict):
        return tool_call.get("function")
    return getattr(tool_call, "function", None)


def _get_function_name(function_call) -> str | None:
    if function_call is None:
        return None
    if isinstance(function_call, dict):
        return function_call.get("name")
    return getattr(function_call, "name", None)


def _get_function_arguments(function_call):
    if function_call is None:
        return None
    if isinstance(function_call, dict):
        return function_call.get("arguments")
    return getattr(function_call, "arguments", None)


def _serialize_function_call(function_call) -> dict | None:
    name = _get_function_name(function_call)
    arguments = _get_function_arguments(function_call)
    if not isinstance(name, str):
        name = None
    if isinstance(arguments, (dict, list)):
        pass
    elif not isinstance(arguments, str):
        arguments = None

    if name is None and arguments is None:
        return None
    if function_call is None:
        return None
    return {
        "name": name,
        "arguments": arguments,
    }


def _serialize_response_payload(content, tool_calls=None, function_call=None) -> str | None:
    payload = {}
    if content is not None:
        payload["content"] = content

    serialized_tool_calls = []
    for tool_call in tool_calls or []:
        function = _get_tool_call_function(tool_call)
        serialized_tool_calls.append(
            {
                "name": _get_function_name(function),
                "arguments": _get_function_arguments(function),
            }
        )
    if serialized_tool_calls:
        payload["tool_calls"] = serialized_tool_calls

    serialized_function_call = _serialize_function_call(function_call)
    if serialized_function_call is not None:
        payload["function_call"] = serialized_function_call

    if not payload:
        return None
    if set(payload) == {"content"} and isinstance(content, str):
        return content
    return json.dumps(payload)


def extract_prediction(
    content: str | None,
    tool_calls=None,
    function_call=None,
) -> float | None:
    """Extract a numeric prediction from structured tool output or text fallback."""
    for tool_call in tool_calls or []:
        function = _get_tool_call_function(tool_call)
        if _get_function_name(function) != ANSWER_FUNCTION_NAME:
            continue
        arguments = _get_function_arguments(function)
        if isinstance(arguments, dict):
            arguments = json.dumps(arguments)
        elif not isinstance(arguments, str):
            arguments = None
        prediction = extract_number(arguments or "")
        if prediction is not None:
            return prediction

    if _get_function_name(function_call) == ANSWER_FUNCTION_NAME:
        arguments = _get_function_arguments(function_call)
        if isinstance(arguments, dict):
            arguments = json.dumps(arguments)
        elif not isinstance(arguments, str):
            arguments = None
        prediction = extract_number(arguments or "")
        if prediction is not None:
            return prediction

    return extract_number(content or "")


def run_single_no_tools(
    scenario: Scenario,
    variable: str,
    model_id: str,
) -> dict:
    """Run a single scenario/variable without tools.

    Returns dict with: prediction, raw_response
    """
    messages, completion_kwargs = _completion_request_kwargs(
        scenario=scenario,
        variable=variable,
        model_id=model_id,
    )

    for attempt in range(MAX_RETRIES):
        try:
            started_at = time.perf_counter()
            response = completion(**completion_kwargs)
            elapsed_seconds = time.perf_counter() - started_at
            message = response.choices[0].message
            content = getattr(message, "content", None)
            tool_calls = getattr(message, "tool_calls", None)
            function_call = getattr(message, "function_call", None)
            raw_response = _serialize_response_payload(
                content=content,
                tool_calls=tool_calls,
                function_call=function_call,
            )
            return {
                "prediction": extract_prediction(
                    content=content,
                    tool_calls=tool_calls,
                    function_call=function_call,
                ),
                "raw_response": raw_response,
                "error": None,
                "elapsed_seconds": elapsed_seconds,
                **_extract_usage_metadata(
                    response,
                    model_id,
                    messages,
                    raw_response or content,
                ),
            }
        except Exception as e:
            if attempt == MAX_RETRIES - 1 or not _should_retry(e):
                raise
            delay = RETRY_BASE_DELAY * (2**attempt)
            print(f"  Retry {attempt + 1}: {e!r:.60s}... {delay}s")
            time.sleep(delay)
    return {  # unreachable
        "prediction": None,
        "raw_response": None,
        "error": None,
        "elapsed_seconds": None,
        "prompt_tokens": None,
        "completion_tokens": None,
        "total_tokens": None,
        "reasoning_tokens": None,
        "cached_prompt_tokens": None,
        "estimated_cost_usd": None,
    }


def _load_existing_rows(output_path: str | None) -> tuple[list[dict], set[tuple[str, str, str]]]:
    if not output_path:
        return [], set()

    path = Path(output_path)
    if not path.exists() or path.stat().st_size == 0:
        return [], set()

    existing = pd.read_csv(path)
    if existing.empty:
        return [], set()

    if "error" in existing.columns:
        existing = existing[existing["error"].isna()].copy()
    if "prediction" in existing.columns:
        existing = existing[existing["prediction"].notna()].copy()
    if existing.empty:
        return [], set()

    rows = existing.to_dict("records")
    completed = {
        (row["model"], row["scenario_id"], row["variable"])
        for row in rows
    }
    return rows, completed


def run_no_tools_eval(
    scenarios: list[Scenario],
    models: dict[str, str] | None = None,
    programs: list[str] | None = None,
    output_path: str | None = None,
    run_id: str | None = None,
) -> pd.DataFrame:
    """Run the AI-alone evaluation across all models.

    If output_path is provided, saves incrementally every 100 rows.

    Returns DataFrame with columns:
        model, scenario_id, variable, prediction, raw_response, error,
        elapsed_seconds, prompt_tokens, completion_tokens, total_tokens,
        reasoning_tokens, cached_prompt_tokens, estimated_cost_usd
    """
    if models is None:
        models = MODELS
    if programs is None:
        programs = PROGRAMS

    all_rows, completed = _load_existing_rows(output_path)
    total = len(models) * len(scenarios) * len(programs)
    done = len(completed)

    for model_name, model_id in models.items():
        model_fatal = False
        for scenario in scenarios:
            for variable in programs:
                key = (model_name, scenario.id, variable)
                if key in completed:
                    continue
                try:
                    result = run_single_no_tools(scenario, variable, model_id)
                except Exception as e:
                    error = _format_error(e)
                    print(f"  ERROR [{model_name}] {scenario.id}/{variable}: {error}")
                    if isinstance(e, MODEL_FATAL_ERRORS):
                        model_fatal = True
                        print(
                            f"  Stopping {model_name} due to fatal error; "
                            "unattempted rows will be retried on resume."
                        )
                        if output_path:
                            pd.DataFrame(all_rows).to_csv(output_path, index=False)
                        break
                    result = {
                        "prediction": None,
                        "raw_response": None,
                        "error": error,
                        "elapsed_seconds": None,
                        "prompt_tokens": None,
                        "completion_tokens": None,
                        "total_tokens": None,
                        "reasoning_tokens": None,
                        "cached_prompt_tokens": None,
                        "estimated_cost_usd": None,
                    }
                all_rows.append(
                    {
                        **({"run_id": run_id} if run_id is not None else {}),
                        "model": model_name,
                        "scenario_id": scenario.id,
                        "variable": variable,
                        **result,
                    }
                )
                completed.add(key)
                done += 1
                if done % CHECKPOINT_EVERY_ROWS == 0:
                    print(f"  Progress: {done}/{total} ({done * 100 // total}%)")
                    if output_path:
                        pd.DataFrame(all_rows).to_csv(output_path, index=False)
            if model_fatal:
                break

    df = pd.DataFrame(all_rows)
    if output_path:
        df.to_csv(output_path, index=False)
    return df


def run_repeated_no_tools_eval(
    scenarios: list[Scenario],
    repeats: int,
    output_dir: str,
    models: dict[str, str] | None = None,
    programs: list[str] | None = None,
) -> pd.DataFrame:
    """Run repeated AI-alone evaluations, saving one artifact per run."""
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    frames = []
    for run_index in range(repeats):
        run_id = f"run_{run_index:03d}"
        run_output_path = output_path / f"{run_id}.csv"
        print(f"=== Starting {run_id} ===")
        frame = run_no_tools_eval(
            scenarios,
            models=models,
            programs=programs,
            output_path=str(run_output_path),
            run_id=run_id,
        )
        if "run_id" not in frame.columns:
            frame = frame.copy()
            frame["run_id"] = run_id
            frame.to_csv(run_output_path, index=False)
        frames.append(frame)

    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def load_repeated_predictions(runs_dir: str) -> pd.DataFrame:
    """Load per-run prediction CSVs from a directory into one DataFrame."""
    runs_path = Path(runs_dir)
    files = sorted(runs_path.glob("*.csv"))
    if not files:
        raise FileNotFoundError(f"No run CSVs found in {runs_path}")

    frames = []
    for path in files:
        frame = pd.read_csv(path)
        if "run_id" not in frame.columns:
            frame = frame.copy()
            frame["run_id"] = path.stem
        frames.append(frame)

    return pd.concat(frames, ignore_index=True)
