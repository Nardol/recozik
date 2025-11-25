import { describe, expect, it, beforeEach, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { LoginForm } from "../LoginForm";
import { I18nProvider } from "../../i18n/I18nProvider";
import { getApiBase } from "../../lib/api";

const refreshProfile = vi.fn();
const replace = vi.fn();
const refresh = vi.fn();

vi.mock("../TokenProvider", () => ({
  useToken: () => ({
    refreshProfile,
    token: null,
    profile: null,
    status: "idle",
  }),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({
    replace,
    refresh,
  }),
}));

function renderForm() {
  return render(
    <I18nProvider locale="en">
      <LoginForm />
    </I18nProvider>,
  );
}

describe("LoginForm", () => {
  beforeEach(() => {
    refreshProfile.mockReset();
    replace.mockReset();
    refresh.mockReset();
    global.fetch = vi.fn();
  });

  it("posts credentials and refreshes profile on success", async () => {
    (global.fetch as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(
      new Response("{}", { status: 200 }),
    );

    renderForm();

    fireEvent.change(screen.getByTestId("login-username"), {
      target: { value: "demo" },
    });
    fireEvent.change(screen.getByTestId("login-password"), {
      target: { value: "secret" },
    });
    fireEvent.click(screen.getByTestId("login-submit"));

    await waitFor(() => expect(refreshProfile).toHaveBeenCalled());
    expect(global.fetch).toHaveBeenCalledWith(
      `${getApiBase().replace(/\/$/, "")}/auth/login`,
      expect.objectContaining({
        method: "POST",
        credentials: "include",
      }),
    );
    expect(replace).toHaveBeenCalledWith("/en");
    expect(refresh).toHaveBeenCalled();
  });

  it("shows an error when credentials are missing", async () => {
    renderForm();

    fireEvent.click(screen.getByTestId("login-submit"));

    expect(
      await screen.findByText("Please provide both username and password."),
    ).toBeInTheDocument();
  });

  it("surfaced backend error when login fails", async () => {
    (global.fetch as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(
      new Response("Invalid credentials", { status: 401 }),
    );

    renderForm();

    fireEvent.change(screen.getByTestId("login-username"), {
      target: { value: "demo" },
    });
    fireEvent.change(screen.getByTestId("login-password"), {
      target: { value: "wrong" },
    });
    fireEvent.click(screen.getByTestId("login-submit"));

    await screen.findByText("Invalid credentials");
  });
});
