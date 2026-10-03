from creator_audio.commerce_processor import CommerceAction, ProcessingState, decide_next_step


def test_delivery_request_releases_asset_and_schedules_subscriber_update() -> None:
    decision = decide_next_step(
        "The edit is approved. Deliver the download and notify all subscribers this afternoon."
    )

    assert decision.action is CommerceAction.DELIVER_ASSET
    assert decision.processing_state is ProcessingState.READY
    assert decision.notify_subscribers is True


def test_unclear_recording_stays_in_review_without_exposing_asset() -> None:
    decision = decide_next_step("I recorded a rough introduction for the course.")

    assert decision.action is CommerceAction.REVIEW_TRANSCRIPT
    assert decision.processing_state is ProcessingState.NEEDS_REVIEW
    assert decision.notify_subscribers is False
