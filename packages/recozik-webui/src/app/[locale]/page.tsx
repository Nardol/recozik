import { cookies } from "next/headers";
import { notFound } from "next/navigation";
import { DashboardClient } from "../../components/DashboardClient";
import { Providers } from "../../components/Providers";
import { serverFetch } from "../../lib/server/api";
import { JobDetail, TokenResponse, UserResponse, WhoAmI } from "../../lib/api";
import { isSupportedLocale } from "../../lib/constants";
import { messages, type Locale } from "../../i18n/messages";
import AdminTokenPanelPragma from "../../components/AdminTokenPanelPragma";
import UsersPanelPragma from "../../components/UsersPanelPragma";

interface Props {
  params: Promise<{ locale: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}

async function loadInitialData(): Promise<{
  profile: WhoAmI | null;
  jobs: JobDetail[];
  tokens: TokenResponse[];
  users: UserResponse[];
}> {
  try {
    const profile = await serverFetch<WhoAmI>("/whoami");
    const jobs = await serverFetch<JobDetail[]>("/jobs");
    let tokens: TokenResponse[] = [];
    let users: UserResponse[] = [];
    if (profile.roles?.includes("admin")) {
      tokens = await serverFetch<TokenResponse[]>("/admin/tokens");
      users = await serverFetch<UserResponse[]>("/admin/users");
    }
    return { profile, jobs, tokens, users };
  } catch {
    return { profile: null, jobs: [], tokens: [], users: [] };
  }
}

export default async function LocaleDashboard({ params, searchParams }: Props) {
  const resolved = await params;
  const qs = await searchParams;
  if (!isSupportedLocale(resolved.locale)) {
    notFound();
  }
  const locale = resolved.locale as Locale;
  const cookieStore = await cookies();
  const sessionId = cookieStore.get("recozik_session")?.value ?? null;
  const { profile, jobs, tokens, users } = await loadInitialData();
  const loginError =
    typeof qs.login_error === "string"
      ? {
          invalid_credentials: translate("login.errorInvalid"),
          account_disabled: translate("login.errorDisabled"),
          missing_credentials: translate("login.errorMissing"),
          generic: translate("login.errorGeneric"),
        }[decodeURIComponent(qs.login_error)] || translate("login.errorGeneric")
      : null;
  const tokenStatus =
    typeof qs.token_status === "string"
      ? decodeURIComponent(qs.token_status)
      : null;
  const tokenError =
    typeof qs.token_error === "string"
      ? decodeURIComponent(qs.token_error)
      : null;
  const userStatus =
    typeof qs.user_status === "string"
      ? decodeURIComponent(qs.user_status)
      : null;
  const userError =
    typeof qs.user_error === "string"
      ? decodeURIComponent(qs.user_error)
      : null;

  const translate = (key: keyof typeof messages.en) =>
    messages[locale][key] ?? key;
  const statusMessage =
    tokenStatus === "created" ? translate("admin.status.created") : null;
  const errorMessage =
    tokenError === "invalid_user"
      ? translate("admin.status.invalidUser")
      : tokenError === "server_error"
        ? translate("admin.status.error")
        : tokenError
          ? `${translate("admin.status.error")} (${tokenError})`
          : null;
  const fieldErrors: Record<string, string> | undefined =
    tokenError === "invalid_user"
      ? { user_id: translate("admin.status.invalidUser") }
      : tokenError === "missing_display"
        ? { display_name: translate("admin.error.displayRequired") }
        : undefined;
  const userStatusMessage =
    userStatus === "created" ? translate("users.status.created") : null;
  const userErrorMessage =
    userError === "missing_fields"
      ? translate("users.status.missing")
      : userError === "server_error"
        ? translate("users.status.error")
        : userError
          ? `${translate("users.status.error")} (${userError})`
          : null;
  const userFieldErrors: Record<string, string> | undefined =
    userError === "missing_fields"
      ? {
          username: translate("users.status.missing"),
          email: translate("users.status.missing"),
          password: translate("users.status.missing"),
        }
      : undefined;

  return (
    <>
      <noscript>
        <style>{`.js-only{display:none !important;}`}</style>
        {profile?.roles?.includes("admin") ? (
          <AdminTokenPanelPragma
            locale={locale}
            tokens={tokens}
            users={users}
            status={statusMessage}
            error={errorMessage}
            fieldErrors={fieldErrors}
          />
        ) : null}
        {profile?.roles?.includes("admin") ? (
          <UsersPanelPragma
            locale={locale}
            users={users}
            status={userStatusMessage}
            error={userErrorMessage}
            fieldErrors={userFieldErrors}
          />
        ) : null}
      </noscript>
      <Providers
        locale={locale}
        initialToken={sessionId}
        initialProfile={profile}
      >
        <DashboardClient initialJobs={jobs} loginError={loginError} />
      </Providers>
    </>
  );
}
