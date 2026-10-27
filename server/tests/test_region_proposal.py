import json

from guide_api.region_proposal import parse_regions

NAMES = ["power", "dial"]


def item(**over):
    base = {
        "component": "power",
        "point": [0.5, 0.5],
        "box": [0.4, 0.4, 0.6, 0.6],
        "visible": True,
    }
    return {**base, **over}


def parse(*items):
    return parse_regions(json.dumps({"regions": list(items)}), NAMES)


def test_valid_region_kept():
    assert parse(item())[0].component == "power"


def test_rejects_malformed_and_unknown():
    assert parse_regions("not json", NAMES) == []
    assert parse(item(component="other")) == []
    assert parse(item(visible=False)) == []
    assert parse(item(point=[1.5, 0.5])) == []
    assert parse(item(box=[0.6, 0.4, 0.4, 0.6])) == []
    assert parse(item(point=[0.9, 0.9])) == []


def test_duplicates_keep_first():
    first = item(point=[0.45, 0.45])
    assert len(parse(first, item())) == 1
    assert parse(first, item())[0].point == (0.45, 0.45)
