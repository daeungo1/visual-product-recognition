from guide_api import consensus, guide_fit

GUIDES = {"A": "전면 패널을 열고 필터를 위로 당겨 분리합니다.", "B": "스탠드형 하단 커버를 엽니다."}


def v(gid, fit="match", quote=None, product_ok=True, task_ok=True):
    return {
        "guide_id": gid,
        "fit": fit,
        "quote": quote,
        "product_ok": product_ok,
        "task_ok": task_ok,
    }


def test_verified_quote_selects_guide():
    d = guide_fit.decide(
        [v("A", quote="필터를 위로 당겨 분리합니다"), v("B", "mismatch")], "A", GUIDES
    )
    assert d.chosen == "A" and d.status == "ok" and "B" in d.rejected


def test_invented_or_short_quote_is_rejected():
    assert (
        guide_fit.decide([v("A", quote="문서에 없는 문장입니다 정말로")], "A", GUIDES).chosen
        is None
    )
    assert guide_fit.decide([v("A", quote="필터")], "A", GUIDES).status == guide_fit.NO_GUIDE


def test_product_mismatch_and_unknown_ids_select_nothing():
    d = guide_fit.decide([v("A", "mismatch", product_ok=False), v("Z")], "Z", GUIDES)
    assert d.chosen is None and d.status == guide_fit.NO_GUIDE


def test_chosen_rejected_falls_back_only_to_single_survivor():
    ok_b = v("B", quote="스탠드형 하단 커버를 엽니다")
    assert (
        guide_fit.decide([v("A", quote="없는 문장 입니다 정말"), ok_b], "A", GUIDES).chosen == "B"
    )


def test_consensus_median_and_stability():
    r = consensus.aggregate(
        [[(0.1, 0.1, 0.3, 0.3)], [(0.11, 0.1, 0.31, 0.3)], [(0.12, 0.11, 0.32, 0.31)]]
    )
    assert (
        r["status"] == "ok"
        and r["regions"][0]["box"] == (0.11, 0.1, 0.31, 0.3)
        and r["regions"][0]["stable"]
    )


def test_consensus_flags_disagreement():
    r = consensus.aggregate([[(0, 0, 0.1, 0.1)], [(0.5, 0.5, 0.6, 0.6)], [(0, 0, 0.1, 0.1)]])
    assert r["regions"][0]["stable"] is False


def test_consensus_needs_strict_majority_counting_failures():
    box = [(0, 0, 0.1, 0.1)]
    assert consensus.aggregate([box, [], None])["status"] == "uncertain"
    assert consensus.aggregate([box, box, None])["status"] == "ok"
    assert consensus.aggregate([])["status"] == "uncertain"
