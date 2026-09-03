import { describe, expect, test } from "bun:test";

import { loadLatestVersion } from "../src/lib/versionSelection";

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

describe("dataset load ordering", () => {
  test("an older load cannot overwrite the final selected version", async () => {
    const liveDashboard = { name: "live" };
    const archivedDashboard = { name: "archive" };
    const archiveLoad = deferred<typeof archivedDashboard>();
    const liveLoad = deferred<typeof liveDashboard>();
    const sequence = { current: 0 };
    let state = { versionId: "1.1", dashboard: liveDashboard };

    const select = (
      versionId: string,
      pending: Promise<typeof liveDashboard>,
    ) => {
      state = { ...state, versionId };
      loadLatestVersion(
        sequence,
        () => pending,
        (dashboard) => {
          state = { versionId, dashboard };
        },
        () => {
          state = { versionId: "1.1", dashboard: liveDashboard };
        },
      );
    };

    select("1.0", archiveLoad.promise);
    select("1.1", liveLoad.promise);
    liveLoad.resolve(liveDashboard);
    await flushPromises();
    archiveLoad.resolve(archivedDashboard);
    await flushPromises();

    expect(state).toEqual({ versionId: "1.1", dashboard: liveDashboard });
  });

  test("an older failed load cannot roll back a newer selection", async () => {
    const liveDashboard = { name: "live" };
    const archiveLoad = deferred<typeof liveDashboard>();
    const liveLoad = deferred<typeof liveDashboard>();
    const sequence = { current: 0 };
    let versionId = "1.1";
    let dashboard = liveDashboard;

    const select = (id: string, pending: Promise<typeof liveDashboard>) => {
      versionId = id;
      loadLatestVersion(
        sequence,
        () => pending,
        (loaded) => {
          dashboard = loaded;
        },
        () => {
          versionId = "1.1";
          dashboard = liveDashboard;
        },
      );
    };

    select("1.0", archiveLoad.promise);
    select("1.1", liveLoad.promise);
    liveLoad.resolve(liveDashboard);
    await flushPromises();
    archiveLoad.reject(new Error("archive failed"));
    await flushPromises();

    expect(versionId).toBe("1.1");
    expect(dashboard).toBe(liveDashboard);
  });
});
