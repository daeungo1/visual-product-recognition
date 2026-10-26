"""Hand-authored original demo script; no real Samsung model or reference is registered."""

from fastapi import HTTPException

from guide_api.models import Guide, Step

DEMO_GUIDE = Guide(
    id="demo-aircon",
    target_id="original-demo-remote-v1",
    title="합성 에어컨: 냉방 24도",
    steps=[
        Step(
            id="power", button_id="power",
            instruction="두 번째 화면의 전원 버튼을 눌러 POWER ON으로 바꾸세요.",
            expected_display="POWER ON",
        ),
        Step(
            id="mode", button_id="mode",
            instruction="모드 버튼을 눌러 MODE COOL로 바꾸세요.",
            expected_display="MODE COOL",
        ),
        Step(
            id="temperature", button_id="temperature",
            instruction="온도 버튼을 눌러 TEMP 24로 바꾸세요.",
            expected_display="TEMP 24",
        ),
    ],
)


def get_guide(guide_id: str) -> Guide:
    """Return only explicitly registered demo guides."""
    if guide_id != DEMO_GUIDE.id:
        raise HTTPException(404, "Guide not registered; real product assets are unavailable.")
    return DEMO_GUIDE
