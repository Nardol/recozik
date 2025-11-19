import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { LanguageSwitcher } from "../LanguageSwitcher";
import { I18nProvider } from "../../i18n/I18nProvider";

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
  usePathname: () => "/en/dashboard/jobs",
  useSearchParams: () => new URLSearchParams(),
}));

describe("LanguageSwitcher", () => {
  beforeEach(() => {
    push.mockClear();
  });

  it("shows the current locale and navigates to the selected one", () => {
    render(
      <I18nProvider locale="en">
        <LanguageSwitcher />
      </I18nProvider>,
    );

    const select = screen.getByRole("combobox", { name: "Interface language" });
    expect(select).toHaveValue("en");

    const options = screen.getAllByRole("option");
    expect(options.map((o) => o.getAttribute("value"))).toEqual(["en", "fr"]);

    fireEvent.change(select, { target: { value: "fr" } });
    expect(push).toHaveBeenCalledWith("/fr/dashboard/jobs");
  });
});
