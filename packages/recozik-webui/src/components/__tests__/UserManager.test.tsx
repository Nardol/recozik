import { describe, expect, it, beforeEach, afterEach, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { UserManager } from "../UserManager";
import { I18nProvider } from "../../i18n/I18nProvider";
import type { WhoAmI } from "../../lib/api";

// Mock API functions
const mockFetchUsers = vi.fn();
const mockRegisterUser = vi.fn();
const mockUpdateUser = vi.fn();
const mockDeleteUser = vi.fn();
const mockAdminResetPassword = vi.fn();
const mockFetchUserSessions = vi.fn();
const mockRevokeUserSessions = vi.fn();

vi.mock("../../lib/api", async () => {
  const actual = await vi.importActual("../../lib/api");
  return {
    ...actual,
    fetchWhoami: () => Promise.resolve(mockProfile),
    fetchUsers: () => mockFetchUsers(),
    registerUser: (payload: unknown) => mockRegisterUser(payload),
    updateUser: (id: number, payload: unknown) => mockUpdateUser(id, payload),
    deleteUser: (id: number) => mockDeleteUser(id),
    adminResetPassword: (id: number, payload: unknown) =>
      mockAdminResetPassword(id, payload),
    fetchUserSessions: (id: number) => mockFetchUserSessions(id),
    revokeUserSessions: (id: number) => mockRevokeUserSessions(id),
  };
});

// Mock TokenProvider
const mockProfile: WhoAmI = {
  user_id: "admin",
  display_name: "Admin User",
  roles: ["admin"],
  allowed_features: ["identify", "rename"],
};

vi.mock("../TokenProvider", () => ({
  useToken: () => ({
    profile: mockProfile,
    token: "mock-token",
    status: "authenticated",
    refreshProfile: vi.fn(),
  }),
}));

const mockUsers = [
  {
    id: 1,
    username: "admin",
    email: "admin@example.com",
    display_name: "Administrator",
    is_active: true,
    roles: ["admin"],
    allowed_features: ["identify", "rename"],
    quota_limits: {},
    created_at: "2024-01-01T00:00:00Z",
  },
  {
    id: 2,
    username: "user1",
    email: "user1@example.com",
    display_name: "User One",
    is_active: true,
    roles: ["operator"],
    allowed_features: ["identify"],
    quota_limits: { acoustid_lookup: 100 },
    created_at: "2024-01-02T00:00:00Z",
  },
  {
    id: 3,
    username: "user2",
    email: "user2@example.com",
    display_name: null,
    is_active: false,
    roles: ["readonly"],
    allowed_features: [],
    quota_limits: {},
    created_at: "2024-01-03T00:00:00Z",
  },
];

function renderUserManager() {
  return render(
    <I18nProvider locale="en">
      <UserManager sectionId="test-section" />
    </I18nProvider>,
  );
}

describe("UserManager", () => {
  beforeEach(() => {
    mockFetchUsers.mockReset();
    mockRegisterUser.mockReset();
    mockUpdateUser.mockReset();
    mockDeleteUser.mockReset();
    mockAdminResetPassword.mockReset();
    mockFetchUserSessions.mockReset();
    mockRevokeUserSessions.mockReset();

    // Default: return users
    mockFetchUsers.mockResolvedValue(mockUsers);
    mockFetchUserSessions.mockResolvedValue([]);

    // Mock window.confirm
    global.confirm = vi.fn(() => true);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders user table with users", async () => {
    renderUserManager();

    // Wait for users to load
    await waitFor(() => expect(mockFetchUsers).toHaveBeenCalled());

    // Check that user table is rendered
    expect(screen.getByRole("table")).toBeInTheDocument();

    // Check that users are displayed
    expect(screen.getByText("admin")).toBeInTheDocument();
    expect(screen.getByText("admin@example.com")).toBeInTheDocument();
    expect(screen.getByText("user1")).toBeInTheDocument();
    expect(screen.getByText("user1@example.com")).toBeInTheDocument();
  });

  it("shows active/inactive status", async () => {
    renderUserManager();

    await waitFor(() => expect(mockFetchUsers).toHaveBeenCalled());

    // User2 is inactive
    const user2Cell = await screen.findByText("user2");
    const user2Row = user2Cell.closest("tr");
    expect(user2Row).not.toBeNull();
    expect(user2Row).toHaveTextContent("Inactive");
  });

  it("displays user roles and features", async () => {
    renderUserManager();

    await waitFor(() => expect(mockFetchUsers).toHaveBeenCalled());

    // Check that roles are displayed (use getAllByText since "admin" appears multiple times)
    expect(screen.getAllByText(/admin/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/operator/i).length).toBeGreaterThan(0);

    // Check that features are displayed
    expect(screen.getAllByText(/identify/i).length).toBeGreaterThan(0);
  });

  it("opens create user modal when create button is clicked", async () => {
    renderUserManager();

    await waitFor(() => expect(mockFetchUsers).toHaveBeenCalled());

    // Click create user button
    const createButton = screen.getByRole("button", { name: /create.*user/i });
    fireEvent.click(createButton);

    // Check that modal is open by looking for the modal heading (h3)
    await waitFor(() => {
      expect(
        screen.getByRole("heading", { name: "Create New User", level: 3 }),
      ).toBeInTheDocument();
    });
  });

  it("creates a new user successfully", async () => {
    mockRegisterUser.mockResolvedValue({ status: "ok" });
    mockFetchUsers.mockResolvedValueOnce(mockUsers).mockResolvedValueOnce([
      ...mockUsers,
      {
        id: 4,
        username: "newuser",
        email: "newuser@example.com",
        display_name: "New User",
        is_active: true,
        roles: ["operator"],
        allowed_features: ["identify"],
        quota_limits: {},
        created_at: "2024-01-04T00:00:00Z",
      },
    ]);

    renderUserManager();

    await waitFor(() => expect(mockFetchUsers).toHaveBeenCalled());

    // Open create modal
    const createButton = screen.getByRole("button", { name: /create.*user/i });
    fireEvent.click(createButton);

    await waitFor(() =>
      expect(
        screen.getByRole("heading", { name: "Create New User", level: 3 }),
      ).toBeInTheDocument(),
    );

    // Fill in form
    fireEvent.change(screen.getByLabelText(/username/i), {
      target: { value: "newuser" },
    });
    fireEvent.change(screen.getByLabelText(/email/i), {
      target: { value: "newuser@example.com" },
    });
    fireEvent.change(screen.getByLabelText(/display name/i), {
      target: { value: "New User" },
    });
    fireEvent.change(screen.getByLabelText(/password/i), {
      target: { value: "SecurePass123!" },
    });

    // Submit form
    const submitButton = screen.getByRole("button", { name: /save user/i });
    fireEvent.click(submitButton);

    // Wait for API call
    await waitFor(() => {
      expect(mockRegisterUser).toHaveBeenCalledWith(
        expect.objectContaining({
          username: "newuser",
          email: "newuser@example.com",
          display_name: "New User",
          password: "SecurePass123!",
        }),
      );
    });

    // Modal should close and users should reload
    await waitFor(() => {
      expect(
        screen.queryByRole("heading", { name: "Create New User", level: 3 }),
      ).not.toBeInTheDocument();
    });
  });

  it("opens edit modal when edit button is clicked", async () => {
    renderUserManager();

    await waitFor(() => expect(mockFetchUsers).toHaveBeenCalled());

    // Find and click edit button for user1
    const editButtons = screen.getAllByRole("button", { name: /edit/i });
    fireEvent.click(editButtons[1]); // Second user (user1)

    // Check that edit modal is open
    await waitFor(() => {
      expect(screen.getByText("Edit User")).toBeInTheDocument();
      expect(screen.getByDisplayValue("user1@example.com")).toBeInTheDocument();
    });
  });

  it("updates user successfully", async () => {
    mockUpdateUser.mockResolvedValue({
      ...mockUsers[1],
      email: "updated@example.com",
    });

    renderUserManager();

    await waitFor(() => expect(mockFetchUsers).toHaveBeenCalled());

    // Open edit modal
    const editButtons = screen.getAllByRole("button", { name: /edit/i });
    fireEvent.click(editButtons[1]);

    await waitFor(() =>
      expect(screen.getByText("Edit User")).toBeInTheDocument(),
    );

    // Update email
    const emailInput = screen.getByDisplayValue("user1@example.com");
    fireEvent.change(emailInput, {
      target: { value: "updated@example.com" },
    });

    // Submit
    const saveButton = screen.getByRole("button", { name: /save/i });
    fireEvent.click(saveButton);

    // Wait for API call
    await waitFor(() => {
      expect(mockUpdateUser).toHaveBeenCalledWith(
        2,
        expect.objectContaining({
          email: "updated@example.com",
        }),
      );
    });
  });

  it("opens delete confirmation when delete button is clicked", async () => {
    renderUserManager();

    await waitFor(() => expect(mockFetchUsers).toHaveBeenCalled());

    // Click delete button
    const deleteButtons = screen.getAllByRole("button", { name: /delete/i });
    fireEvent.click(deleteButtons[1]);

    // Check that window.confirm was called
    expect(global.confirm).toHaveBeenCalled();
  });

  it("deletes user when confirmed", async () => {
    mockDeleteUser.mockResolvedValue({ status: "deleted" });

    renderUserManager();

    await waitFor(() => expect(mockFetchUsers).toHaveBeenCalled());

    // Click delete button (confirm is already mocked to return true)
    const deleteButtons = screen.getAllByRole("button", { name: /delete/i });
    fireEvent.click(deleteButtons[1]);

    // Wait for API call (confirm returns true, so delete proceeds)
    await waitFor(() => {
      expect(mockDeleteUser).toHaveBeenCalledWith(2);
    });
  });

  it("opens password reset modal when reset button is clicked", async () => {
    renderUserManager();

    await waitFor(() => expect(mockFetchUsers).toHaveBeenCalled());

    // Click password reset button for first user (admin)
    const resetButtons = screen.getAllByRole("button", {
      name: /reset password/i,
    });
    fireEvent.click(resetButtons[0]);

    // Check that password modal is open by looking for the heading
    await waitFor(() => {
      expect(screen.getByText(/Reset Password for admin/i)).toBeInTheDocument();
    });
  });

  it("resets password successfully", async () => {
    mockAdminResetPassword.mockResolvedValue({ status: "ok" });

    renderUserManager();

    await waitFor(() => expect(mockFetchUsers).toHaveBeenCalled());

    // Open password reset modal
    const resetButtons = screen.getAllByRole("button", {
      name: /reset password/i,
    });
    fireEvent.click(resetButtons[0]);

    await waitFor(() =>
      expect(screen.getByText(/Reset Password for admin/i)).toBeInTheDocument(),
    );

    // Enter new password
    const passwordInput = screen.getByLabelText(/new password/i);
    fireEvent.change(passwordInput, {
      target: { value: "NewSecure123!" },
    });

    // Submit - find all buttons with reset and click the submit one (not the action button)
    const allResetButtons = screen.getAllByRole("button", {
      name: /reset password/i,
    });
    // The last one is the submit button in the modal
    fireEvent.click(allResetButtons[allResetButtons.length - 1]);

    // Wait for API call
    await waitFor(() => {
      expect(mockAdminResetPassword).toHaveBeenCalledWith(
        mockUsers[0].id,
        expect.objectContaining({
          new_password: "NewSecure123!",
        }),
      );
    });
  });

  it("opens sessions modal when sessions button is clicked", async () => {
    mockFetchUserSessions.mockResolvedValue([
      {
        id: 1,
        user_id: 1,
        created_at: "2024-01-01T10:00:00Z",
        expires_at: "2024-01-01T11:00:00Z",
        refresh_expires_at: "2024-01-08T10:00:00Z",
        remember: false,
      },
    ]);

    renderUserManager();

    await waitFor(() => expect(mockFetchUsers).toHaveBeenCalled());

    // Click sessions button for first user (admin)
    const sessionsButtons = screen.getAllByRole("button", {
      name: /sessions/i,
    });
    fireEvent.click(sessionsButtons[0]);

    // Check that sessions modal is open
    await waitFor(() => {
      expect(
        screen.getByText(/Active Sessions for admin/i),
      ).toBeInTheDocument();
      expect(mockFetchUserSessions).toHaveBeenCalledWith(1);
    });
  });

  it("revokes all sessions successfully", async () => {
    mockFetchUserSessions.mockResolvedValue([
      {
        id: 1,
        user_id: 1,
        created_at: "2024-01-01T10:00:00Z",
        expires_at: "2024-01-01T11:00:00Z",
        refresh_expires_at: "2024-01-08T10:00:00Z",
        remember: false,
      },
    ]);
    mockRevokeUserSessions.mockResolvedValue({ status: "ok" });

    renderUserManager();

    await waitFor(() => expect(mockFetchUsers).toHaveBeenCalled());

    // Open sessions modal
    const sessionsButtons = screen.getAllByRole("button", {
      name: /sessions/i,
    });
    fireEvent.click(sessionsButtons[0]);

    await waitFor(() =>
      expect(
        screen.getByText(/Active Sessions for admin/i),
      ).toBeInTheDocument(),
    );

    // Click revoke all button
    const revokeButton = screen.getByRole("button", {
      name: /revoke all/i,
    });
    fireEvent.click(revokeButton);

    // Wait for API call
    await waitFor(() => {
      expect(mockRevokeUserSessions).toHaveBeenCalledWith(1);
    });
  });

  it("shows error message when user creation fails", async () => {
    mockRegisterUser.mockRejectedValue(new Error("Email already exists"));

    renderUserManager();

    await waitFor(() => expect(mockFetchUsers).toHaveBeenCalled());

    // Open create modal
    const createButton = screen.getByRole("button", { name: /create.*user/i });
    fireEvent.click(createButton);

    await waitFor(() =>
      expect(
        screen.getByRole("heading", { name: "Create New User", level: 3 }),
      ).toBeInTheDocument(),
    );

    // Fill minimal form
    fireEvent.change(screen.getByLabelText(/username/i), {
      target: { value: "duplicate" },
    });
    fireEvent.change(screen.getByLabelText(/email/i), {
      target: { value: "exists@example.com" },
    });
    fireEvent.change(screen.getByLabelText(/password/i), {
      target: { value: "SecurePass123!" },
    });

    // Submit
    const submitButton = screen.getByRole("button", { name: /save user/i });
    fireEvent.click(submitButton);

    // Wait for error message
    await waitFor(() => {
      expect(screen.getByText(/email already exists/i)).toBeInTheDocument();
    });
  });
});
