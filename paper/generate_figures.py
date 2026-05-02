"""Generate paper-ready derived artifacts from the current dashboard data."""

from __future__ import annotations

import html
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
APP_DATA = ROOT / "app" / "src" / "data.json"
FIGURES_DIR = ROOT / "paper" / "figures"


def _escape(value: object) -> str:
    return html.escape(str(value), quote=True)


def _write_svg_and_png(filename: str, svg: str) -> dict[str, str]:
    svg_path = FIGURES_DIR / f"{filename}.svg"
    png_path = FIGURES_DIR / f"{filename}.png"
    svg_path.write_text(svg, encoding="utf-8")

    converter = shutil.which("rsvg-convert")
    if converter:
        subprocess.run(
            [converter, "-w", "1800", str(svg_path), "-o", str(png_path)],
            check=True,
        )
        return {
            "svg": str(svg_path.relative_to(ROOT)),
            "png": str(png_path.relative_to(ROOT)),
        }
    return {"svg": str(svg_path.relative_to(ROOT))}


def _model_label(model_id: str) -> str:
    labels = {
        "claude-haiku-4.5": "Claude Haiku 4.5",
        "claude-opus-4.7": "Claude Opus 4.7",
        "claude-sonnet-4.6": "Claude Sonnet 4.6",
        "gemini-3-flash-preview": "Gemini 3 Flash",
        "gemini-3.1-flash-lite-preview": "Gemini 3.1 Flash-Lite",
        "gemini-3.1-pro-preview": "Gemini 3.1 Pro",
        "gpt-5.4-mini": "GPT-5.4 mini",
        "gpt-5.4-nano": "GPT-5.4 nano",
        "gpt-5.5": "GPT-5.5",
        "grok-4.1-fast": "Grok 4.1 fast",
        "grok-4.20": "Grok 4.20",
        "grok-4.3": "Grok 4.3",
    }
    return labels.get(model_id, model_id)


def _variable_label(variable_id: str) -> str:
    labels = {
        "federal_income_tax_before_refundable_credits": "Fed. income tax",
        "federal_refundable_credits": "Fed. refundable credits",
        "state_income_tax_before_refundable_credits": "State income tax",
        "state_refundable_credits": "State refundable credits",
        "local_income_tax": "Local income tax",
        "payroll_tax": "Payroll tax",
        "self_employment_tax": "Self-employment tax",
        "snap": "SNAP",
        "ssi": "SSI",
        "tanf": "TANF",
        "premium_tax_credit": "Premium tax credit",
        "free_school_meals_eligible": "Free school meals",
        "reduced_price_school_meals_eligible": "Reduced-price meals",
        "person_wic_eligible": "WIC",
        "person_medicaid_eligible": "Medicaid",
        "person_chip_eligible": "CHIP",
        "person_medicare_eligible": "Medicare",
        "person_head_start_eligible": "Head Start",
        "person_early_head_start_eligible": "Early Head Start",
        "income_tax": "Income Tax",
        "national_insurance": "National Insurance",
        "capital_gains_tax": "Capital Gains Tax",
        "child_benefit": "Child Benefit",
        "universal_credit": "Universal Credit",
        "pension_credit": "Pension Credit",
        "pip": "PIP",
    }
    return labels.get(variable_id, variable_id.replace("_", " ").title())


def _global_leaderboard_svg(payload: dict[str, Any]) -> str:
    models = payload.get("global", {}).get("modelStats", [])[:10]
    width = 900
    height = 120 + 44 * len(models)
    left = 255
    right = 50
    chart_width = width - left - right
    max_score = max((float(row.get("score", 0)) for row in models), default=100)
    max_score = max(100.0, max_score)

    rows = [
        "<svg xmlns='http://www.w3.org/2000/svg' "
        f"width='{width}' height='{height}' viewBox='0 0 {width} {height}'>",
        "<rect width='100%' height='100%' fill='#f7fafc'/>",
        (
            "<text x='32' y='42' font-family='Arial, sans-serif' "
            "font-size='24' font-weight='700' fill='#10231f'>"
            "Global shared-model leaderboard</text>"
        ),
        (
            "<text x='32' y='68' font-family='Arial, sans-serif' "
            "font-size='13' fill='#52645f'>Equal-country score, frozen "
            "2026-05-01 snapshot</text>"
        ),
    ]
    for index, row in enumerate(models):
        score = float(row.get("score", 0))
        y = 100 + index * 44
        bar_width = chart_width * score / max_score
        rows.extend(
            [
                (
                    f"<text x='32' y='{y + 22}' font-family='Arial, sans-serif' "
                    f"font-size='14' fill='#10231f'>"
                    f"{_escape(_model_label(row['model']))}</text>"
                ),
                (
                    f"<rect x='{left}' y='{y}' width='{chart_width}' height='24' "
                    "rx='12' fill='#dcebe5'/>"
                ),
                (
                    f"<rect x='{left}' y='{y}' width='{bar_width:.1f}' height='24' "
                    "rx='12' fill='#2f8f6b'/>"
                ),
                (
                    f"<text x='{left + chart_width + 12}' y='{y + 18}' "
                    "font-family='Arial, sans-serif' font-size='13' "
                    f"fill='#10231f'>{score:.1f}</text>"
                ),
            ]
        )
    rows.append("</svg>")
    return "\n".join(rows)


def _positive_zero_scatter_svg(payload: dict[str, Any]) -> str:
    points = []
    for country, country_payload in payload.get("countries", {}).items():
        programs = country_payload.get("failureModes", {}).get("programs", [])
        for row in programs:
            x = row.get("zeroCasePct")
            y = row.get("positiveCasePct")
            if x is None or y is None:
                continue
            points.append(
                {
                    "country": country,
                    "variable": row.get("variable"),
                    "x": float(x),
                    "y": float(y),
                }
            )

    width = 900
    height = 610
    left = 82
    top = 90
    chart_width = 690
    chart_height = 410
    rows = [
        "<svg xmlns='http://www.w3.org/2000/svg' "
        f"width='{width}' height='{height}' viewBox='0 0 {width} {height}'>",
        "<rect width='100%' height='100%' fill='#f7fafc'/>",
        (
            "<text x='32' y='42' font-family='Arial, sans-serif' "
            "font-size='24' font-weight='700' fill='#10231f'>"
            "Performance on zero and positive cases</text>"
        ),
        (
            "<text x='32' y='68' font-family='Arial, sans-serif' "
            "font-size='13' fill='#52645f'>Each dot is one output group. "
            "Binary outputs use classification accuracy.</text>"
        ),
        (
            f"<rect x='{left}' y='{top}' width='{chart_width}' "
            f"height='{chart_height}' fill='#ffffff' stroke='#c9d8d2'/>"
        ),
    ]
    for tick in range(0, 101, 25):
        x = left + chart_width * tick / 100
        y = top + chart_height - chart_height * tick / 100
        rows.extend(
            [
                f"<line x1='{x:.1f}' y1='{top}' x2='{x:.1f}' "
                f"y2='{top + chart_height}' stroke='#edf3f0'/>",
                f"<line x1='{left}' y1='{y:.1f}' x2='{left + chart_width}' "
                f"y2='{y:.1f}' stroke='#edf3f0'/>",
                (
                    f"<text x='{x:.1f}' y='{top + chart_height + 24}' "
                    "font-family='Arial, sans-serif' font-size='12' "
                    f"text-anchor='middle' fill='#52645f'>{tick}</text>"
                ),
                (
                    f"<text x='{left - 14}' y='{y + 4:.1f}' "
                    "font-family='Arial, sans-serif' font-size='12' "
                    f"text-anchor='end' fill='#52645f'>{tick}</text>"
                ),
            ]
        )
    rows.append(
        f"<line x1='{left}' y1='{top + chart_height}' "
        f"x2='{left + chart_width}' y2='{top}' stroke='#9cb6ad' "
        "stroke-dasharray='5 5'/>"
    )

    colors = {"us": "#2f8f6b", "uk": "#375a7f"}
    for point in points:
        x = left + chart_width * point["x"] / 100
        y = top + chart_height - chart_height * point["y"] / 100
        color = colors.get(point["country"], "#6b7280")
        rows.append(
            f"<circle cx='{x:.1f}' cy='{y:.1f}' r='5.5' fill='{color}' "
            "fill-opacity='0.82'>"
            f"<title>{_escape(point['country'].upper())}: "
            f"{_escape(_variable_label(point['variable']))} "
            f"zero={point['x']:.1f}, positive={point['y']:.1f}</title></circle>"
        )

    rows.extend(
        [
            (
                f"<text x='{left + chart_width / 2}' y='{height - 44}' "
                "font-family='Arial, sans-serif' font-size='14' "
                "text-anchor='middle' fill='#10231f'>"
                "Zero-reference cases correct (%)</text>"
            ),
            (
                f"<text x='24' y='{top + chart_height / 2}' "
                "font-family='Arial, sans-serif' font-size='14' "
                "text-anchor='middle' fill='#10231f' "
                "transform='rotate(-90 24 "
                f"{top + chart_height / 2})'>"
                "Positive-reference cases correct (%)</text>"
            ),
            (
                "<circle cx='805' cy='120' r='6' fill='#2f8f6b'/>"
                "<text x='820' y='124' font-family='Arial, sans-serif' "
                "font-size='13' fill='#10231f'>US</text>"
            ),
            (
                "<circle cx='805' cy='148' r='6' fill='#375a7f'/>"
                "<text x='820' y='152' font-family='Arial, sans-serif' "
                "font-size='13' fill='#10231f'>UK</text>"
            ),
            "</svg>",
        ]
    )
    return "\n".join(rows)


def load_dashboard_summary(path: Path) -> dict[str, object] | None:
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    countries = payload.get("countries", {})
    return {
        "path": str(path.relative_to(ROOT)),
        "countries": sorted(countries),
        "global_models": len(payload.get("global", {}).get("modelStats", [])),
        "country_models": {
            country: len(country_payload.get("modelStats", []))
            for country, country_payload in countries.items()
        },
        "country_outputs": {
            country: len(country_payload.get("programStats", []))
            for country, country_payload in countries.items()
        },
    }


def main() -> None:
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    payload = json.loads(APP_DATA.read_text(encoding="utf-8"))

    generated_figures = {
        "global_leaderboard": _write_svg_and_png(
            "global_leaderboard",
            _global_leaderboard_svg(payload),
        ),
        "positive_zero_scatter": _write_svg_and_png(
            "positive_zero_scatter",
            _positive_zero_scatter_svg(payload),
        ),
    }

    manifest = {
        "dashboard": load_dashboard_summary(APP_DATA),
        "figures": generated_figures,
    }

    output_path = FIGURES_DIR / "manifest.json"
    output_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Wrote {output_path}")


if __name__ == "__main__":
    main()
