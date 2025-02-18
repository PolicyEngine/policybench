import re
import sys
from typing import Optional, Dict, Any, List, Tuple, Union

from edsl import Agent, QuestionFreeText, Survey, Model


def ensure_string(obj: Union[str, bytes, object]) -> str:
    """
    Convert arbitrary data to a UTF-8 decoded string if possible,
    or a fallback using str() if not.
    """
    if isinstance(obj, str):
        return obj
    elif isinstance(obj, bytes):
        # decode bytes
        return obj.decode("utf-8", errors="replace")
    else:
        # fallback for weird types (bytearray, etc.)
        # optional: debug logging
        print(
            f"[DEBUG] ensure_string() got type={type(obj)}, repr={obj!r}",
            file=sys.stderr,
        )
        return str(obj)


def parse_llm_answer(obj: Union[str, bytes, object]) -> Tuple[Optional[float], str]:
    """
    Convert `obj` to a string, then parse numeric substrings, ignoring "2025".
    Returns (parsed_value, final_text):
      - parsed_value: the max float found or None
      - final_text: the final string used (for debugging, CSV logs).
    """
    text = ensure_string(obj)

    # Now text is definitely a str, so re.findall is safe
    matches = re.findall(r"([\d,\.]+)", text)
    candidates = []
    for m in matches:
        m_clean = m.replace(",", "")
        if m_clean == "2025":
            continue
        try:
            val = float(m_clean)
            candidates.append(val)
        except ValueError:
            pass

    if not candidates:
        return None, text
    return max(candidates), text


def build_survey(program: str, scenario: Dict[str, Any], year: int) -> Survey:
    adult_count = sum("adult" in pid.lower() for pid in scenario["people"].keys())
    child_count = sum("child" in pid.lower() for pid in scenario["people"].keys())
    hh_key = list(scenario["households"].keys())[0]
    state_2025 = scenario["households"][hh_key]["state_name"].get(str(year), "??")

    question_text = (
        f"This household has {adult_count} adult(s) and {child_count} child(ren). "
        f"They live in {state_2025}. We want to estimate '{program}' in tax year {year}. "
        "Provide a single numeric answer (no extra text)."
    )
    question = QuestionFreeText(
        question_name="llm_program_estimate",
        question_text=question_text,
    )
    return Survey(questions=[question])


def estimate_program_value(
    program: str,
    scenario: Dict[str, Any],
    model_name: str = "gpt-4o",
    year: int = 2025,
    n_runs: int = 1,
) -> List[Tuple[Optional[float], str]]:
    """
    Runs an EDSL survey n_runs times, returns a list of (parsed_float, raw_text).
    """
    agent = Agent(
        traits={
            "persona": (
                "You are an expert in U.S. tax and benefit laws. "
                "Provide only a numeric answer in dollars."
            )
        }
    )

    survey = build_survey(program, scenario, year)
    model = Model(model_name, temperature=1.0)

    results_list = []
    for _ in range(n_runs):
        edsl_results = survey.by(agent).by(model).run()
        raw_obj = (
            edsl_results.select("answer.llm_program_estimate")
            .to_pandas()["answer.llm_program_estimate"]
            .iloc[0]
        )
        parsed_val, final_text = parse_llm_answer(raw_obj)
        results_list.append((parsed_val, final_text))

    return results_list
