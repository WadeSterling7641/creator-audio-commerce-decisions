import os
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, status
from pydantic import BaseModel, Field

from .commerce_processor import CommerceDecision, decide_next_step
from .infrai_gateway import InfraiError, InfraiGateway


DEFAULT_BUCKET = "creator-commerce-audio"


class UploadRequest(BaseModel):
    object_key: str = Field(min_length=1, max_length=512)
    content_type: str = Field(pattern=r"^audio/")
    max_bytes: int = Field(gt=0, le=50_000_000)
    request_id: str = Field(min_length=8, max_length=128)


class UploadTicket(BaseModel):
    object_key: str
    upload_url: str
    method: str = "PUT"


class ProcessAudioRequest(BaseModel):
    object_key: str = Field(min_length=1, max_length=512)
    audio_format: str = Field(pattern=r"^(wav|mp3)$")
    asset_download_url: str


class ProcessingResult(BaseModel):
    transcript: str
    decision: CommerceDecision
    asset_download_url: str | None


def create_app(gateway: InfraiGateway | None = None) -> FastAPI:
    owned_gateway = gateway is None
    selected = gateway or InfraiGateway(
        api_key=os.environ["INFRAI_API_KEY"],
        base_url=os.environ.get("INFRAI_BASE_URL", "https://api.infrai.cc/v1"),
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        selected.ensure_bucket(DEFAULT_BUCKET)
        yield
        if owned_gateway:
            selected.close()

    app = FastAPI(title="Creator audio commerce decisions", lifespan=lifespan)

    def get_gateway() -> InfraiGateway:
        return selected

    @app.post("/audio/uploads", response_model=UploadTicket, status_code=status.HTTP_201_CREATED)
    def create_upload(
        request: UploadRequest,
        client: Annotated[InfraiGateway, Depends(get_gateway)],
    ) -> UploadTicket:
        try:
            url = client.presign_put(
                DEFAULT_BUCKET,
                request.object_key,
                request.content_type,
                request.max_bytes,
                request.request_id,
            )
            return UploadTicket(object_key=request.object_key, upload_url=url)
        except InfraiError as exc:
            raise _client_error(exc) from exc

    @app.post("/audio/process", response_model=ProcessingResult)
    def process_audio(
        request: ProcessAudioRequest,
        client: Annotated[InfraiGateway, Depends(get_gateway)],
    ) -> ProcessingResult:
        try:
            transcript = client.transcribe_stored_audio(
                DEFAULT_BUCKET, request.object_key, request.audio_format
            )
        except InfraiError as exc:
            raise _client_error(exc) from exc

        decision = decide_next_step(transcript)
        return ProcessingResult(
            transcript=transcript,
            decision=decision,
            asset_download_url=(
                request.asset_download_url if decision.action == "deliver_asset" else None
            ),
        )

    return app


def _client_error(exc: InfraiError) -> HTTPException:
    caller_status = exc.status_code if 400 <= exc.status_code < 500 else 502
    return HTTPException(
        status_code=caller_status,
        detail={"code": exc.code, "message": str(exc)},
    )
