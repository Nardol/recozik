import { test, expect } from "@playwright/test";

test.describe("JobList states (mocked API)", () => {
  test.use({
    baseURL: "http://localhost:3000",
  });

  test("shows pending and failed jobs from mocked whoami/jobs", async ({
    page,
    context,
  }) => {
    await context.route("**/api/whoami", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          user_id: "demo",
          display_name: "Demo",
          roles: ["admin"],
          allowed_features: ["identify", "rename"],
        }),
      });
    });

    await context.route("**/api/jobs**", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([
          {
            job_id: "job-pending",
            status: "pending",
            created_at: "2024-01-01T12:00:00Z",
            updated_at: "2024-01-01T12:00:00Z",
            finished_at: null,
            messages: ["Queued"],
            error: null,
            result: null,
          },
          {
            job_id: "job-failed",
            status: "failed",
            created_at: "2024-01-01T12:01:00Z",
            updated_at: "2024-01-01T12:02:00Z",
            finished_at: "2024-01-01T12:02:00Z",
            messages: ["Upload received"],
            error: "Network error",
            result: {
              matches: [],
              match_source: null,
              metadata: null,
              audd_note: null,
              audd_error: null,
              fingerprint: "zzz",
              duration_seconds: 0,
            },
          },
        ]),
      });
    });

    await page.goto("/en");

    await expect(page.getByTestId("main-heading")).toBeVisible();
    const jobsHeading = page.getByRole("heading", { name: "Jobs" });
    await expect(jobsHeading).toBeVisible();

    const pendingRow = page.getByTestId("job-row-job-pending");
    const failedRow = page.getByTestId("job-row-job-failed");

    await expect(pendingRow).toBeVisible();
    await expect(pendingRow.getByTestId("job-status")).toHaveText(/pending/i);
    await expect(pendingRow.getByTestId("job-messages")).toContainText(
      "Queued",
    );

    await expect(failedRow).toBeVisible();
    await expect(failedRow.getByTestId("job-status")).toHaveText(/failed/i);
    await expect(failedRow.getByText("Error: Network error")).toBeVisible();
  });
});
