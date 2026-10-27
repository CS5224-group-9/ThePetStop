# Facility ingestion operations

The same handlers run locally in Floci and in the optional CDK ingestion stack. Fetch/geocode/reconcile/failure capture run outside the AWS VPC. Only the load/status function enters the existing isolated subnets and reads the RDS/Django secrets. SQS FIFO uses one message group across both registries; no Celery service is required.

Loader concurrency is capped at two to bound its PostgreSQL connections during
status replays. Geocoding and reconciliation each have concurrency one. Status
events remain queued for delivery while the loader is busy.

## Run history and data safety

Supply a UUID `run_id` on manual starts. Scheduled starts derive a stable UUID from the EventBridge execution ID, so Lambda retries reuse the run. Fetch takes a conditional S3 lease before changing its manifest. Each stage writes immutable events under `status/<source>/<run_id>/`; the load function projects these into `FacilitySyncRun` and `FacilitySyncEvent`. Duplicate or reordered status deliveries cannot regress a successful run. Run progress and event history are read-only in Django admin.

The ready-snapshot loader serializes writes per source inside a PostgreSQL transaction. Failed writes roll back, repeated snapshots are idempotent, and an earlier retrieved snapshot cannot replace a later successful one. A snapshot that would deactivate more than `FACILITY_MAX_DEACTIVATION_FRACTION` of active source facilities (default 0.2) is marked `review_required`; the previous dataset stays active. Review the raw PDF, parsed artifact and snapshot before approving its exact digest. This guard also catches identity churn when a parser change alters many source keys.

Resolved geocodes are cached for `GEOCODE_CACHE_MAX_AGE_DAYS` (default 90). Per-run query checkpoints survive retries independently of that cache. A complete snapshot is published only after every expected query and batch validates, using a conditional S3 write to handle competing finalizers.

## Failure and recovery contract

| Failure | Behavior |
| --- | --- |
| AVS network/server error or 429 | Bounded HTTP retries, jitter, and Retry-After for short waits; subsequent invocation/reconciliation retries retain the run ID |
| Invalid PDF, source URL, or schema | Terminal failed event and artifact; requires a corrected source/parser and an explicit operator retry |
| OneMap 401/403 | One token renewal, with authentication and fallback calls included in pacing |
| OneMap 429/network/5xx | Persist cooldown and completed queries; fail the SQS delivery and request a deferred visibility window |
| Invalid queue payload/configuration | Retain the message in `quarantine/`, record a permanent failure when its identity is valid, and acknowledge it so it cannot block the FIFO group indefinitely |
| Repeated transient SQS failure/timeout | Work queue redrives after five receives to its FIFO DLQ; the reconciler archives each message under `work-failures/`, records failure, and only then acknowledges the DLQ message |
| Fetch/load/reconcile async retries exhausted | Standard failure queue; failure-capture Lambda archives the invocation envelope in S3. Its own delivery failures have a separate DLQ in AWS |
| Database unavailable | Original exception remains visible; status stays durable in S3. No load receipt is written until the database transaction commits |
| Missing status/ready notification | Reconciler re-emits unprojected status events and ready snapshots without a `loaded/` receipt |
| Partial dispatch or interrupted finalization | Reconciler requeues unfinished work or reruns finalization using persisted artifacts |
| Excessive deactivation | Staff review required; automatic retries do not approve it |

Automatic reconciliation runs every 15 minutes when schedules are enabled. It waits at least 15 minutes before repairing new runs, resets the retry budget when batch progress advances, and bounds unsuccessful recovery to five attempts and `FACILITY_MAX_RUN_AGE_HOURS` (default 24). Permanent failures stay stopped until an operator requests retry. A successful load writes `loaded/<source>/<run_id>.json` after committing; replay is safe if receipt writing itself fails.

Inspect `failed/`, `quarantine/`, `work-failures/`, `invocation-failures/`, SQS DLQs, and the run's admin events when investigating. Exceptions contain safe codes, not upstream bodies or credentials. Structured logs include run/source/stage/batch IDs. CloudWatch metrics track failures, quarantine and dataset age; alarms cover Lambda errors, old work, DLQs, and data older than eight days. After a DLQ message is archived, retry uses the original run manifest rather than requiring that queue message to remain available.

The single FIFO group serializes ingestion pacing at 75 attempts/minute. Interactive OneMap traffic uses its own client, so it also contributes to the provider's account quota. The initial 75 limit leaves headroom; it is not a global account-wide quota coordinator.

## Local live runs

Always include the overlay when starting PostgreSQL for ingestion. Starting only the base Compose file can recreate PostgreSQL without its ingestion-network attachment.

```powershell
docker compose -f docker-compose.yml -f compose.ingestion.yml --profile ingestion up -d db floci
uv run --project backend python backend/manage.py migrate
docker build --platform linux/amd64 -t petstop-backend:ingestion-local backend
uv run --project backend python scripts/facilities/bootstrap_local.py --endpoint-url http://localhost:4566 --image petstop-backend:ingestion-local
uv run --project backend python scripts/facilities/integration_local.py --endpoint-url http://localhost:4566 --source both
```

The bootstrap preserves bucket contents, queue work and database rows. Re-run it after rebuilding the image; rebuilding a tag alone does not update a running Lambda container. Floci is pinned by digest in Compose; set `FLOCI_IMAGE` only when deliberately validating another version. The pin was obtained from the running image rather than guessed.

Use `--source vet --run-id <uuid>` to resume a partial dispatch. For full recovery invoke `petstop-facility-reconcile-local` with `{"source":"vet","run_id":"<uuid>"}`. An explicit `"operation":"retry"` clears the terminal run marker and reuses its checkpoints; inspect and redrive/archive the related DLQ messages as part of that intervention. For a general reconciliation invoke it with `{}`. Local schedules are not created automatically; call this function manually while developing.

For count-drop review, configure the host's `AWS_ENDPOINT_URL=http://localhost:4566` and dummy AWS credentials, then run:

```powershell
uv run --project backend python backend/manage.py approve_facility_snapshot --source vet --run-id <uuid> --snapshot-sha256 <reviewed-digest>
```

This command records approval for that digest and re-emits the ready object. It does not disable the guard for other runs. Inspect the run's final counts afterward.

## Deterministic Floci verification

Use the separate fixture database on port 5434. Fixture resources use `-fixture` names and fake credentials; live resource names and the existing PostgreSQL volume are separate. Run suites serially. The temporary database is held in tmpfs and is discarded when its container is removed.

```powershell
docker build --platform linux/amd64 -t petstop-backend:ingestion-local backend
docker compose -f docker-compose.yml -f compose.ingestion.yml --profile ingestion-fixtures up -d fixtures ingestion-db
uv run --project backend python scripts/facilities/bootstrap_local.py --endpoint-url http://localhost:4566 --image petstop-backend:ingestion-local --fixture-mode
uv run --project backend python scripts/facilities/integration_fixtures.py --reset-queues
```

`--reset-queues` explicitly purges only the suite's fixture queues before running. It is useful after an interrupted suite and must not be used while another suite is running. The suite checks exact generated records, 429 redelivery, token renewal, malformed PDF preservation, duplicate ready delivery and recovery after temporarily misconfiguring only the fixture loader's database connection. It waits for actual SQS/S3 triggers; it does not call the geocoder or loader directly.

The fixture worker timeout is 15 seconds and work visibility is 90 seconds, preserving a six-times ratio while keeping failed-delivery checks bounded. The live/AWS values are 120 and 900 seconds. Emulation does not establish AWS delivery timing or IAM correctness.

The pinned Floci image can leave a reused HTTP connection invalid after rejecting
a conditional PUT, causing a later request to return HTTP 400. Emulator S3 clients
send `Connection: close` to avoid that transport issue. The capability probe
requires the correct 412 precondition response, verifies a successful matching
write, and checks that rejected creates/updates preserve the original contents.
AWS clients keep their normal connection pooling. No read-then-overwrite fallback
is used.

Floci also drops direct S3-to-Lambda notices when reserved concurrency is full.
The suite invokes the actual reconciler after a malformed fetch to verify that
its durable failed event is projected even if the first notice was lost. Keep
the loader's database concurrency limit; use reconciliation to repair missing
notices. Local schedules are manual, while the disabled AWS stack includes the
15-minute reconciliation rule for activation after staging acceptance.

Backend unit/database tests additionally inject partial dispatch, an interrupted query batch, rollback, stale snapshots, out-of-order status and count-drop approval. CI runs Django tests with PostgreSQL and the pinned Floci fixture suite without real credentials or live endpoints.

## AWS handoff and release gate

The CDK stack is opt-in so the existing `deploy --all` workflow does not provision it accidentally:

```powershell
cd infra
yarn build
yarn test --runInBand
yarn cdk synth -c facilityIngestion=true
yarn cdk diff -c facilityIngestion=true
# Deployment is performed by the infrastructure owner after reviewing the diff.
```

The stack outputs the artifact bucket, OneMap secret ARN, alert topic ARN, operator policy ARN, and fetch/reconcile names. Before production use:

1. Apply backend migrations through the existing management Lambda.
2. Populate the OneMap secret with `email` and `password` (and optionally `access_token`) through Secrets Manager. Do not place values in CDK context or Git.
3. Subscribe the team's monitored destination to the alert topic and confirm the subscription. An unconfigured topic cannot notify anyone.
   Dataset-age alarms also detect missing health reports; an uninitialized or
   disabled pipeline can therefore show stale-data alarms until its first sync
   and reconciliation report.
4. Attach the output recovery-operator policy to the approved operator role. It allows reviewed snapshot approval and invoking reconciliation. The general API role is not given these privileges.
5. Run a manual AWS sync and inspect the first dataset before public use. Verify actual IAM, secret reads, private RDS access, async destinations, DLQ redrive and a controlled outage/replay on a staging dataset.
6. Enable the weekly rules and 15-minute reconciliation only after those checks pass. Schedules are disabled in code by default. Weekly source starts use separate UTC hours; record the desired business schedule before changing them.

Keep versioned raw documents, snapshots and invocation failures for investigation. The bucket is retained on stack deletion; cache objects expire after 90 days and old object versions after 30 days. Choose any additional primary-artifact retention policy with the team instead of deleting evidence during recovery.

Production readiness requires verified alerts and recovery on AWS. Local green checks establish application behavior and emulator integration, not AWS acceptance.

## Verification record — 28 October 2026

- All 38 backend tests pass with PostgreSQL 16; migration generation reports no drift.
- All 10 CDK template tests, TypeScript checks and formatting checks pass.
- The pinned Floci fixture suite passes strict conditional writes, duplicate
  starts, exact records, expired-token renewal, 429 redelivery, malformed PDF
  preservation, lost-status reconciliation, duplicate loads, database-outage
  replay, durable DLQ archival and invocation-failure capture with loader
  concurrency capped at two.
- The local migration and function updates were applied. The live local database
  retains 125 vets and 340 pet shops. Its geocoder remains at 75 attempts/minute.
- No AWS deployment or schedule activation was performed. The GitHub workflow
  was updated; the recorded checks were run locally rather than on GitHub.
