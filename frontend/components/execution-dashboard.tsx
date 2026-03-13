"use client";

import { FormEvent, MouseEvent, useCallback, useEffect, useMemo, useState } from "react";

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

function memoLabel(row: Pick<ExecutionRecord, "ticker" | "company_name">): string {
  return row.company_name ? `${row.ticker} · ${row.company_name}` : row.ticker;
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
  const [selectedMemoId, setSelectedMemoId] = useState<string | null>(null);

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

  useEffect(() => {
    if (!selectedMemoId) {
      return;
    }
    const selectedRecord = records.find((row) => row.id === selectedMemoId);
    if (!selectedRecord || !selectedRecord.memo_pdf_url) {
      setSelectedMemoId(null);
    }
  }, [records, selectedMemoId]);

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

  const selectedMemoRecord = useMemo(() => {
    if (!selectedMemoId) {
      return null;
    }
    return records.find((row) => row.id === selectedMemoId) ?? null;
  }, [records, selectedMemoId]);

  useEffect(() => {
    if (!selectedMemoRecord) {
      return;
    }
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setSelectedMemoId(null);
      }
    };
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    window.addEventListener("keydown", handleKeyDown);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [selectedMemoRecord]);

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

  const openMemo = useCallback((recordId: string) => {
    setSelectedMemoId(recordId);
  }, []);

  const closeMemoViewer = useCallback(() => {
    setSelectedMemoId(null);
  }, []);

  const closeModalOnBackdrop = useCallback(
    (event: MouseEvent<HTMLDivElement>) => {
      if (event.target === event.currentTarget) {
        closeMemoViewer();
      }
    },
    [closeMemoViewer]
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
                    records.map((row) => {
                      const isSelected = row.id === selectedMemoId;
                      return (
                        <tr key={row.id} className={isSelected ? "is-selected" : undefined}>
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
                              <button
                                type="button"
                                className={`link-button ${isSelected ? "link-button-active" : ""}`}
                                onClick={() => openMemo(row.id)}
                                aria-pressed={isSelected}
                              >
                                {isSelected ? "Viewing" : "Open Memo"}
                              </button>
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
                      );
                    })
                  )}
                </tbody>
              </table>
            </div>

            <div className="execution-mobile-list">
              {records.length === 0 ? (
                <p className="empty-mobile-list">No executions yet.</p>
              ) : (
                records.map((row) => {
                  const isSelected = row.id === selectedMemoId;
                  return (
                    <article
                      className={`execution-card ${isSelected ? "is-selected" : ""}`}
                      key={`mobile-${row.id}`}
                    >
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
                              <button
                                type="button"
                                className={`link-button ${isSelected ? "link-button-active" : ""}`}
                                onClick={() => openMemo(row.id)}
                                aria-pressed={isSelected}
                              >
                                {isSelected ? "Viewing" : "Open Memo"}
                              </button>
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
                  );
                })
              )}
            </div>
          </>
        ) : null}
      </section>

      {selectedMemoRecord && selectedMemoRecord.memo_pdf_url ? (
        <div
          className="memo-modal-overlay"
          role="presentation"
          onClick={closeModalOnBackdrop}
        >
          <section
            className="memo-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="memo-modal-title"
            onClick={(event) => event.stopPropagation()}
          >
            <header className="memo-modal-header">
              <div>
                <p className="memo-modal-label">Investment Memo</p>
                <h2 id="memo-modal-title" className="memo-modal-title">
                  {memoLabel(selectedMemoRecord)}
                </h2>
                <p className="memo-modal-meta">Analyzed {formatUtc(selectedMemoRecord.analyzed_at_utc)}</p>
              </div>

              <div className="memo-modal-actions">
                <a
                  href={selectedMemoRecord.memo_pdf_url}
                  target="_blank"
                  rel="noreferrer"
                  className="viewer-action-link"
                >
                  New Tab
                </a>
                <a
                  href={selectedMemoRecord.memo_pdf_url}
                  download={`${selectedMemoRecord.ticker}_${selectedMemoRecord.run_id}_investment_memo.pdf`}
                  className="viewer-action-link"
                >
                  Download
                </a>
                <button type="button" className="memo-modal-close" onClick={closeMemoViewer} aria-label="Close memo viewer">
                  Close
                </button>
              </div>
            </header>

            <div className="memo-modal-frame-wrap">
              <iframe
                key={selectedMemoRecord.id}
                src={selectedMemoRecord.memo_pdf_url}
                title={`${memoLabel(selectedMemoRecord)} investment memo PDF`}
                className="memo-modal-frame"
              />
            </div>
          </section>
        </div>
      ) : null}
    </main>
  );
}
