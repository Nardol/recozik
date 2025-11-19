import { describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import { JobList } from "../JobList";
import type { JobDetail } from "../../lib/api";
import { renderWithProviders } from "../../tests/test-utils";

describe("JobList", () => {
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
});
