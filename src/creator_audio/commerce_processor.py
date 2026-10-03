from dataclasses import dataclass
from enum import StrEnum


class CommerceAction(StrEnum):
    DELIVER_ASSET = "deliver_asset"
    REVIEW_TRANSCRIPT = "review_transcript"


class ProcessingState(StrEnum):
    READY = "ready"
    NEEDS_REVIEW = "needs_review"


@dataclass(frozen=True)
class CommerceDecision:
    action: CommerceAction
    processing_state: ProcessingState
    notify_subscribers: bool


def decide_next_step(transcript: str) -> CommerceDecision:
    """Turn creator intent into an explicit, auditable state transition."""
    normalized = transcript.casefold()
    delivery_words = ("deliver", "download", "send the asset", "release the file")
    subscriber_words = ("subscriber", "members", "newsletter", "notify everyone")
    deliver = any(word in normalized for word in delivery_words)

    return CommerceDecision(
        action=CommerceAction.DELIVER_ASSET if deliver else CommerceAction.REVIEW_TRANSCRIPT,
        processing_state=ProcessingState.READY if deliver else ProcessingState.NEEDS_REVIEW,
        notify_subscribers=deliver and any(word in normalized for word in subscriber_words),
    )
