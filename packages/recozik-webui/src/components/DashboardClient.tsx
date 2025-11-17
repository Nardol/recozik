"use client";

import { useCallback, useMemo, useState, useEffect } from "react";
import { TokenForm } from "./TokenForm";
import { useToken } from "./TokenProvider";
import { JobUploader } from "./JobUploader";
import { JobList } from "./JobList";
import { AdminTokenManager } from "./AdminTokenManager";
import { ProfileCard } from "./ProfileCard";
import { NavigationBar } from "./NavigationBar";
import { JobDetail } from "../lib/api";
import { useI18n } from "../i18n/I18nProvider";

export function DashboardClient() {
  const { token } = useToken();
  const { t } = useI18n();
  const [jobs, setJobs] = useState<JobDetail[]>([]);

  useEffect(() => {
    setJobs([]);
  }, [token]);

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

  if (!token) {
    return (
      <main className="container" id="main-content">
        <header>
          <h1>{t("app.title")}</h1>
          <p>{t("app.lead")}</p>
        </header>
        <TokenForm />
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
