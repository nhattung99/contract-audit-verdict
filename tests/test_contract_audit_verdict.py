import json
import pytest

REPORT = "https://github.com/examplesec/audits/blob/main/treasury-v2.md"
SOURCE = "https://github.com/dao/treasury/blob/main/Treasury.sol"

def _submit(contract, direct_vm, who):
    with direct_vm.prank(who):
        return contract.submit_review(
            "Treasury v2", "ExampleSec", REPORT, SOURCE)

def _mock_web(vm, pattern, body):
    vm.mock_web(pattern, {"body": body, "status": 200, "headers": {}})


def _mock_pages(direct_vm, report_text, source_text):
    _mock_web(direct_vm, r".*examplesec.*", report_text)
    _mock_web(direct_vm, r".*dao/treasury.*", source_text)

LONG_REPORT = ("Audit of Treasury v2. Scope: Treasury.sol commit abc123. "
               "Tools: Slither, Foundry fuzzing, 3 weeks manual review by "
               "4 auditors. Findings: H-01 reentrancy in withdraw() with "
               "PoC test. M-01 missing timelock on setOwner(). "
               "Remediation: apply checks-effects-interactions; fix "
               "re-review completed. " * 3)
SOURCE_TEXT = ("contract Treasury { function withdraw(uint a) external "
               "{ payable(msg.sender).transfer(a); } function setOwner(address o) external { owner = o; } }" * 2)

def test_thorough_grade_and_computed_overall(direct_vm, direct_deploy,
                                              direct_alice):
    contract = direct_deploy("contracts/contract_audit_verdict.py")
    rid = _submit(contract, direct_vm, direct_alice)
    assert rid == "1"
    assert contract.get_count() == 1

    _mock_pages(direct_vm, LONG_REPORT, SOURCE_TEXT)
    direct_vm.mock_llm(r".*audit reviewer.*", json.dumps({
        "score_coverage": 90, "score_findings": 85,
        "score_severity": 80, "score_remediation": 75,
        "score_methodology": 95,
        "confidence": 88,
        "reasoning": "Report covers withdraw and setOwner with PoC and "
                     "discloses scope, commit, tools and team.",
        "missing_coverage": ["upgrade path not discussed"]
    }))

    contract.assess_audit(rid)

    r = json.loads(contract.get_assessment(rid))
    assert r["overall_score"] == (90 + 85 + 80 + 75 + 95) // 5, r["reasoning"]
    assert r["grade"] == "THOROUGH"
    assert r["criteria"]["coverage"] == 90
    assert r["criteria"]["methodology"] == 95
    assert r["gap_count"] == 1
    assert json.loads(r["missing_coverage"]) == ["upgrade path not discussed"]
    assert r["source_readable"] is True
    assert json.loads(contract.get_review(rid))["status"] == "ASSESSED"


def test_superficial_grade(direct_vm, direct_deploy, direct_alice):
    contract = direct_deploy("contracts/contract_audit_verdict.py")
    rid = _submit(contract, direct_vm, direct_alice)
    _mock_pages(direct_vm, LONG_REPORT, SOURCE_TEXT)
    direct_vm.mock_llm(r".*audit reviewer.*", json.dumps({
        "score_coverage": 20, "score_findings": 25,
        "score_severity": 30, "score_remediation": 15,
        "score_methodology": 10, "confidence": 80,
        "reasoning": "Generic checklist output, no PoC, no scope.",
        "missing_coverage": ["no access control review",
                             "no external call analysis"]
    }))
    contract.assess_audit(rid)
    r = json.loads(contract.get_assessment(rid))
    assert r["grade"] == "SUPERFICIAL"
    assert r["overall_score"] == 20
    assert r["gap_count"] == 2



def test_report_unreadable_unassessable(direct_vm, direct_deploy,
                                         direct_alice):
    contract = direct_deploy("contracts/contract_audit_verdict.py")
    rid = _submit(contract, direct_vm, direct_alice)
    # report fetch raises / returns empty; source is fine
    _mock_web(direct_vm, r".*examplesec.*", "")
    _mock_web(direct_vm, r".*dao/treasury.*", SOURCE_TEXT)
    # Even if an LLM mock claims THOROUGH it must be ignored
    direct_vm.mock_llm(r".*audit reviewer.*", json.dumps({
        "score_coverage": 99, "score_findings": 99, "score_severity": 99,
        "score_remediation": 99, "score_methodology": 99,
        "confidence": 99, "reasoning": "x", "missing_coverage": []}))
    contract.assess_audit(rid)
    full = json.loads(contract.get_review(rid))
    assert full["status"] == "UNASSESSABLE"
    assert full["grade"] == "UNASSESSABLE"
    assert full["overall_score"] == 0

def test_source_unreadable_caps_coverage(direct_vm, direct_deploy,
                                          direct_alice):
    contract = direct_deploy("contracts/contract_audit_verdict.py")
    rid = _submit(contract, direct_vm, direct_alice)
    _mock_web(direct_vm, r".*examplesec.*", LONG_REPORT)
    _mock_web(direct_vm, r".*dao/treasury.*", "")      # unreadable
    direct_vm.mock_llm(r".*audit reviewer.*", json.dumps({
        "score_coverage": 95, "score_findings": 80, "score_severity": 80,
        "score_remediation": 80, "score_methodology": 80,
        "confidence": 70, "reasoning": "ok", "missing_coverage": []}))
    contract.assess_audit(rid)
    r = json.loads(contract.get_assessment(rid))
    assert r["criteria"]["coverage"] == 50
    assert r["source_readable"] is False
    assert r["gap_count"] >= 1
    assert any("unreadable" in m for m in json.loads(r["missing_coverage"]))











def test_empty_contract_name(direct_vm, direct_deploy, direct_alice):
    c = direct_deploy("contracts/contract_audit_verdict.py")
    with direct_vm.prank(direct_alice):
        with direct_vm.expect_revert("contract_name cannot be empty"):
            c.submit_review("", "ExampleSec", REPORT, SOURCE)






def test_get_assessment_pending(direct_vm, direct_deploy, direct_alice):
    c = direct_deploy("contracts/contract_audit_verdict.py")
    rid = _submit(c, direct_vm, direct_alice)
    with direct_vm.expect_revert("Not yet assessed"):
        c.get_assessment(rid)






KEYS = ["score_coverage", "score_findings", "score_severity",
        "score_remediation", "score_methodology"]


def _payload(scores=(80, 80, 80, 80, 80), **updates):
    result = dict(zip(KEYS, scores))
    result.update(confidence=85, reasoning="Specific report evidence.",
                  missing_coverage=["upgrade path not discussed"])
    result.update(updates)
    return result


def _assess(c, vm, alice, payload=None, report=LONG_REPORT, source=SOURCE_TEXT):
    rid = _submit(c, vm, alice)
    vm.clear_mocks()
    _mock_pages(vm, report, source)
    vm.mock_llm(r".*audit reviewer.*", json.dumps(payload or _payload()))
    c.assess_audit(rid)
    return rid, json.loads(c.get_assessment(rid))


def test_adequate_grade(direct_vm, direct_deploy, direct_alice):
    c = direct_deploy("contracts/contract_audit_verdict.py")
    _, r = _assess(c, direct_vm, direct_alice, _payload((60, 55, 50, 60, 65)))
    assert (r["grade"], r["overall_score"]) == ("ADEQUATE", 58)


@pytest.mark.parametrize("score,grade", [(75, "THOROUGH"), (74, "ADEQUATE"),
                                          (40, "ADEQUATE"), (39, "SUPERFICIAL")])
def test_grade_boundaries(direct_vm, direct_deploy, direct_alice, score, grade):
    c = direct_deploy("contracts/contract_audit_verdict.py")
    _, r = _assess(c, direct_vm, direct_alice, _payload((score,) * 5))
    assert (r["grade"], r["overall_score"]) == (grade, score)


def test_overall_integer_division(direct_vm, direct_deploy, direct_alice):
    c = direct_deploy("contracts/contract_audit_verdict.py")
    _, r = _assess(c, direct_vm, direct_alice, _payload((71, 72, 73, 74, 76)))
    assert r["overall_score"] == 73


@pytest.mark.parametrize("case", ["no_gaps", "missing", "non_integer", "clamped",
                                  "non_list", "forged", "range"])
def test_response_edge_cases(direct_vm, direct_deploy, direct_alice, case):
    c = direct_deploy("contracts/contract_audit_verdict.py")
    p = _payload()
    if case == "no_gaps":
        p = _payload((10,) * 5, missing_coverage=[])
    elif case == "missing":
        del p["score_severity"]
    elif case == "non_integer":
        p["score_coverage"] = "high"
    elif case in ("clamped", "range"):
        p = _payload((150, -5, 999, -999, 100), confidence=150)
    elif case == "non_list":
        p["missing_coverage"] = "not a list"
    elif case == "forged":
        p = _payload((30,) * 5, grade="THOROUGH", overall_score=99)
    _, r = _assess(c, direct_vm, direct_alice, p)
    if case == "no_gaps":
        assert (r["grade"], r["overall_score"]) == ("ADEQUATE", 40)
    elif case in ("missing", "non_integer"):
        assert r["grade"] == "UNASSESSABLE"
        assert all(v == 0 for v in r["criteria"].values())
    elif case in ("clamped", "range"):
        assert list(r["criteria"].values()) == [100, 0, 100, 0, 100]
        assert all(0 <= n <= 100 for n in [r["overall_score"], r["confidence"], *r["criteria"].values()])
    elif case == "non_list":
        assert r["missing_coverage"] == "[]" and r["gap_count"] == 0
    else:
        assert (r["grade"], r["overall_score"]) == ("SUPERFICIAL", 30)


@pytest.mark.parametrize("fenced", [False, True])
def test_llm_json_parsing(direct_vm, direct_deploy, direct_alice, fenced):
    c = direct_deploy("contracts/contract_audit_verdict.py")
    rid = _submit(c, direct_vm, direct_alice)
    _mock_pages(direct_vm, LONG_REPORT, SOURCE_TEXT)
    raw = "```json\n" + json.dumps(_payload()) + "\n```" if fenced else "not json!!"
    direct_vm.mock_llm(r".*audit reviewer.*", raw)
    c.assess_audit(rid)
    assert json.loads(c.get_assessment(rid))["grade"] == ("THOROUGH" if fenced else "UNASSESSABLE")


@pytest.mark.parametrize("both", [True, False])
def test_fetch_exceptions(direct_vm, direct_deploy, direct_alice, monkeypatch, both):
    c = direct_deploy("contracts/contract_audit_verdict.py")
    rid = _submit(c, direct_vm, direct_alice)
    _mock_pages(direct_vm, LONG_REPORT, SOURCE_TEXT)
    direct_vm.mock_llm(r".*audit reviewer.*", json.dumps(_payload()))
    import genlayer
    original = genlayer.gl.nondet.web.render
    def render(url):
        if both or url == SOURCE:
            raise RuntimeError("fetch failed")
        return original(url)
    monkeypatch.setattr(genlayer.gl.nondet.web, "render", render)
    c.assess_audit(rid)
    r = json.loads(c.get_assessment(rid))
    if both:
        assert r["grade"] == "UNASSESSABLE"
    else:
        assert r["criteria"]["coverage"] == 50
        assert r["gap_count"] == 2
    assert r["source_readable"] is False


@pytest.mark.parametrize("args,message", [
    (("Treasury", "", REPORT, SOURCE), "audit_firm cannot be empty"),
    (("Treasury", "Sec", "ftp://bad", SOURCE), "Invalid report_url"),
    (("Treasury", "Sec", REPORT, "bad"), "Invalid source_url"),
    (("Treasury", "Sec", REPORT, REPORT), "report_url and source_url must differ"),
    (("x" * 101, "Sec", REPORT, SOURCE), "contract_name cannot exceed 100 characters"),
    (("Treasury", "x" * 101, REPORT, SOURCE), "audit_firm cannot exceed 100 characters"),
])
def test_submit_validation(direct_vm, direct_deploy, direct_alice, args, message):
    c = direct_deploy("contracts/contract_audit_verdict.py")
    with direct_vm.prank(direct_alice), direct_vm.expect_revert(message):
        c.submit_review(*args)
    assert c.get_count() == 0


def test_assess_twice_rejected(direct_vm, direct_deploy, direct_alice):
    c = direct_deploy("contracts/contract_audit_verdict.py")
    rid, _ = _assess(c, direct_vm, direct_alice)
    with direct_vm.expect_revert("Review is not PENDING"):
        c.assess_audit(rid)


def test_get_review_not_found(direct_vm, direct_deploy):
    c = direct_deploy("contracts/contract_audit_verdict.py")
    with direct_vm.expect_revert("Review not found"):
        c.get_review("999")


def test_lookup_by_report(direct_vm, direct_deploy, direct_alice, direct_bob):
    c = direct_deploy("contracts/contract_audit_verdict.py")
    _submit(c, direct_vm, direct_alice)
    rid = _submit(c, direct_vm, direct_bob)
    r = json.loads(c.lookup_by_report(REPORT))
    assert r["review_id"] == rid == "2"
    assert r["submitter"].lower() == "0x" + direct_bob.hex()
    assert json.loads(c.lookup_by_report("https://unknown")) == {"found": False}


def test_list_reviews_filter(direct_vm, direct_deploy, direct_alice):
    c = direct_deploy("contracts/contract_audit_verdict.py")
    _assess(c, direct_vm, direct_alice)
    _assess(c, direct_vm, direct_alice, _payload((20,) * 5))
    _submit(c, direct_vm, direct_alice)
    for grade in ("THOROUGH", "SUPERFICIAL", "PENDING"):
        rows = json.loads(c.list_reviews(grade))["reviews"]
        assert len(rows) == 1
        assert rows[0]["status" if grade == "PENDING" else "grade"] == grade
    assert len(json.loads(c.list_reviews(""))["reviews"]) == 3


def test_invalidate_owner_only(direct_vm, direct_deploy, direct_alice, direct_bob):
    with direct_vm.prank(direct_alice):
        c = direct_deploy("contracts/contract_audit_verdict.py")
    rid = _submit(c, direct_vm, direct_bob)
    with direct_vm.prank(direct_bob), direct_vm.expect_revert("Only owner can invalidate"):
        c.invalidate_review(rid)
    with direct_vm.prank(direct_alice):
        c.invalidate_review(rid)
    r = json.loads(c.get_assessment(rid))
    assert r["grade"] == r["status"] == "UNASSESSABLE"
    assert r["reasoning"] == "Invalidated by admin"
    assessed, _ = _assess(c, direct_vm, direct_bob)
    with direct_vm.prank(direct_alice), direct_vm.expect_revert("Only PENDING reviews can be invalidated"):
        c.invalidate_review(assessed)


@pytest.mark.parametrize("change,accepted", [
    ({}, True), ({"overall_score": 85}, False), ({"overall_score": 86}, False),
    ({"score_coverage": 90, "overall_score": 82}, True), ({"score_coverage": 91}, False),
    ({"grade": "ADEQUATE"}, False), ({"confidence": 79}, False),
    ({"score_findings": -1}, False),
])
def test_validator_rules(direct_vm, direct_deploy, direct_alice, change, accepted):
    c = direct_deploy("contracts/contract_audit_verdict.py")
    _assess(c, direct_vm, direct_alice)
    leader = _payload()
    leader.update(grade="THOROUGH", overall_score=80, gap_count=1, source_readable=True)
    leader["missing_coverage"] = json.dumps(leader["missing_coverage"])
    leader.update(change)
    assert direct_vm.run_validator(leader_result=leader) is accepted


def test_unreadable_report_skips_llm(direct_vm, direct_deploy, direct_alice, monkeypatch):
    c = direct_deploy("contracts/contract_audit_verdict.py")
    rid = _submit(c, direct_vm, direct_alice)
    _mock_pages(direct_vm, "", SOURCE_TEXT)
    direct_vm.mock_llm(r".*audit reviewer.*", json.dumps(_payload()))
    import genlayer
    def forbidden(*args, **kwargs):
        pytest.fail("LLM called for unreadable report")
    monkeypatch.setattr(genlayer.gl.nondet, "exec_prompt", forbidden)
    c.assess_audit(rid)
    assert json.loads(c.get_assessment(rid))["grade"] == "UNASSESSABLE"


def test_llm_failure_is_unassessable(direct_vm, direct_deploy, direct_alice, monkeypatch):
    c = direct_deploy("contracts/contract_audit_verdict.py")
    rid = _submit(c, direct_vm, direct_alice)
    _mock_pages(direct_vm, LONG_REPORT, SOURCE_TEXT)
    direct_vm.mock_llm(r".*audit reviewer.*", json.dumps(_payload()))
    import genlayer
    def fail(*args, **kwargs):
        raise RuntimeError("provider unavailable")
    monkeypatch.setattr(genlayer.gl.nondet, "exec_prompt", fail)
    c.assess_audit(rid)
    assert json.loads(c.get_assessment(rid))["grade"] == "UNASSESSABLE"


@pytest.mark.parametrize("key", KEYS)
def test_validator_checks_each_criterion(direct_vm, direct_deploy, direct_alice, key):
    c = direct_deploy("contracts/contract_audit_verdict.py")
    _assess(c, direct_vm, direct_alice)
    leader = _payload()
    leader.update(grade="THOROUGH", overall_score=80, gap_count=1)
    leader[key] = 91
    leader["overall_score"] = 82
    leader["missing_coverage"] = json.dumps(leader["missing_coverage"])
    assert direct_vm.run_validator(leader_result=leader) is False


def test_validator_superficial_requires_both_gap_counts(direct_vm, direct_deploy, direct_alice):
    c = direct_deploy("contracts/contract_audit_verdict.py")
    _assess(c, direct_vm, direct_alice, _payload((20,) * 5))
    leader = _payload((20,) * 5)
    leader.update(grade="SUPERFICIAL", overall_score=20, gap_count=0)
    leader["missing_coverage"] = json.dumps(leader["missing_coverage"])
    assert direct_vm.run_validator(leader_result=leader) is False
    leader["gap_count"] = 1
    assert direct_vm.run_validator(leader_result=leader) is True
    direct_vm.clear_mocks()
    _mock_pages(direct_vm, LONG_REPORT, SOURCE_TEXT)
    direct_vm.mock_llm(r".*audit reviewer.*", json.dumps(_payload((20,) * 5, missing_coverage=[])))
    assert direct_vm.run_validator(leader_result=leader) is False


def test_validator_rejects_leader_error(direct_vm, direct_deploy, direct_alice):
    c = direct_deploy("contracts/contract_audit_verdict.py")
    _assess(c, direct_vm, direct_alice)
    assert direct_vm.run_validator(leader_error=RuntimeError("leader failed")) is False


@pytest.mark.parametrize("method", ["get_assessment", "assess_audit", "invalidate_review"])
def test_unknown_review_errors(direct_vm, direct_deploy, method):
    c = direct_deploy("contracts/contract_audit_verdict.py")
    with direct_vm.expect_revert("Review not found"):
        getattr(c, method)("999")


def _leader_payload(scores=(80, 80, 80, 80, 80), gaps=None):
    gaps = ["upgrade path not discussed"] if gaps is None else gaps
    p = _payload(scores, missing_coverage=json.dumps(gaps))
    overall = sum(scores) // 5
    if overall < 40 and not gaps:
        overall = 40
    grade = "THOROUGH" if overall >= 75 else "ADEQUATE" if overall >= 40 else "SUPERFICIAL"
    p.update(overall_score=overall, grade=grade, gap_count=len(gaps), source_readable=True)
    return p


@pytest.mark.parametrize("change", [
    {"overall_score": 79}, {"overall_score": 81},
    {"grade": "ADEQUATE"}, {"grade": "SUPERFICIAL"},
    {"gap_count": 0}, {"gap_count": 2}, {"gap_count": -1},
    {"missing_coverage": "not json"}, {"missing_coverage": "{}"},
    {"missing_coverage": "null"}, {"missing_coverage": '[""]'},
    {"missing_coverage": '["   "]'}, {"missing_coverage": '[3]'},
    {"missing_coverage": '[null]'}, {"missing_coverage": '[true]'},
    {"missing_coverage": ["upgrade path not discussed"]},
    {"missing_coverage": None},
    {"overall_score": "80"}, {"overall_score": True},
    {"score_coverage": "80"}, {"score_coverage": True},
    {"gap_count": "1"}, {"gap_count": True},
    {"confidence": "85"},
])
def test_validator_rejects_inconsistent_leader_before_nondet(
        direct_vm, direct_deploy, direct_alice, monkeypatch, change):
    c = direct_deploy("contracts/contract_audit_verdict.py")
    _assess(c, direct_vm, direct_alice)
    leader = _leader_payload()
    leader.update(change)
    import genlayer
    def must_not_call(*args, **kwargs):
        pytest.fail("Invalid payload reached independent assessment")
    monkeypatch.setattr(genlayer.gl.nondet.web, "render", must_not_call)
    monkeypatch.setattr(genlayer.gl.nondet, "exec_prompt", must_not_call)
    assert direct_vm.run_validator(leader_result=leader) is False


@pytest.mark.parametrize("scores,gaps,grade,overall", [
    ((75,) * 5, ["gap"], "THOROUGH", 75),
    ((74,) * 5, ["gap"], "ADEQUATE", 74),
    ((40,) * 5, ["gap"], "ADEQUATE", 40),
    ((39,) * 5, ["gap"], "SUPERFICIAL", 39),
    ((10,) * 5, [], "ADEQUATE", 40),
    ((0,) * 5, [], "ADEQUATE", 40),
    ((39,) * 5, [], "ADEQUATE", 40),
    ((71, 72, 73, 74, 76), ["gap"], "ADEQUATE", 73),
])
def test_validator_accepts_deterministic_boundaries_and_floor(
        direct_vm, direct_deploy, direct_alice, scores, gaps, grade, overall):
    c = direct_deploy("contracts/contract_audit_verdict.py")
    _assess(c, direct_vm, direct_alice, _payload(scores, missing_coverage=gaps))
    leader = _leader_payload(scores, gaps)
    assert (leader["grade"], leader["overall_score"]) == (grade, overall)
    assert direct_vm.run_validator(leader_result=leader) is True
    leader["overall_score"] = overall + 1
    assert direct_vm.run_validator(leader_result=leader) is False


@pytest.mark.parametrize("score,accepted", [(85, True), (86, False)])
def test_validator_retains_overall_tolerance_for_consistent_leaders(
        direct_vm, direct_deploy, direct_alice, score, accepted):
    c = direct_deploy("contracts/contract_audit_verdict.py")
    _assess(c, direct_vm, direct_alice)
    assert direct_vm.run_validator(leader_result=_leader_payload((score,) * 5)) is accepted


@pytest.mark.parametrize("change,accepted", [
    ({}, True), ({"overall_score": 1}, False),
    ({"score_coverage": 1}, False), ({"confidence": 1}, False),
    ({"missing_coverage": '["gap"]', "gap_count": 1}, False),
    ({"grade": "SUPERFICIAL"}, False),
])
def test_validator_unassessable_invariants(
        direct_vm, direct_deploy, direct_alice, change, accepted):
    c = direct_deploy("contracts/contract_audit_verdict.py")
    _assess(c, direct_vm, direct_alice, report="")
    leader = _leader_payload((0,) * 5, [])
    leader.update(grade="UNASSESSABLE", overall_score=0, confidence=0)
    leader.update(change)
    assert direct_vm.run_validator(leader_result=leader) is accepted
