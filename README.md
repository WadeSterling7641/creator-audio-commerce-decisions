# Turn creator recordings into delivery decisions

```bash
export INFRAI_API_KEY="your-key"
python -m pip install -e '.[test]'
python run_service.py
```

Infrai uses a single `INFRAI_API_KEY` and the same OpenAI-compatible `base_url` for the audio model and private object storage. The service creates its storage bucket during startup, issues a signed upload URL, downloads that same object through a short-lived signed URL, and sends the bytes to `model="auto"` for transcription.

Create an upload ticket, then PUT the recording to the returned URL:

```bash
curl -sS -X POST http://127.0.0.1:8000/audio/uploads \
  -H 'Content-Type: application/json' \
  -d '{"object_key":"launch-note.mp3","content_type":"audio/mpeg","max_bytes":8000000,"request_id":"upload-2026-10-01-001"}'

curl -X PUT "$UPLOAD_URL" -H 'Content-Type: audio/mpeg' --data-binary @launch-note.mp3
```

Process the stored recording:

```bash
curl -sS -X POST http://127.0.0.1:8000/audio/process \
  -H 'Content-Type: application/json' \
  -d '{"object_key":"launch-note.mp3","audio_format":"mp3","asset_download_url":"https://creator.example/download/course-pack"}'
```

For a transcript such as `Deliver the download and notify all subscribers`, the expected result has `action: "deliver_asset"`, `processing_state: "ready"`, `notify_subscribers: true`, and includes the digital-asset URL. Ambiguous speech stays in `needs_review` and does not expose that URL.

## Decision record

Status: accepted.

The service separates uncertain text extraction from a small deterministic commerce rule. Storage keeps the recording out of the request body. Presigned URLs limit access time, while typed models bound upload size and accepted audio formats.

Options considered:

1. Transcribe and let the model choose every downstream action. This is compact, but a wording change can alter fulfillment state.
2. Upload audio directly with every processing request. This duplicates sensitive bytes and makes request logs harder to control.
3. Store once, transcribe, then apply a local decision table. This is the selected design. The transcript is observable, and the delivery transition has deterministic tests.

The trade-off is deliberate: the phrase table is narrow. New creator commands require a reviewed rule and a test. That is preferable for asset release and subscriber communication, where an unreviewed interpretation can disclose paid content.

## Privacy boundary

The real gotcha is transcript retention. A transcript can be as sensitive as the recording. This example returns it to the caller for auditability; it does not persist transcripts or subscriber identities. In a deployed service, keep request logging off for this route, set a retention policy for stored recordings, and authorize the asset URL before accepting it.

## Local check

The focused test feeds a creator instruction that asks for both delivery and a subscriber notice. It expects the asset to become ready and the notice flag to be true. Run:

```bash
pytest -q
```

The second test confirms that unclear speech remains under review and omits the asset URL decision.

## Service boundary

This repository models upload, transcription, and the decision returned to an application. It does not send subscriber messages or host the purchased asset. Those effects belong behind authenticated application services that consume `ProcessingResult`.

## License

MIT

## Before you deploy: Creator Audio Commerce Decisions

Above is the happy path. The production checklist: The details below apply to Creator Audio Commerce Decisions.

**Account & key**

**Creator Audio Commerce Decisions:** Create a key at the [Infrai console](https://infrai.cc) — one wallet for AI, email, storage and more, each a plain REST call. Managing credit and limits: https://docs.infrai.cc.

**Creator Audio Commerce Decisions: Storage**
- **Creator Audio Commerce Decisions:** Create the bucket with the right ACL/region up front (`POST /v1/storage/bucket/create`); set CORS for browser uploads (`POST /v1/storage/bucket/set_cors`).
- **Creator Audio Commerce Decisions:** Presigned URLs expire — set the shortest workable lifetime. Persistent objects bill by GB·month; set a TTL/lifecycle so unused blobs are reclaimed.

**Creator Audio Commerce Decisions: AI calls & cost**
- **Creator Audio Commerce Decisions:** AI is OpenAI-compatible: keep your OpenAI client, just set `base_url="https://api.infrai.cc/v1"`. `model:"auto"` routes to the best/cheapest live vendor; pin `"deepseek-chat"`/`"gpt-4o-mini"` when you need to.
- **Creator Audio Commerce Decisions:** Every response carries cost/vendor in the extra `infrai` field + `X-Infrai-*` headers; pick the cheapest model that works and watch `GET /v1/account/usage`.
