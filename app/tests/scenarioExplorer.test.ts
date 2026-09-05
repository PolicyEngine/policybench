import { describe, expect, test } from "bun:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import frozenServingConfig from "../../paper/snapshot/20260501/model_serving_config.json";
import RequestShapeNotice from "../src/components/RequestShapeNotice";

type ServingConfiguration = {
  models: Record<string, { request_shape: string }>;
};

const servingModels = (frozenServingConfig as ServingConfiguration).models;

function renderNotice(model: string, versionId = "1.1"): string {
  return renderToStaticMarkup(
    createElement(RequestShapeNotice, {
      model,
      requestShape: servingModels[model]?.request_shape,
      versionId,
      liveVersionId: "1.1",
    }),
  );
}

describe("RequestShapeNotice", () => {
  test("renders the frozen output-subset count for a chunked live-board model", () => {
    const html = renderNotice("gpt-5.5");

    expect(html).toContain(
      "GPT-5.5 answered this household over 3-output subsets of this prompt",
    );
    expect(html).toContain("serving-configuration table");
  });

  test("does not render for a whole-scenario model", () => {
    expect(renderNotice("gpt-5.6-sol")).toBe("");
  });

  test("does not apply the live serving configuration to an archived board", () => {
    expect(renderNotice("gpt-5.5", "1.0")).toBe("");
  });
});

import { DetailContent } from "../src/components/ScenarioExplorer";
import {
  findReferenceExclusion,
  predictionStatus,
} from "../src/lib/predictionStatus";
import type { ReferenceExclusion, ScenarioPrediction } from "../src/types";

const SSI_EXCLUSION: ReferenceExclusion = {
  scenarioId: "scenario_064",
  variable: "ssi",
  reasonCode: "reference_depends_on_unlisted_input",
  unlistedInput: "meets_ssi_disability_criteria",
  alternativeReading:
    "The household's 'is disabled' fact is read as meeting the SSI disability criterion.",
  frozenValue: 0,
  alternativeValue: 11928,
  engineVersion: "policyengine-us 1.755.4",
  decidedOn: "2026-09-05",
  note: "",
};

function excludedRow(overrides: Partial<ScenarioPrediction> = {}): ScenarioPrediction {
  return {
    prediction: 11928,
    error: 11928,
    groundTruth: 0,
    scored: false,
    excludedReason: "reference_depends_on_unlisted_input",
    excludedInput: "meets_ssi_disability_criteria",
    exact: 0,
    failureSource: "prompt_ambiguity",
    annotation:
      "The prompt lists 'is disabled' but never the SSI disability criterion.",
    ...overrides,
  };
}

function renderDetail(
  pred: ScenarioPrediction,
  { exclusion }: { exclusion?: ReferenceExclusion } = {
    exclusion: SSI_EXCLUSION,
  },
): string {
  return renderToStaticMarkup(
    createElement(DetailContent, {
      selectedCell: { variable: "ssi", model: "gpt-5.6-sol" },
      exclusion,
      predictions: { ssi: { "gpt-5.6-sol": pred } },
      country: "us",
      currencySymbol: "$",
      explanationsStatus: "ready",
      versionId: "1.1",
      liveVersionId: "1.1",
      onClose: () => {},
    }),
  );
}

describe("prediction detail for excluded outputs", () => {
  test("labels an excluded miss Excluded, not Off, and shows the exclusion record", () => {
    const html = renderDetail(excludedRow());

    expect(html).toContain(">Excluded<");
    expect(html).not.toContain(">Off<");
    expect(html).not.toContain(">Correct<");
    expect(html).not.toContain(">Error<");
    expect(html).toContain("None, for any model");
    expect(html).toContain("Excluded from scoring");
    expect(html).toContain("meets_ssi_disability_criteria");
    expect(html).toContain("Under that reading the reference is");
    expect(html).toContain("$11,928");
    expect(html).toContain("policyengine-us 1.755.4");
    expect(html).toContain("Prompt ambiguity");
    expect(html).toContain("never the SSI disability criterion");
  });

  test("an excluded answer matching the frozen value is not labeled Correct", () => {
    const html = renderDetail(
      excludedRow({
        prediction: 0,
        error: 0,
        exact: 100,
        failureSource: undefined,
        annotation: undefined,
      }),
    );

    expect(html).toContain(">Excluded<");
    expect(html).not.toContain(">Correct<");
    expect(html).not.toContain("Not yet reviewed");
  });

  test("falls back to the row's own exclusion fields without a release record", () => {
    const html = renderDetail(excludedRow(), {});

    expect(html).toContain(">Excluded<");
    expect(html).toContain("meets_ssi_disability_criteria");
    expect(html).not.toContain("Under that reading");
  });

  test("a scored miss keeps the Off label and its error", () => {
    const html = renderDetail({
      prediction: 11928,
      error: 11928,
      groundTruth: 0,
      scored: true,
      exact: 0,
      failureSource: "llm_error",
      annotation: "Applied SSI without the disability criterion.",
    });

    expect(html).toContain(">Off<");
    expect(html).toContain(">Error<");
    expect(html).not.toContain("Excluded from scoring");
  });
});

describe("predictionStatus", () => {
  test("excluded outranks correctness and parse state", () => {
    expect(predictionStatus(excludedRow({ exact: 100 }), 0, false)).toBe(
      "excluded",
    );
    expect(
      predictionStatus(excludedRow({ prediction: null, exact: 0 }), 0, false),
    ).toBe("excluded");
    expect(
      predictionStatus(
        { prediction: null, error: null, groundTruth: 0 },
        0,
        false,
      ),
    ).toBe("unparsed");
    expect(
      predictionStatus(
        { prediction: 0, error: 0, groundTruth: 0, exact: 100 },
        0,
        false,
      ),
    ).toBe("correct");
    expect(
      predictionStatus(
        { prediction: 5, error: 5, groundTruth: 0, exact: 0 },
        0,
        false,
      ),
    ).toBe("off");
  });

  test("findReferenceExclusion matches on scenario and variable", () => {
    expect(
      findReferenceExclusion([SSI_EXCLUSION], "scenario_064", "ssi"),
    ).toBe(SSI_EXCLUSION);
    expect(
      findReferenceExclusion([SSI_EXCLUSION], "scenario_064", "snap"),
    ).toBeUndefined();
    expect(findReferenceExclusion(undefined, "scenario_064", "ssi")).toBeUndefined();
    expect(findReferenceExclusion([SSI_EXCLUSION], null, "ssi")).toBeUndefined();
  });
});
