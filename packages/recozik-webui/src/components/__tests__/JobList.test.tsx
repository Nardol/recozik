import { beforeEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import { JobList } from "../JobList";
import type { JobDetail } from "../../lib/api";
import { renderWithProviders } from "../../tests/test-utils";

type SocketEvent = "message" | "close" | "error";
type Listener = (event: MessageEvent) => void;

const mockSockets: Array<{
  emit: (type: SocketEvent, event: MessageEvent) => void;
}> = [];

vi.mock("../../lib/job-websocket", () => {
  return {
    createJobWebSocket: vi.fn(() => {
      const listeners: Record<SocketEvent, Listener[]> = {
        message: [],
        close: [],
        error: [],
      };
      const socket = {
        addEventListener: (type: SocketEvent, cb: Listener) => {
          listeners[type]?.push(cb);
        },
        close: vi.fn(),
        emit: (type: SocketEvent, event: MessageEvent) => {
          listeners[type]?.forEach((cb) => cb(event));
        },
      };
      mockSockets.push(socket);
      return socket;
    }),
  };
});

describe("JobList", () => {
  beforeEach(() => {
    mockSockets.length = 0;
    vi.clearAllMocks();
  });

  it("shows the empty state when no jobs are provided", () => {
    renderWithProviders(
      <JobList jobs={[]} onUpdate={vi.fn()} sectionId="jobs-section" />,
    );

    expect(screen.getByRole("heading", { name: "Jobs" })).toBeInTheDocument();
    expect(
      screen.getByText(
        "No identify jobs yet. Submit an upload to see live results.",
      ),
    ).toBeInTheDocument();
  });

  it("renders a completed job summary with metadata and score", () => {
    const completedJob: JobDetail = {
      job_id: "job-123",
      status: "completed",
      created_at: "2024-01-01T12:00:00Z",
      updated_at: "2024-01-01T12:05:00Z",
      finished_at: "2024-01-01T12:05:00Z",
      messages: ["Upload received", "Processed by AcoustID"],
      error: null,
      result: {
        matches: [
          {
            score: 0.872,
            title: "Harder, Better, Faster, Stronger",
            artist: "Daft Punk",
            release_group_title: "Discovery",
          },
        ],
        match_source: "acoustid",
        metadata: {
          title: "Harder, Better, Faster, Stronger",
          artist: "Daft Punk",
          album: "Discovery",
        },
        audd_note: "Enterprise fallback",
        audd_error: null,
        fingerprint: "abcdef",
        duration_seconds: 220,
      },
    };

    renderWithProviders(
      <JobList
        jobs={[completedJob]}
        onUpdate={vi.fn()}
        sectionId="jobs-section"
      />,
    );

    expect(
      screen.getByText("Daft Punk — Harder, Better, Faster, Stronger"),
    ).toBeInTheDocument();
    expect(screen.getByText("Discovery")).toBeInTheDocument();
    expect(screen.getByText(/Score: 87%/)).toBeInTheDocument();
    expect(
      screen.getByText(
        "Metadata: Harder, Better, Faster, Stronger · Daft Punk · Discovery",
      ),
    ).toBeInTheDocument();
    expect(screen.getByText(/Source: acoustid/)).toBeInTheDocument();
    expect(screen.getByText("Note: Enterprise fallback")).toBeInTheDocument();
    expect(screen.getByText("View JSON")).toBeInTheDocument();
  });

  it("renders running and failed jobs with appropriate summaries", () => {
    const runningJob: JobDetail = {
      job_id: "job-999",
      status: "running",
      created_at: "2024-01-02T12:00:00Z",
      updated_at: "2024-01-02T12:01:00Z",
      finished_at: null,
      messages: [],
      error: null,
      result: null,
    };
    const failedJob: JobDetail = {
      job_id: "job-500",
      status: "failed",
      created_at: "2024-01-03T12:00:00Z",
      updated_at: "2024-01-03T12:02:00Z",
      finished_at: "2024-01-03T12:02:00Z",
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
    };

    renderWithProviders(
      <JobList
        jobs={[runningJob, failedJob]}
        onUpdate={vi.fn()}
        sectionId="jobs-section"
      />,
    );

    expect(screen.getByTestId("job-row-job-999")).toBeInTheDocument();
    expect(screen.getByTestId("job-row-job-500")).toBeInTheDocument();
    expect(
      screen.getAllByTestId("job-status").map((el) => el.textContent),
    ).toContain("Running");
    expect(screen.getByText("Failed")).toBeInTheDocument();
    expect(screen.getByText("Error: Network error")).toBeInTheDocument();
  });

  it("renders queued jobs without JSON details", () => {
    const queuedJob: JobDetail = {
      job_id: "job-queued",
      status: "queued",
      created_at: "2024-01-04T12:00:00Z",
      updated_at: "2024-01-04T12:00:00Z",
      finished_at: null,
      messages: [],
      error: null,
      result: null,
    };

    renderWithProviders(
      <JobList
        jobs={[queuedJob]}
        onUpdate={vi.fn()}
        sectionId="jobs-section"
      />,
    );

    const statuses = screen
      .getAllByTestId("job-status")
      .map((el) => el.textContent);
    expect(statuses).toContain("Queued");
    expect(screen.queryByText("View JSON")).not.toBeInTheDocument();
  });

  it("shows no-match summary and source when matches are empty", () => {
    const noMatchJob: JobDetail = {
      job_id: "job-nomatch",
      status: "completed",
      created_at: "2024-01-05T12:00:00Z",
      updated_at: "2024-01-05T12:05:00Z",
      finished_at: "2024-01-05T12:05:00Z",
      messages: [],
      error: null,
      result: {
        matches: [],
        match_source: "audd",
        metadata: null,
        audd_note: null,
        audd_error: null,
        fingerprint: "abc",
        duration_seconds: 10,
      },
    };

    renderWithProviders(
      <JobList
        jobs={[noMatchJob]}
        onUpdate={vi.fn()}
        sectionId="jobs-section"
      />,
    );

    expect(screen.getByText("No matches returned.")).toBeInTheDocument();
    expect(screen.getByText("Source: audd")).toBeInTheDocument();
  });

  it("invokes onUpdate when a WebSocket job update arrives", async () => {
    const runningJob: JobDetail = {
      job_id: "job-live",
      status: "running",
      created_at: "2024-01-06T12:00:00Z",
      updated_at: "2024-01-06T12:00:00Z",
      finished_at: null,
      messages: [],
      error: null,
      result: null,
    };
    const onUpdate = vi.fn();

    renderWithProviders(
      <JobList jobs={[runningJob]} onUpdate={onUpdate} sectionId="jobs" />,
    );

    await waitFor(() => expect(mockSockets.length).toBeGreaterThan(0));

    const updated: JobDetail = {
      ...runningJob,
      status: "completed",
      updated_at: "2024-01-06T12:01:00Z",
      finished_at: "2024-01-06T12:01:00Z",
      result: {
        matches: [],
        match_source: null,
        metadata: null,
        audd_note: null,
        audd_error: null,
        fingerprint: "abc",
        duration_seconds: 10,
      },
    };

    const message = new MessageEvent("message", {
      data: JSON.stringify({ job: updated }),
    });
    mockSockets[0]?.emit("message", message);

    expect(onUpdate).toHaveBeenCalledWith(updated);
  });
});
