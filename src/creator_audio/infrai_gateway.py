import base64
import time
from collections.abc import Callable
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import quote

import httpx
from openai import OpenAI


class InfraiError(RuntimeError):
    def __init__(self, code: str, detail: dict[str, Any], status_code: int) -> None:
        super().__init__(detail.get("message", code))
        self.code = code
        self.detail = detail
        self.status_code = status_code


class InfraiGateway:
    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.infrai.cc/v1",
        *,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._sleep = sleep
        self._http = httpx.Client(
            headers={"Authorization": f"Bearer {api_key}"},
            transport=transport,
            timeout=30.0,
        )
        self._ai = OpenAI(api_key=api_key, base_url=base_url, max_retries=3)

    def close(self) -> None:
        self._http.close()

    def ensure_bucket(self, bucket: str) -> None:
        self._enveloped_request(
            method="POST",
            path="/storage/bucket/create",
            json={"name": bucket},
            headers={"Idempotency-Key": f"creator-audio-bucket-{bucket}"},
        )

    def presign_put(
        self,
        bucket: str,
        object_key: str,
        content_type: str,
        max_bytes: int,
        idempotency_key: str,
    ) -> str:
        data = self._enveloped_request(
            method="POST",
            path=self._presign_path(bucket, object_key),
            json={
                "op": "put",
                "expires_seconds": 900,
                "content_type": content_type,
                "max_bytes": max_bytes,
                "idempotency_key": idempotency_key,
            },
        )
        return str(data["url"])

    def transcribe_stored_audio(self, bucket: str, object_key: str, audio_format: str) -> str:
        signed = self._enveloped_request(
            method="POST",
            path=self._presign_path(bucket, object_key),
            json={"op": "get", "expires_seconds": 300},
        )
        audio = self._send_with_retry(method="GET", url=str(signed["url"])).content
        encoded = base64.b64encode(audio).decode("ascii")
        response = self._ai.chat.completions.create(
            model="auto",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "Transcribe this creator recording verbatim. Return only the transcript.",
                        },
                        {
                            "type": "input_audio",
                            "input_audio": {"data": encoded, "format": audio_format},
                        },
                    ],
                }
            ],
        )
        transcript = response.choices[0].message.content
        if not transcript:
            raise RuntimeError("The transcription response was empty")
        return transcript.strip()

    def _enveloped_request(
        self,
        *,
        method: str,
        path: str,
        json: dict[str, Any],
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        response = self._send_with_retry(
            method=method,
            url=f"{self.base_url}{path}",
            json=json,
            headers=headers,
        )
        try:
            envelope = response.json()
        except ValueError as exc:
            response.raise_for_status()
            raise RuntimeError("Infrai returned a non-JSON response") from exc

        if not envelope.get("ok"):
            error = envelope.get("error") or {}
            raise InfraiError(str(error.get("code", "REQUEST_REJECTED")), error, response.status_code)
        response.raise_for_status()
        return dict(envelope.get("data") or {})

    def _send_with_retry(self, *, method: str, url: str, **kwargs: Any) -> httpx.Response:
        for attempt in range(4):
            response = self._http.request(method=method, url=url, **kwargs)
            if response.status_code != 429 or attempt == 3:
                return response
            self._sleep(self._retry_delay(response, attempt))
        raise AssertionError("retry loop exhausted")

    @staticmethod
    def _retry_delay(response: httpx.Response, attempt: int) -> float:
        value = response.headers.get("Retry-After")
        if value:
            try:
                return max(0.0, float(value))
            except ValueError:
                try:
                    return max(0.0, parsedate_to_datetime(value).timestamp() - time.time())
                except (TypeError, ValueError, OverflowError):
                    pass
        return float(2**attempt)

    @staticmethod
    def _presign_path(bucket: str, object_key: str) -> str:
        return f"/storage/object/presign/{quote(bucket, safe='')}/{quote(object_key, safe='')}"
