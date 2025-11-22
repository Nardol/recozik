"use client";

import { useCallback, useMemo, useState, useEffect } from "react";
import { useToken } from "./TokenProvider";
import { JobUploader } from "./JobUploader";
import { JobList } from "./JobList";
import { AdminTokenManager } from "./AdminTokenManager";
import { ProfileCard } from "./ProfileCard";
import { NavigationBar } from "./NavigationBar";
import { JobDetail, fetchJobs } from "../lib/api";
import { useI18n } from "../i18n/I18nProvider";
import { LoginForm } from "./LoginForm";

export function DashboardClient() {
  const { token, profile, status } = useToken();
  const { t } = useI18n();
  const [jobs, setJobs] = useState<JobDetail[]>([]);

  useEffect(() => {
    setJobs([]);
  }, [token, profile]);

  useEffect(() => {
    if (!profile) {
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const initial = await fetchJobs();
        if (!cancelled) {
          setJobs(initial);
        }
      } catch (error) {
        console.error("Unable to load recent jobs", error);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [profile]);

  const sortedJobs = useMemo(
    () =>
      [...jobs].sort(
        (a, b) =>
          new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime(),
      ),
    [jobs],
  );

  const handleJobUpdate = useCallback((detail: JobDetail) => {
    setJobs((previous) => {
      const idx = previous.findIndex((job) => job.job_id === detail.job_id);
      if (idx >= 0) {
        const clone = [...previous];
        clone[idx] = detail;
        return clone;
      }
      return [...previous, detail];
    });
  }, []);

  if (status === "loading") {
    return (
      <main className="container" id="main-content">
        <header>
          <h1 data-testid="main-heading">{t("app.title")}</h1>
          <p className="muted">{t("app.lead")}</p>
        </header>
        <p>{t("app.loading")}</p>
      </main>
    );
  }

  if (!profile) {
    return (
      <main className="container" id="main-content">
        <header>
          <h1 data-testid="main-heading">{t("app.title")}</h1>
          <p data-testid="login-prompt">{t("app.lead")}</p>
        </header>
        <div className="panel">
          <h2>{t("login.title")}</h2>
          <p className="muted">{t("login.description")}</p>
          <LoginForm />
        </div>
      </main>
    );
  }

  return (
    <>
      <NavigationBar />
      <main className="container" id="main-content">
        <header>
          <h1>{t("app.title")}</h1>
          <p className="muted">{t("app.leadAuthed")}</p>
        </header>
        <ProfileCard />
        <div className="grid">
          <JobUploader
            sectionId="upload-section"
            onJobUpdate={handleJobUpdate}
          />
          <JobList
            sectionId="jobs-section"
            jobs={sortedJobs}
            onUpdate={handleJobUpdate}
          />
        </div>
        <AdminTokenManager sectionId="admin-section" />
      </main>
    </>
  );
}
