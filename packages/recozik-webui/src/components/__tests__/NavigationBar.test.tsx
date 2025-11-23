import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, screen } from "@testing-library/react";
import { NavigationBar } from "../NavigationBar";
import { renderWithProviders } from "../../tests/test-utils";
import type { WhoAmI } from "../../lib/api";

const push = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({
    push,
    replace: vi.fn(),
    prefetch: vi.fn(),
    refresh: vi.fn(),
    back: vi.fn(),
    forward: vi.fn(),
  }),
  usePathname: () => "/en",
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock("../../lib/api", () => ({
  fetchWhoami: vi.fn().mockResolvedValue({
    user_id: "demo",
    display_name: "Demo User",
    roles: ["admin"],
    allowed_features: ["identify", "rename"],
  }),
}));

const mockProfile: WhoAmI = {
  user_id: "demo",
  display_name: "Demo User",
  roles: ["admin"],
  allowed_features: ["identify", "rename"],
};

describe("NavigationBar", () => {
  beforeEach(() => {
    push.mockClear();
  });

  it("does not render when no profile is available", () => {
    const { container } = renderWithProviders(<NavigationBar />);
    expect(container.firstChild).toBeNull();
  });

  it("renders navigation links when a profile is present", () => {
    renderWithProviders(<NavigationBar />, {
      profile: mockProfile,
    });

    expect(
      screen.getByRole("navigation", { name: "Main navigation" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Upload" })).toHaveAttribute(
      "href",
      "#upload-section",
    );
    expect(screen.getByRole("link", { name: "Jobs" })).toHaveAttribute(
      "href",
      "#jobs-section",
    );
    expect(screen.getByRole("button", { name: "Disconnect" })).toHaveClass(
      "secondary",
    );
  });

  it("submits logout action when Disconnect is clicked", () => {
    renderWithProviders(<NavigationBar />, {
      profile: mockProfile,
    });

    const form = screen.getByTestId("logout-form") as HTMLFormElement;
    const submitSpy = vi.fn();
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      submitSpy();
    });

    fireEvent.click(screen.getByRole("button", { name: "Disconnect" }));

    expect(submitSpy).toHaveBeenCalled();
  });

  it("navigates to anchors when links clicked", () => {
    renderWithProviders(<NavigationBar />, {
      profile: mockProfile,
    });

    fireEvent.click(screen.getByRole("link", { name: "Jobs" }));
    fireEvent.click(screen.getByRole("link", { name: "Upload" }));

    expect(screen.getByRole("link", { name: "Jobs" })).toHaveAttribute(
      "href",
      "#jobs-section",
    );
    expect(screen.getByRole("link", { name: "Upload" })).toHaveAttribute(
      "href",
      "#upload-section",
    );
  });
});
