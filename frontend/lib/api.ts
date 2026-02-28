export type ExecutionStatus = "QUEUED" | "RUNNING" | "COMPLETED" | "FAILED";

export type ExecutionRecord = {
  id: string;
  run_id: string;
  ticker: string;
  company_name: string | null;
  status: ExecutionStatus;
  submitted_at_utc: string;
  started_at_utc: string | null;
  finished_at_utc: string | null;
  analyzed_at_utc: string;
  google_sheets_url: string | null;
  memo_pdf_url: string | null;
  error_message: string | null;
};

export type ExecutionListPayload = {
  items: ExecutionRecord[];
  total: number;
  page: number;
  page_size: number;
};

const API_BASE_URL = (process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000").replace(/\/$/, "");

type ListParams = {
  page?: number;
  pageSize?: number;
  ticker?: string;
  status?: ExecutionStatus;
};

export async function fetchExecutions(params: ListParams = {}): Promise<ExecutionListPayload> {
  const query = new URLSearchParams();
  query.set("page", String(params.page ?? 1));
  query.set("page_size", String(params.pageSize ?? 50));
  if (params.ticker) {
    query.set("ticker", params.ticker);
  }
  if (params.status) {
    query.set("status", params.status);
  }

  const response = await fetch(`${API_BASE_URL}/api/v1/executions?${query.toString()}`, {
    method: "GET",
    cache: "no-store",
  });
  return parseJsonResponse<ExecutionListPayload>(response);
}

export async function submitExecution(ticker: string): Promise<ExecutionRecord> {
  const response = await fetch(`${API_BASE_URL}/api/v1/executions`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ ticker }),
  });
  return parseJsonResponse<ExecutionRecord>(response);
}

async function parseJsonResponse<T>(response: Response): Promise<T> {
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail =
      typeof payload.detail === "string"
        ? payload.detail
        : `API request failed with status ${response.status}`;
    throw new Error(detail);
  }
  return payload as T;
}
