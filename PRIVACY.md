# Privacy Policy — AgentCheckpoint

## Open Source Version

The open source version of AgentCheckpoint collects **zero telemetry** and **zero data**.

- No analytics
- No tracking
- No crash reports
- No data is sent anywhere
- All checkpoint data stays on your infrastructure

This is a hard guarantee. There is no hidden telemetry in the codebase.

## Enterprise Version

The enterprise version offers an **opt-in** aggregate telemetry feature.

When explicitly enabled, it sends only:
- Step count per run
- Failure type (e.g., "RateLimitError")
- Step latency (milliseconds)
- Framework name (e.g., "langchain")
- Model name (e.g., "claude-3-opus")

**It NEVER sends:**
- Message content
- Tool inputs or outputs
- Retrieved documents
- API responses
- Any user or customer data

Telemetry is disabled by default and must be explicitly enabled by setting
`AGENTCHECKPOINT_TELEMETRY=true` in your environment.

## Data Storage

All checkpoint data is stored exclusively on infrastructure you control:
- Local disk (default)
- Your S3 bucket / R2 bucket / MinIO instance
- Your PostgreSQL database

AgentCheckpoint never has access to your checkpoint data unless you
explicitly grant it. The self-hosted dashboard connects to *your* storage
with credentials *you* provide.

## Questions?

Email: privacy@agentcheckpoint.dev
