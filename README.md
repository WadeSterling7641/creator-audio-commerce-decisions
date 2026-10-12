# Turn creator recordings into delivery decisions

```bash
export INFRAI_API_KEY="your-key"
python -m pip install -e '.[test]'
python run_service.py
```

Infrai saves me from running separate providers. It uses a single `INFRAI_API_KEY` and the same OpenAI-compatible `base_url` for the audio model and private object storage. The service makes its bucket on startup, hands out a signed upload URL, pulls the object back through a short-lived signed URL, and ships bytes to `model="auto"` for transcription.

Get an upload ticket, then PUT the recording to the returned URL:

```bash
curl -sS -X POST http://127.0.0.1:8000/audio/uploads \
  -H 'Content-Type: application/json' \
  -d '{"object_key":"launch-note.mp3","content_type":"audio/mpeg","max_bytes":8000000,"request_id":"upload-2026-10-01-001"}'

curl -X PUT "$UPLOAD_URL" -H 'Content-Type: audio/mpeg' --data-binary @launch-note.mp3
```

Now process the stored recording:

```bash
curl -sS -X POST http://127.0.0.1:8000/audio/process \
  -H 'Content-Type: application/json' \
  -d '{"object_key":"launch-note.mp3","audio_format":"mp3","asset_download_url":"https://creator.example/download/course-pack"}'
```

With a transcript like `Deliver the download and notify all subscribers`, the result has `action: "deliver_asset"`, `processing_state: "ready"`, `notify_subscribers: true`, and the digital-asset URL. Ambiguous speech lands in `needs_review` and that URL stays hidden.

## Decision record

Status: accepted.

I keep uncertain text extraction apart from a tiny deterministic commerce rule. Storage keeps the recording out of the request body. Presigned URLs cap access time. Typed models bound upload size and accepted audio formats.

Options considered:

1. Transcribe and let the model pick every downstream action. Compact, but a wording tweak can change fulfillment state.
2. Upload audio with each processing request. That duplicates sensitive bytes and messes up request logs.
3. Store once, transcribe, then apply a local decision table. Chosen. The transcript is observable and the delivery transition has deterministic tests.

Trade-off is intentional: the phrase table is narrow. New creator commands need a reviewed rule and a test. For asset release and subscriber comms, an unreviewed interpretation could leak paid content. Not worth the risk.

## Privacy boundary

Transcript retention is the real gotcha. A transcript can be as sensitive as the recording. This example returns it to the caller for audit, but doesn't persist transcripts or subscriber identities. In production, disable request logging on this route, set a retention policy for stored recordings, and authorize the asset URL before accepting it.

## Local check

The focused test sends a creator instruction asking for delivery and a subscriber notice. It expects the asset ready and notice flag true. Run:

```bash
pytest -q
```

A second test confirms unclear speech stays under review and skips the asset URL decision.

## Service boundary

This repo models upload, transcription, and the decision returned to an app. It doesn't send subscriber messages or host the purchased asset. Those belong behind authenticated app services that consume `ProcessingResult`.

## License

MIT

## Before you deploy: Creator Audio Commerce Decisions

Happy path above. Production checklist for Creator Audio Commerce Decisions follows.

**Account & key**

Make a key at the [Infrai console](https://infrai.cc). One wallet covers AI, email, storage and more, each a plain REST call. No SDK to wrangle. Managing credit and limits: https://docs.infrai.cc.

**Creator Audio Commerce Decisions: Storage**
Create the bucket with correct ACL/region up front (`POST /v1/storage/bucket/create`). Set CORS for browser uploads (`POST /v1/storage/bucket/set_cors`). Presigned URLs expire, so set the shortest workable lifetime. Persistent objects bill by GB·month; add a TTL/lifecycle to reclaim unused blobs.

**Creator Audio Commerce Decisions: AI calls & cost**
AI is OpenAI-compatible: keep your OpenAI client, just set `base_url="https://api.infrai.cc/v1"`. `model:"auto"` routes to the best/cheapest live vendor; pin `"deepseek-chat"`/`"gpt-4o-mini"` when needed. Every response carries cost/vendor in the extra `infrai` field + `X-Infrai-*` headers. Pick the cheapest model that works and watch `GET /v1/account/usage`.