# Deploying a public instance

The point of a hosted instance is that someone can use the thing rather than
read about it. That means it is unauthenticated, which shapes every decision
below.

## The rule

**A public instance runs the `demo` provider.** It is not a formality: the
endpoint is open, and on a live provider every visitor would be spending real
model credits against your key with no cap. The app refuses to start with
`FILING_INTEL_PUBLIC_DEMO=true` and any provider other than `demo`.

Demo mode is still worth hosting. It hits **real SEC EDGAR** and quotes real
filings; what it lacks is a model, so it extracts passages by keyword overlap
instead of reasoning about them. The UI says so in a banner.

## Render (recommended)

`render.yaml` is a blueprint. From a Render account:

1. **New → Blueprint**, point it at this repository.
2. Set `FILING_INTEL_SEC_USER_AGENT` to something like
   `anita-portfolio/1.0 (you@example.com)`. EDGAR returns 403 without a
   contact address, so the blueprint marks it `sync: false` rather than
   shipping a placeholder that would fail confusingly.
3. Deploy.

The free plan sleeps after 15 minutes idle and takes roughly a minute to wake,
so the first request after a quiet period is slow. For a portfolio demo that is
an acceptable trade against a monthly bill.

## Hugging Face Spaces

Also free, no card, and does not sleep as aggressively. Create a Space with the
**Docker** SDK, point it at this directory, and set the same variables as
repository secrets. Spaces listens on port 7860, so override the command:

```
CMD ["uvicorn", "filing_intel.api.app:app", "--host", "0.0.0.0", "--port", "7860"]
```

## Anywhere else

The image is a plain container listening on `$PORT` (8000 by default) with a
`/healthz` endpoint. Nothing about it is platform-specific.

```bash
docker build -t filing-intel .
docker run -p 8000:8000 \
  -e FILING_INTEL_PROVIDER=demo \
  -e FILING_INTEL_PUBLIC_DEMO=true \
  -e FILING_INTEL_SEC_USER_AGENT="you/1.0 (you@example.com)" \
  filing-intel
```

## What is protected, and what is not

| | |
|---|---|
| Model spend | Structurally prevented — demo mode has no provider to bill |
| EDGAR politeness | Rate limited per client, and the client is capped at 6 research calls a minute |
| Memory | The limiter bounds how many clients it tracks; sessions and caches expire |
| Abuse | Only dampened. `X-Forwarded-For` is spoofable, so the limiter is a speed bump, not authentication |

If you ever want a live-model instance, put it behind auth and a spend cap
first. An open endpoint on a real API key is a bill waiting to happen.
