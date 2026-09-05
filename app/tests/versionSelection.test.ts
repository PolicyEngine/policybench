import { describe, expect, test } from "bun:test";

import {
  datasetSelectionReducer,
  loadLatestVersion,
  urlForDatasetVersion,
} from "../src/lib/versionSelection";

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (error: unknown) => void;
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
}

const flushPromises = () => new Promise((resolve) => setTimeout(resolve, 0));

type Dashboard = { name: string };
type VisibleState = {
  versionId: string;
  pendingVersionId: string | null;
  dashboard: Dashboard;
  url: string;
};

function selectionHarness(initialState: VisibleState) {
  const sequence = { current: 0 };
  const mounted = { current: true };
  let state = initialState;
  const renders: VisibleState[] = [state];

  const update = (next: VisibleState) => {
    state = next;
    renders.push(state);
  };

  const select = (versionId: string, pending: Promise<Dashboard>) => {
    update({
      ...datasetSelectionReducer(state, { type: "start", versionId }),
      url: state.url,
    });
    loadLatestVersion(
      sequence,
      mounted,
      () => pending,
      (dashboard) => {
        const selected = datasetSelectionReducer(state, {
          type: "loaded",
          versionId,
          dashboard,
        });
        update({
          ...selected,
          url: urlForDatasetVersion(state.url, versionId, "1.1"),
        });
      },
      () => {
        const activeVersionId = state.versionId;
        update({
          ...datasetSelectionReducer(state, { type: "clear-pending" }),
          url: urlForDatasetVersion(state.url, activeVersionId, "1.1"),
        });
      },
    );
  };

  return {
    select,
    state: () => state,
    renders,
  };
}

describe("dataset load ordering", () => {
  test("keeps the visible version, dashboard, and URL unchanged until resolution", async () => {
    const liveDashboard = { name: "live" };
    const archivedDashboard = { name: "archive" };
    const archiveLoad = deferred<Dashboard>();
    const initial = {
      versionId: "1.1",
      pendingVersionId: null,
      dashboard: liveDashboard,
      url: "https://policybench.org/?country=us",
    };
    const harness = selectionHarness(initial);

    harness.select("1.0", archiveLoad.promise);

    expect(harness.state()).toEqual({
      ...initial,
      pendingVersionId: "1.0",
    });

    archiveLoad.resolve(archivedDashboard);
    await flushPromises();

    expect(harness.state()).toEqual({
      versionId: "1.0",
      pendingVersionId: null,
      dashboard: archivedDashboard,
      url: "https://policybench.org/?country=us&dataset=1.0",
    });
    expect(harness.renders).toHaveLength(3);
  });

  test("an older load cannot overwrite the final selected version", async () => {
    const previousDashboard = { name: "previous" };
    const liveDashboard = { name: "live" };
    const archivedDashboard = { name: "archive" };
    const archiveLoad = deferred<Dashboard>();
    const liveLoad = deferred<Dashboard>();
    const harness = selectionHarness({
      versionId: "previous",
      pendingVersionId: null,
      dashboard: previousDashboard,
      url: "https://policybench.org/?country=us&dataset=previous",
    });

    harness.select("1.0", archiveLoad.promise);
    harness.select("1.1", liveLoad.promise);
    liveLoad.resolve(liveDashboard);
    await flushPromises();
    archiveLoad.resolve(archivedDashboard);
    await flushPromises();

    expect(harness.state()).toEqual({
      versionId: "1.1",
      pendingVersionId: null,
      dashboard: liveDashboard,
      url: "https://policybench.org/?country=us",
    });
  });

  test("an older failed load cannot roll back a newer selection", async () => {
    const previousDashboard = { name: "previous" };
    const liveDashboard = { name: "live" };
    const archiveLoad = deferred<Dashboard>();
    const liveLoad = deferred<Dashboard>();
    const harness = selectionHarness({
      versionId: "previous",
      pendingVersionId: null,
      dashboard: previousDashboard,
      url: "https://policybench.org/?country=us&dataset=previous",
    });

    harness.select("1.0", archiveLoad.promise);
    harness.select("1.1", liveLoad.promise);
    liveLoad.resolve(liveDashboard);
    await flushPromises();
    archiveLoad.reject(new Error("archive failed"));
    await flushPromises();

    expect(harness.state()).toEqual({
      versionId: "1.1",
      pendingVersionId: null,
      dashboard: liveDashboard,
      url: "https://policybench.org/?country=us",
    });
  });

  test("a failed latest load clears pending state without changing the selection", async () => {
    const liveDashboard = { name: "live" };
    const archiveLoad = deferred<Dashboard>();
    const initial = {
      versionId: "1.1",
      pendingVersionId: null,
      dashboard: liveDashboard,
      url: "https://policybench.org/?country=us",
    };
    const harness = selectionHarness(initial);

    harness.select("1.0", archiveLoad.promise);
    archiveLoad.reject(new Error("archive failed"));
    await flushPromises();

    expect(harness.state()).toEqual(initial);
  });

  test("a failed initial URL load removes its stale dataset query", async () => {
    const liveDashboard = { name: "live" };
    const archiveLoad = deferred<Dashboard>();
    const harness = selectionHarness({
      versionId: "1.1",
      pendingVersionId: null,
      dashboard: liveDashboard,
      url: "https://policybench.org/?country=us&dataset=1.0",
    });

    harness.select("1.0", archiveLoad.promise);
    archiveLoad.reject(new Error("archive failed"));
    await flushPromises();

    expect(harness.state()).toEqual({
      versionId: "1.1",
      pendingVersionId: null,
      dashboard: liveDashboard,
      url: "https://policybench.org/?country=us",
    });
  });

  test("a pending load that resolves after unmount changes no state or URL", async () => {
    const sequence = { current: 0 };
    const mounted = { current: true };
    const pending = deferred<Dashboard>();
    let dispatches = 0;
    let url = "https://policybench.org/?country=us";

    loadLatestVersion(
      sequence,
      mounted,
      () => pending.promise,
      () => {
        dispatches += 1;
        url = "https://policybench.org/?country=us&dataset=1.0";
      },
      () => {
        dispatches += 1;
        url = "https://policybench.org/?country=us&dataset=failed";
      },
    );
    mounted.current = false;
    pending.resolve({ name: "archive" });
    await flushPromises();

    expect(dispatches).toBe(0);
    expect(url).toBe("https://policybench.org/?country=us");
  });

  test("a pending load that rejects after unmount changes no state or URL", async () => {
    const sequence = { current: 0 };
    const mounted = { current: true };
    const pending = deferred<Dashboard>();
    let dispatches = 0;
    let url = "https://policybench.org/?country=us";

    loadLatestVersion(
      sequence,
      mounted,
      () => pending.promise,
      () => {
        dispatches += 1;
        url = "https://policybench.org/?country=us&dataset=1.0";
      },
      () => {
        dispatches += 1;
        url = "https://policybench.org/?country=us&dataset=failed";
      },
    );
    mounted.current = false;
    pending.reject(new Error("unmounted"));
    await flushPromises();

    expect(dispatches).toBe(0);
    expect(url).toBe("https://policybench.org/?country=us");
  });
});
