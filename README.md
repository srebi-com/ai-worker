# Srebi Analysis Worker

Local CLI worker that downloads incident evidence from Cloudflare R2, extracts keyframes, runs vision analysis, and writes results back to R2.

## Requirements
- Python 3.10+
- ffmpeg + ffprobe installed and on PATH

## Setup
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Environment
Create `.env.local` from the example and fill in secrets:
```
cp .env.example .env.local
```

Required vars:
- `R2_ACCOUNT_ID`
- `R2_ACCESS_KEY_ID`
- `R2_SECRET_ACCESS_KEY`
- `R2_BUCKET` (defaults to `srebi-incidents`)
- `OPENAI_API_KEY` (required for `--mode ai`)
- `OPENAI_MODEL` (optional, defaults to `gpt-4o-mini`)

## Usage
Dummy mode (no external API calls):
```bash
python worker.py --incident <INCIDENT_ID> --hint-start 3.0 --hint-end 5.0 --mode dummy
```
python worker.py --incident c43adeb6-c29c-468e-bfdd-d767354b54d0 --hint-start 3.0 --hint-end 5.0 --mode dummy


AI mode (calls OpenAI vision):
```bash
python worker.py --incident <INCIDENT_ID> --hint-start 3.0 --hint-end 5.0 --mode ai
```
python worker.py --incident 30da2ec7-3158-4c74-8da5-abcadf4dae6c --hint-start 3.0 --hint-end 5.0 --mode ai

Options:
- `--force` re-run even if analysis already completed
- `--max-frames` limit the number of keyframes (default 8)
- `--every-s` extraction interval (default 0.5 seconds)

## Outputs in R2
- `incidents/{incidentId}/derived/analysis.json`
- `incidents/{incidentId}/derived/keyframes/frame_###.jpg`
- (optional) `incidents/{incidentId}/derived/report_draft.md`

## Notes
- The bucket remains private; credentials are never written to disk.
- AI mode incurs API costs and requires a valid OpenAI API key.
- The analysis JSON is strict and stored under `meta.json` in `analysis`.
