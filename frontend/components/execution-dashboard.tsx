"use client";

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";

import {
  ExecutionRecord,
  ExecutionStatus,
  fetchExecutions,
  submitExecution,
} from "../lib/api";

const POLL_INTERVAL_MS = 10_000;

function formatUtc(timestamp: string | null): string {
  if (!timestamp) {
    return "-";
  }
  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) {
    return timestamp;
  }
  return date.toISOString().replace("T", " ").replace(".000", "");
}

function statusBadgeClass(status: ExecutionStatus): string {
  switch (status) {
    case "COMPLETED":
      return "status-pill status-completed";
    case "FAILED":
      return "status-pill status-failed";
    case "RUNNING":
      return "status-pill status-running";
    default:
      return "status-pill status-queued";
  }
}

function compactError(message: string, maxLength = 180): string {
  const normalized = message.replace(/\s+/g, " ").trim();
  if (normalized.length <= maxLength) {
    return normalized;
  }
  return `${normalized.slice(0, maxLength - 1)}…`;
}

export default function ExecutionDashboard() {
  const [ticker, setTicker] = useState("");
  const [records, setRecords] = useState<ExecutionRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [lastSyncUtc, setLastSyncUtc] = useState<string>("");

  const loadRows = useCallback(async (showSpinner: boolean) => {
    if (showSpinner) {
      setLoading(true);
    } else {
      setRefreshing(true);
    }
    try {
      const payload = await fetchExecutions({ page: 1, pageSize: 50 });
      setRecords(payload.items);
      setLoadError(null);
      setLastSyncUtc(new Date().toISOString());
    } catch (error) {
      setLoadError(error instanceof Error ? error.message : "Failed to load executions.");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    void loadRows(true);
    const interval = setInterval(() => {
      void loadRows(false);
    }, POLL_INTERVAL_MS);
    return () => clearInterval(interval);
  }, [loadRows]);

  const metrics = useMemo(() => {
    const counts: Record<ExecutionStatus, number> = {
      QUEUED: 0,
      RUNNING: 0,
      COMPLETED: 0,
      FAILED: 0,
    };
    for (const row of records) {
      counts[row.status] += 1;
    }
    return counts;
  }, [records]);

  const onSubmit = useCallback(
    async (event: FormEvent<HTMLFormElement>) => {
      event.preventDefault();
      const normalized = ticker.trim().toUpperCase();
      if (!normalized) {
        setSubmitError("Ticker is required.");
        return;
      }

      setSubmitting(true);
      setSubmitError(null);
      try {
        const created = await submitExecution(normalized);
        setRecords((prev) => [created, ...prev]);
        setTicker("");
      } catch (error) {
        setSubmitError(error instanceof Error ? error.message : "Failed to submit execution.");
      } finally {
        setSubmitting(false);
      }
    },
    [ticker]
  );

  return (
    <main className="dashboard-shell">
      <section className="hero-card">
        <div className="brand-lockup">
          <img src="/brand/valence-logo.svg" alt="Valence" className="brand-logo" />
          <p className="eyebrow">Institutional-Grade Equity Research</p>
        </div>
        <h1 className="hero-title">Valence Terminal</h1>
        <p className="hero-subtitle">
          Premium US equities research for the public market investor: submit a ticker, generate a formula-owned valuation
          workbook, and track every execution with client-ready memo deliverables. All times are UTC.
        </p>

        <form className="submit-form" onSubmit={onSubmit}>
          <label htmlFor="ticker-input" className="field-label">
            Stock Ticker
          </label>
          <div className="field-row">
            <input
              id="ticker-input"
              type="text"
              value={ticker}
              onChange={(event) => setTicker(event.target.value.toUpperCase())}
              placeholder="AAPL"
              maxLength={10}
              autoComplete="off"
            />
            <button type="submit" disabled={submitting}>
              {submitting ? "Submitting..." : "Analyze"}
            </button>
          </div>
          {submitError ? <p className="error-text">{submitError}</p> : null}
        </form>

        <div className="metrics-grid">
          <article className="metric-card">
            <p>Total</p>
            <h3>{records.length}</h3>
          </article>
          <article className="metric-card">
            <p>Queued</p>
            <h3>{metrics.QUEUED}</h3>
          </article>
          <article className="metric-card">
            <p>Running</p>
            <h3>{metrics.RUNNING}</h3>
          </article>
          <article className="metric-card">
            <p>Completed</p>
            <h3>{metrics.COMPLETED}</h3>
          </article>
          <article className="metric-card">
            <p>Failed</p>
            <h3>{metrics.FAILED}</h3>
          </article>
        </div>
      </section>

      <section className="table-card">
        <header className="table-header">
          <div>
            <h2>Execution History</h2>
            <p className="table-subtitle">Latest 50 valuation + memo runs. Timestamp standard: UTC.</p>
          </div>
          <p className="sync-text">
            {refreshing ? "Refreshing..." : "Synced"}
            {lastSyncUtc ? ` at ${formatUtc(lastSyncUtc)}` : ""}
          </p>
        </header>

        {loadError ? <p className="error-text">{loadError}</p> : null}
        {loading ? <p className="loading-text">Loading executions...</p> : null}

        {!loading ? (
          <>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Stock Ticker</th>
                    <th>Name</th>
                    <th>When Analyzed (UTC)</th>
                    <th>Google Sheets</th>
                    <th>Investment Memo PDF</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {records.length === 0 ? (
                    <tr>
                      <td colSpan={6} className="empty-row">
                        No executions yet.
                      </td>
                    </tr>
                  ) : (
                    records.map((row) => (
                      <tr key={row.id}>
                        <td className="mono">{row.ticker}</td>
                        <td>{row.company_name || "-"}</td>
                        <td className="mono">{formatUtc(row.analyzed_at_utc)}</td>
                        <td>
                          {row.google_sheets_url ? (
                            <a href={row.google_sheets_url} target="_blank" rel="noreferrer">
                              Open Sheet
                            </a>
                          ) : (
                            "-"
                          )}
                        </td>
                        <td>
                          {row.memo_pdf_url ? (
                            <a href={row.memo_pdf_url} target="_blank" rel="noreferrer">
                              Open Memo
                            </a>
                          ) : (
                            "-"
                          )}
                        </td>
                        <td>
                          <span className={statusBadgeClass(row.status)}>{row.status}</span>
                          {row.status === "FAILED" && row.error_message ? (
                            <p className="row-error" title={row.error_message}>
                              {compactError(row.error_message)}
                            </p>
                          ) : null}
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>

            <div className="execution-mobile-list">
              {records.length === 0 ? (
                <p className="empty-mobile-list">No executions yet.</p>
              ) : (
                records.map((row) => (
                  <article className="execution-card" key={`mobile-${row.id}`}>
                    <header className="execution-card-header">
                      <div>
                        <p className="execution-card-label">Ticker</p>
                        <h3 className="execution-card-ticker mono">{row.ticker}</h3>
                        <p className="execution-card-name">{row.company_name || "-"}</p>
                      </div>
                      <span className={statusBadgeClass(row.status)}>{row.status}</span>
                    </header>

                    <dl className="execution-card-details">
                      <div>
                        <dt>When Analyzed (UTC)</dt>
                        <dd className="mono">{formatUtc(row.analyzed_at_utc)}</dd>
                      </div>
                      <div>
                        <dt>Google Sheets</dt>
                        <dd>
                          {row.google_sheets_url ? (
                            <a href={row.google_sheets_url} target="_blank" rel="noreferrer">
                              Open Sheet
                            </a>
                          ) : (
                            "-"
                          )}
                        </dd>
                      </div>
                      <div>
                        <dt>Investment Memo PDF</dt>
                        <dd>
                          {row.memo_pdf_url ? (
                            <a href={row.memo_pdf_url} target="_blank" rel="noreferrer">
                              Open Memo
                            </a>
                          ) : (
                            "-"
                          )}
                        </dd>
                      </div>
                    </dl>

                    {row.status === "FAILED" && row.error_message ? (
                      <p className="row-error" title={row.error_message}>
                        {compactError(row.error_message)}
                      </p>
                    ) : null}
                  </article>
                ))
              )}
            </div>
            </>
          ) : null}
      </section>
    </main>
  );
}
