"use client";

import { useCallback, useMemo, useState, useEffect } from "react";
import { TokenForm } from "../components/TokenForm";
import { useToken } from "../components/TokenProvider";
import { JobUploader } from "../components/JobUploader";
import { JobList } from "../components/JobList";
import { AdminTokenManager } from "../components/AdminTokenManager";
import { ProfileCard } from "../components/ProfileCard";
import { NavigationBar } from "../components/NavigationBar";
import { JobDetail } from "../lib/api";

export default function Home() {
  const { token } = useToken();
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
          <h1>Recozik Web Console</h1>
          <p>
            Authenticate with an API token to access jobs and admin features.
          </p>
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
          <h1>Recozik Web Console</h1>
          <p className="muted">
            Monitor identify jobs, trigger uploads, and manage API tokens.
          </p>
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
