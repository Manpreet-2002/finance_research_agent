# Backend Cloud Run Deployment Memory (2026-03-04)

This file records the current backend deployment state and the deployment commands used in this conversation.

Scope and accuracy notes:
- This document distinguishes between:
  - exact commands I can confirm from the shell transcript still visible in this session
  - earlier bootstrap commands that were executed earlier in this conversation, but whose raw shell lines are no longer fully present in the active transcript window
- Where a command includes a secret, password, or token, the value is intentionally redacted.
- Passive polling and wait commands (`sleep`, repeated `curl` polls with the same URL) are not exhaustively listed unless they materially changed state.
- User-run commands are called out separately from assistant-run commands.

## Current Verified Live State

As verified on 2026-03-04:

- GCP project: `finance-research-agent`
- Region: `us-central1`

### Cloud Run API service

- Service: `finance-research-api`
- URL: `https://finance-research-api-gfnc7q4q7a-uc.a.run.app`
- Latest ready revision: `finance-research-api-00007-74j`
- Current image:
  - `us-central1-docker.pkg.dev/finance-research-agent/finance-research-backend/finance-research-backend:20260304-030500`
- This latest API-only rollout contains the `http -> https` memo URL generation fix.
- The latest config-only revision also adds:
  - `API_CORS_ORIGINS=https://finance-research-agent.vercel.app,http://localhost:3000,http://127.0.0.1:3000`

### Vercel frontend

- Frontend URL:
  - `https://finance-research-agent.vercel.app`
- Expected production backend base URL:
  - `https://finance-research-api-gfnc7q4q7a-uc.a.run.app`

### Cloud Run worker job

- Job: `finance-research-worker`
- Current image:
  - `us-central1-docker.pkg.dev/finance-research-agent/finance-research-backend/finance-research-backend:20260304-022339`
- Current command:
  - `/app/.venv/bin/python -m backend.app.workers.run_execution`
- Current timeout:
  - `2700` seconds (`45m`)
- Current retries:
  - `0`
- Current service account:
  - `finance-research-worker@finance-research-agent.iam.gserviceaccount.com`

Important current state:
- The API service and worker job are intentionally on different image tags right now.
- That is expected at the moment because the most recent redeploy only needed the API service for the memo URL scheme fix.

### Storage

- Artifacts bucket:
  - `gs://finance-research-agent-artifacts`
- Current bucket IAM relevant to the app:
  - `finance-research-worker@finance-research-agent.iam.gserviceaccount.com` has `roles/storage.objectAdmin`
  - `finance-research-api@finance-research-agent.iam.gserviceaccount.com` has `roles/storage.objectViewer`

This API bucket read permission was added after the first deployed memo fetch returned `403 Forbidden`.

### Scheduler

- Scheduler job:
  - `projects/finance-research-agent/locations/us-central1/jobs/finance-research-dispatch`
- Schedule:
  - `* * * * *`
- Target:
  - `https://finance-research-api-gfnc7q4q7a-uc.a.run.app/api/v1/internal/dispatch-next`
- Auth:
  - Bearer token header is configured
  - token value intentionally not recorded here

### Cloud SQL / database

Confirmed logical deployment state from the deployed app configuration used in this conversation:

- Cloud SQL instance: `finance-research-pg`
- Database: `finance_research`
- Application DB user: `finance_agent`
- Database connection is supplied to Cloud Run through the `execution-database-url` Secret Manager secret
- The actual password is intentionally not recorded in this file

### Secrets in active use

The deployed job configuration confirms the following secrets are wired into runtime:

- `execution-database-url`
- `google-oauth-client-secret-json`
- `google-oauth-token-json`
- `google-api-key`
- `finnhub-api-key`
- `alpha-vantage-api-key`
- `tavily-api-key`
- `fred-api-key`
- `sec-api-user-agent`
- `sec-contact-email`

The API also uses:

- `execution-internal-auth-token`

## User-Run Commands (before assistant deployment actions)

The following were explicitly reported by the user as already completed:

```bash
gcloud config set project finance-research-agent
gcloud auth login
```

The user also stated that the deployment environment variables had been populated in `.env`.

## Exact Assistant-Run Commands Confirmed From This Session

These commands are exact shell invocations that are confirmed by the visible shell transcript in this session.

### Deployment state inspection

```bash
gcloud run services describe finance-research-api --region us-central1 --format='yaml(metadata.name,status.url,status.latestReadyRevisionName,spec.template.spec.containers[0].image)'
```

```bash
gcloud run jobs describe finance-research-worker --region us-central1 --format=json
```

```bash
gcloud scheduler jobs describe finance-research-dispatch --location us-central1 --format='yaml(name,schedule,httpTarget.uri,httpTarget.headers)'
```

```bash
gcloud storage buckets get-iam-policy gs://finance-research-agent-artifacts --format='yaml(bindings)'
```

### Initial live API smoke check after deployment

```bash
curl -sS https://finance-research-api-gfnc7q4q7a-uc.a.run.app/api/v1/executions
```

This was used to confirm the API was serving successfully after deployment.

### Submit and monitor the deployed PLTR run

The deployed Cloud Run-backed execution was submitted for `PLTR` and then polled until completion.

Submission command:

```bash
curl -sS -X POST https://finance-research-api-gfnc7q4q7a-uc.a.run.app/api/v1/executions -H 'Content-Type: application/json' -d '{"ticker":"PLTR"}'
```

Polling command:

```bash
curl -sS https://finance-research-api-gfnc7q4q7a-uc.a.run.app/api/v1/executions/dc6f562e-aaf1-4172-99f2-90f5ed100c39
```

Observed terminal result:

- Execution ID: `dc6f562e-aaf1-4172-99f2-90f5ed100c39`
- Run ID: `api_20260303T210738812405Z_acb0400c`
- Ticker: `PLTR`
- Status: `COMPLETED`
- Company: `Palantir Technologies Inc.`
- Google Sheet:
  - `https://docs.google.com/spreadsheets/d/1BCfrr7F_BuMsiGIQB_aKqCuP893LNN1JHdv_6cCuDqE/edit`

### Fix memo download permission

This command was run to fix the deployed API's inability to read memo PDFs from GCS:

```bash
gcloud storage buckets add-iam-policy-binding gs://finance-research-agent-artifacts --member="serviceAccount:finance-research-api@finance-research-agent.iam.gserviceaccount.com" --role="roles/storage.objectViewer"
```

This fixed the `403 Forbidden` GCS read failure from the API memo endpoint.

### Build and deploy image tag `20260304-030500` (API-only rollout for HTTPS memo URLs)

The latest image build command:

```bash
gcloud builds submit --config cloudbuild.backend.yaml --substitutions _IMAGE=us-central1-docker.pkg.dev/finance-research-agent/finance-research-backend/finance-research-backend:20260304-030500 .
```

Build result:

- Cloud Build ID: `aaf86b41-a3f4-4c11-bc2a-db22997d8370`
- Image:
  - `us-central1-docker.pkg.dev/finance-research-agent/finance-research-backend/finance-research-backend:20260304-030500`
- Digest:
  - `sha256:1a0c60e0109c9df86d289a3baa9f90213131a91150cfc6abba1311ce4cf79684`

The API service update command:

```bash
gcloud run services update finance-research-api --region us-central1 --image us-central1-docker.pkg.dev/finance-research-agent/finance-research-backend/finance-research-backend:20260304-030500
```

Rollout result:

- New revision: `finance-research-api-00006-m62`
- Traffic: `100%`

### Final recheck after the HTTPS fix

```bash
curl -sS https://finance-research-api-gfnc7q4q7a-uc.a.run.app/api/v1/executions/dc6f562e-aaf1-4172-99f2-90f5ed100c39
```

Confirmed result:

- `memo_pdf_url` now returns:
  - `https://finance-research-api-gfnc7q4q7a-uc.a.run.app/api/v1/executions/dc6f562e-aaf1-4172-99f2-90f5ed100c39/memo.pdf`

### Fix deployed CORS for the Vercel frontend

The first attempt used `--update-env-vars` without a custom delimiter and failed because the commas inside the `API_CORS_ORIGINS` value were parsed as separators.

Failed command:

```bash
gcloud run services update finance-research-api --region us-central1 --update-env-vars API_CORS_ORIGINS=https://finance-research-agent.vercel.app,http://localhost:3000,http://127.0.0.1:3000
```

Successful command:

```bash
gcloud run services update finance-research-api --region us-central1 --update-env-vars '^#^API_CORS_ORIGINS=https://finance-research-agent.vercel.app,http://localhost:3000,http://127.0.0.1:3000'
```

Rollout result:

- New revision: `finance-research-api-00007-74j`
- Traffic: `100%`
- The deployed API now explicitly allows the production Vercel origin plus localhost development origins.

### Direct memo endpoint probes attempted from this shell

These two direct header checks were attempted after the API fix:

```bash
curl -sS -I https://finance-research-api-gfnc7q4q7a-uc.a.run.app/api/v1/executions/dc6f562e-aaf1-4172-99f2-90f5ed100c39/memo.pdf
```

```bash
curl -sS -I https://finance-research-api-820190948453.us-central1.run.app/api/v1/executions/dc6f562e-aaf1-4172-99f2-90f5ed100c39/memo.pdf
```

Both of these failed from this shell with DNS resolution errors (`curl: (6)`), so they did not provide a fresh header-level verification from this environment.

## Earlier Bootstrap And First Deployment Commands (Executed Earlier In This Conversation)

The exact raw shell transcript for the initial bootstrap and first full deployment is not fully available in the active transcript window anymore. To avoid inventing false precision, this section records:

- what was definitely deployed earlier in this conversation
- the exact resource names now present
- the canonical command shapes that match the live resources

These earlier steps were completed before the later API-only redeploy.

### APIs enabled

This project required these services to be enabled:

- `run.googleapis.com`
- `artifactregistry.googleapis.com`
- `cloudbuild.googleapis.com`
- `secretmanager.googleapis.com`
- `sqladmin.googleapis.com`
- `cloudscheduler.googleapis.com`
- `storage.googleapis.com`
- `iam.googleapis.com`

Canonical command shape:

```bash
gcloud services enable run.googleapis.com artifactregistry.googleapis.com cloudbuild.googleapis.com secretmanager.googleapis.com sqladmin.googleapis.com cloudscheduler.googleapis.com storage.googleapis.com iam.googleapis.com
```

### Artifact Registry created

Live resource:

- Repository: `finance-research-backend`
- Location: `us-central1`

Canonical command shape:

```bash
gcloud artifacts repositories create finance-research-backend --repository-format=docker --location=us-central1 --description="Finance research backend images"
```

### Artifacts bucket created

Live resource:

- Bucket: `gs://finance-research-agent-artifacts`

Canonical command shape:

```bash
gcloud storage buckets create gs://finance-research-agent-artifacts --location=us-central1 --uniform-bucket-level-access
```

### Cloud SQL provisioned

Live resources:

- Instance: `finance-research-pg`
- Database: `finance_research`
- User: `finance_agent`

Canonical command shapes:

```bash
gcloud sql instances create finance-research-pg --database-version=POSTGRES_16 --region=us-central1 --cpu=2 --memory=4096MB
```

```bash
gcloud sql databases create finance_research --instance=finance-research-pg
```

```bash
gcloud sql users create finance_agent --instance=finance-research-pg --password='<redacted>'
```

### Service accounts created

Live service accounts referenced by deployed resources:

- `finance-research-api@finance-research-agent.iam.gserviceaccount.com`
- `finance-research-worker@finance-research-agent.iam.gserviceaccount.com`

Canonical command shapes:

```bash
gcloud iam service-accounts create finance-research-api --display-name="Finance Research API"
```

```bash
gcloud iam service-accounts create finance-research-worker --display-name="Finance Research Worker"
```

### Secrets created

At minimum, the following secrets were created and are now in use:

- `execution-internal-auth-token`
- `execution-database-url`
- `google-oauth-client-secret-json`
- `google-oauth-token-json`
- `google-api-key`
- `finnhub-api-key`
- `alpha-vantage-api-key`
- `tavily-api-key`
- `fred-api-key`
- `sec-api-user-agent`
- `sec-contact-email`

Canonical command shapes:

```bash
gcloud secrets create <secret-name> --replication-policy=automatic
```

```bash
printf '%s' '<secret-value>' | gcloud secrets versions add <secret-name> --data-file=-
```

For the JSON secrets, files were uploaded with:

```bash
gcloud secrets versions add google-oauth-client-secret-json --data-file=credentials.json
```

```bash
gcloud secrets versions add google-oauth-token-json --data-file=token.json
```

### First backend image rollout (full backend deployment)

This earlier build and rollout occurred before the API-only HTTPS fix.

Confirmed earlier image:

- `us-central1-docker.pkg.dev/finance-research-agent/finance-research-backend/finance-research-backend:20260304-022339`
- Digest:
  - `sha256:833845389aa7be09c1f02858be8128559dc60a328b0ce27d9a025cfbd04d54f0`

This image is still the current worker job image.

The earlier rollout updated:

- `finance-research-api` (before the later API-only fix)
- `finance-research-worker`

### Scheduler created

Live scheduler resource:

- `projects/finance-research-agent/locations/us-central1/jobs/finance-research-dispatch`

Canonical command shape:

```bash
gcloud scheduler jobs create http finance-research-dispatch --location=us-central1 --schedule="* * * * *" --uri="https://finance-research-api-gfnc7q4q7a-uc.a.run.app/api/v1/internal/dispatch-next" --http-method=POST --headers="Authorization=Bearer <redacted>"
```

## App-Level Fixes Applied Before Or During Deployment

These code changes were part of making the backend production-safe and operational:

- Cloud Run-safe execution dispatch path
  - API no longer depends on a long-running in-process web worker for Cloud Run mode
- Shared execution state via Postgres
- Memo artifact publishing via GCS
- Writable Google OAuth JSON staging at runtime under `/tmp/google`
- Retry/backoff for transient Gemini failures
  - `503 UNAVAILABLE`
  - `600s` model invoke timeouts
- Final retry model fallback
  - third retry uses `gemini-2.5-pro`
- Memo URL scheme fix
  - API now respects `X-Forwarded-Proto` and emits `https://` memo URLs on Cloud Run

## Current Operational Status

As of this file:

- Local end-to-end smoke runs with memo succeeded for:
  - `MCD`
  - `JNJ`
- Deployed Cloud Run end-to-end execution succeeded for:
  - `PLTR`
- The deployed `PLTR` execution record now returns:
  - a valid Google Sheets URL
  - an `https://` memo PDF API URL

## Remaining Known Gap

The worker job is still on image `20260304-022339`, while the API is on `20260304-030500`.

That is safe for the current state because:

- the `20260304-030500` change only fixed API-side absolute URL generation for `memo_pdf_url`
- the worker does not generate that response field

If future code changes touch shared runtime logic, redeploy both the API service and the worker job together to keep them aligned.
