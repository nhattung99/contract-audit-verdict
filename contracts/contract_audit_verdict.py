# v0.2.16
# { "Seq": [{ "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }] }
from genlayer import *
import json
from dataclasses import dataclass

@allow_storage
@dataclass
class AuditReview:
    submitter: Address
    contract_name: str          # label e.g. "Treasury v2"
    audit_firm: str             # label e.g. "ExampleSec"
    report_url: str             # audit report URL
    source_url: str             # audited contract source URL
    status: str                 # "PENDING" | "ASSESSED" | "UNASSESSABLE"
    grade: str                  # "THOROUGH"|"ADEQUATE"|"SUPERFICIAL"|
                                # "UNASSESSABLE"|""
    overall_score: u256         # 0-100, computed average
    score_coverage: u256        # 0-100
    score_findings: u256        # 0-100
    score_severity: u256        # 0-100
    score_remediation: u256     # 0-100
    score_methodology: u256     # 0-100
    confidence: u256            # 0-100
    reasoning: str              # AI explanation
    missing_coverage: str       # JSON array string of strings
    gap_count: u256             # number of missing coverage areas
    source_readable: bool       # was the contract source readable

class Contract(gl.Contract):
    reviews: TreeMap[str, AuditReview]
    next_id: bigint
    owner: Address
    report_cache: TreeMap[str, str]

    def __init__(self):
        self.owner = gl.message.sender_address
        self.next_id = bigint(1)

    @gl.public.write
    def submit_review(self, contract_name: str, audit_firm: str,
                      report_url: str, source_url: str) -> str:
        if not contract_name.strip():
            raise gl.vm.UserError("contract_name cannot be empty")
        if len(contract_name) > 100:
            raise gl.vm.UserError("contract_name cannot exceed 100 characters")
        if not audit_firm.strip():
            raise gl.vm.UserError("audit_firm cannot be empty")
        if len(audit_firm) > 100:
            raise gl.vm.UserError("audit_firm cannot exceed 100 characters")
        if not report_url.startswith(("http://", "https://")):
            raise gl.vm.UserError("Invalid report_url")
        if not source_url.startswith(("http://", "https://")):
            raise gl.vm.UserError("Invalid source_url")
        if report_url == source_url:
            raise gl.vm.UserError("report_url and source_url must differ")
        review_id = str(self.next_id)
        self.reviews[review_id] = AuditReview(
            submitter=gl.message.sender_address, contract_name=contract_name,
            audit_firm=audit_firm, report_url=report_url, source_url=source_url,
            status="PENDING", grade="", overall_score=u256(0),
            score_coverage=u256(0), score_findings=u256(0),
            score_severity=u256(0), score_remediation=u256(0),
            score_methodology=u256(0), confidence=u256(0), reasoning="",
            missing_coverage="[]", gap_count=u256(0), source_readable=False)
        self.report_cache[report_url] = review_id
        self.next_id += 1
        return review_id

    @gl.public.write
    def assess_audit(self, review_id: str) -> None:
        if review_id not in self.reviews:
            raise gl.vm.UserError("Review not found")
        review = self.reviews[review_id]
        if review.status != "PENDING":
            raise gl.vm.UserError("Review is not PENDING")
        report_url_cap = review.report_url
        source_url_cap = review.source_url
        contract_name_cap = review.contract_name
        audit_firm_cap = review.audit_firm

        def leader_fn():
            # 1. Fetch audit report - try/except
            report_readable = False
            report_content = ""
            try:
                res = gl.nondet.web.render(report_url_cap)
                body = res.body if hasattr(res, 'body') else str(res)
                if body and len(body.strip()) > 100:
                    report_content = body[:6000]
                    report_readable = True
                else:
                    report_content = "(empty or too short)"
            except Exception as e:
                report_content = f"(fetch failed: {str(e)})"

            # 2. Fetch contract source - try/except
            source_readable = False
            source_content = ""
            try:
                res2 = gl.nondet.web.render(source_url_cap)
                body2 = res2.body if hasattr(res2, 'body') else str(res2)
                if body2 and len(body2.strip()) > 50:
                    source_content = body2[:4000]
                    source_readable = True
                else:
                    source_content = "(empty or too short)"
            except Exception as e:
                source_content = f"(fetch failed: {str(e)})"

            # 3. If the report itself is unreadable there is nothing to score.
            #    Return immediately WITHOUT calling the LLM.
            if not report_readable:
                return {
                    "grade": "UNASSESSABLE",
                    "overall_score": 0,
                    "score_coverage": 0,
                    "score_findings": 0,
                    "score_severity": 0,
                    "score_remediation": 0,
                    "score_methodology": 0,
                    "confidence": 0,
                    "reasoning": "Audit report could not be read",
                    "missing_coverage": "[]",
                    "gap_count": 0,
                    "source_readable": source_readable
                }

            # 4. Build prompt
            prompt = f"""You are an expert smart contract security audit reviewer
        on GenLayer. You review the QUALITY of an audit report. You do NOT audit
        the contract yourself and you do NOT judge whether the contract is safe.

        Audited contract: {contract_name_cap}
        Audit firm: {audit_firm_cap}

        Audit report fetched on-chain (may be truncated; do not penalize length):
        {report_content}

        Audited contract source fetched on-chain:
        {source_content}

        Score the report on five criteria, each an integer 0 to 100:

        1. coverage: Does the report address the attack surface visible in the
           source (public/external functions, access control, external calls,
           token flows, upgrade paths)? If the source is unreadable, score
           conservatively.
        2. findings: Are findings specific, tied to code locations, with proof
           of concept or reproduction steps?
        3. severity: Are severity ratings consistent and justified by impact
           and likelihood, neither inflated nor deflated?
        4. remediation: Is the fix guidance concrete and actionable, and is
           there a fix-verification or re-review section?
        5. methodology: Are scope, commit hash, tooling, manual review effort,
           and auditor team disclosed?

        Also list the specific coverage areas the report MISSED (for example:
        "no analysis of the upgrade proxy", "reentrancy in withdraw() not
        discussed"). Use an empty list only if nothing material is missing.

        Base every score ONLY on the fetched text. Do not use outside knowledge
        about the audit firm's reputation.

        Return ONLY raw JSON, no markdown, no backticks:
        {{"score_coverage": <0-100>,
          "score_findings": <0-100>,
          "score_severity": <0-100>,
          "score_remediation": <0-100>,
          "score_methodology": <0-100>,
          "confidence": <0-100>,
          "reasoning": "<2-3 sentences citing specific report content>",
          "missing_coverage": ["<missed area 1>", "<missed area 2>"]}}"""


            # 5. Parse with safe fallback - NEVER throw from leader_fn
            try:
                raw = gl.nondet.exec_prompt(prompt, response_format="json")
                if isinstance(raw, dict):
                    parsed = raw
                else:
                    cleaned = str(raw).strip()
                    if cleaned.startswith("```json"): cleaned = cleaned[7:]
                    if cleaned.startswith("```"): cleaned = cleaned[3:]
                    if cleaned.endswith("```"): cleaned = cleaned[:-3]
                    parsed = json.loads(cleaned.strip())

                # All five criteria must be present integers, else treat the
                # whole response as unusable (UNASSESSABLE, not a guessed score)
                keys = ["score_coverage", "score_findings", "score_severity",
                        "score_remediation", "score_methodology"]
                scores = {}
                for k in keys:
                    scores[k] = max(0, min(100, int(parsed[k])))   # KeyError/ValueError -> except

                # Deterministic cap: if the source was unreadable, coverage
                # cannot be verified against it
                if not source_readable and scores["score_coverage"] > 50:
                    scores["score_coverage"] = 50

                try: conf = max(0, min(100, int(parsed.get("confidence", 0))))
                except: conf = 0

                raw_missing = parsed.get("missing_coverage", [])
                if not isinstance(raw_missing, list): raw_missing = []
                clean_missing = [str(m) for m in raw_missing if m and str(m).strip()]

                if not source_readable:
                    clean_missing.append(
                        "contract source unreadable: coverage could not be verified")

                # Deterministic derivations
                overall = (scores["score_coverage"] + scores["score_findings"]
                           + scores["score_severity"] + scores["score_remediation"]
                           + scores["score_methodology"]) // 5

                if overall >= 75: grade = "THOROUGH"
                elif overall >= 40: grade = "ADEQUATE"
                else: grade = "SUPERFICIAL"

                # Consistency: SUPERFICIAL must be backed by at least 1 missing
                # coverage area; otherwise treat as ADEQUATE (floor score 40)
                if grade == "SUPERFICIAL" and len(clean_missing) == 0:
                    grade = "ADEQUATE"
                    overall = max(overall, 40)

                return {
                    "grade": grade,
                    "overall_score": overall,
                    "score_coverage": scores["score_coverage"],
                    "score_findings": scores["score_findings"],
                    "score_severity": scores["score_severity"],
                    "score_remediation": scores["score_remediation"],
                    "score_methodology": scores["score_methodology"],
                    "confidence": conf,
                    "reasoning": str(parsed.get("reasoning", "")),
                    "missing_coverage": json.dumps(clean_missing),
                    "gap_count": len(clean_missing),
                    "source_readable": source_readable
                }
            except Exception as e:
                return {
                    "grade": "UNASSESSABLE",
                    "overall_score": 0,
                    "score_coverage": 0,
                    "score_findings": 0,
                    "score_severity": 0,
                    "score_remediation": 0,
                    "score_methodology": 0,
                    "confidence": 0,
                    "reasoning": f"Parse error or incomplete criteria: {str(e)}",
                    "missing_coverage": "[]",
                    "gap_count": 0,
                    "source_readable": source_readable
                }


        def validator_fn(leader_res) -> bool:
            if not isinstance(leader_res, gl.vm.Return):
                return False
            lp = leader_res.calldata
            if not isinstance(lp, dict):
                return False

            valid_grades = ["THOROUGH", "ADEQUATE", "SUPERFICIAL", "UNASSESSABLE"]
            keys = ["score_coverage", "score_findings", "score_severity",
                    "score_remediation", "score_methodology"]

            leader_grade = lp.get("grade")
            if leader_grade not in valid_grades:
                return False
            try:
                l_overall = int(lp.get("overall_score"))
                l_conf = int(lp.get("confidence"))
                l_scores = {k: int(lp.get(k)) for k in keys}
                l_gaps = int(lp.get("gap_count", 0))
            except:
                return False
            if not (0 <= l_overall <= 100): return False
            if not (0 <= l_conf <= 100): return False
            for k in keys:
                if not (0 <= l_scores[k] <= 100): return False

            try:
                my = leader_fn()
            except:
                return False

            # 1. Grade must match exactly - the headline decision
            if my.get("grade") != leader_grade:
                return False

            # 2. Overall score within +-5
            try:
                m_overall = int(my.get("overall_score", 0))
                if abs(m_overall - l_overall) > 5:
                    return False
            except:
                return False

            # 3. EVERY per-criterion score within +-10
            try:
                for k in keys:
                    if abs(int(my.get(k, 0)) - l_scores[k]) > 10:
                        return False
            except:
                return False

            # 4. SUPERFICIAL: both sides must report at least 1 missing area
            if leader_grade == "SUPERFICIAL":
                try:
                    if int(my.get("gap_count", 0)) == 0 or l_gaps == 0:
                        return False
                except:
                    return False

            # 5. Confidence banding - same 3-band system as approved contracts
            try:
                m_conf = int(my.get("confidence", 0))
                if not (0 <= m_conf <= 100): return False
            except:
                return False

            def _band(c):
                if c < 35: return 1
                elif c < 80: return 2
                else: return 3

            return _band(m_conf) == _band(l_conf)


        # Execute and unpack result
        ruling = gl.vm.run_nondet_unsafe(leader_fn, validator_fn)
        result_data = ruling.calldata if hasattr(ruling, 'calldata') else ruling

        result_grade = result_data.get("grade", "UNASSESSABLE")
        review.grade = result_grade
        review.overall_score = u256(result_data.get("overall_score", 0))
        review.score_coverage = u256(result_data.get("score_coverage", 0))
        review.score_findings = u256(result_data.get("score_findings", 0))
        review.score_severity = u256(result_data.get("score_severity", 0))
        review.score_remediation = u256(result_data.get("score_remediation", 0))
        review.score_methodology = u256(result_data.get("score_methodology", 0))
        review.confidence = u256(result_data.get("confidence", 0))
        review.reasoning = str(result_data.get("reasoning", ""))
        review.missing_coverage = str(result_data.get("missing_coverage", "[]"))
        review.gap_count = u256(result_data.get("gap_count", 0))
        review.source_readable = bool(result_data.get("source_readable", False))
        review.status = "ASSESSED" if result_grade != "UNASSESSABLE" \
            else "UNASSESSABLE"
        self.reviews[review_id] = review

    @gl.public.write
    def invalidate_review(self, review_id: str) -> None:
        if gl.message.sender_address != self.owner:
            raise gl.vm.UserError("Only owner can invalidate")
        if review_id not in self.reviews:
            raise gl.vm.UserError("Review not found")
        review = self.reviews[review_id]
        if review.status != "PENDING":
            raise gl.vm.UserError("Only PENDING reviews can be invalidated")
        review.status = "UNASSESSABLE"
        review.grade = "UNASSESSABLE"
        review.reasoning = "Invalidated by admin"
        self.reviews[review_id] = review

    @gl.public.view
    def get_review(self, review_id: str) -> str:
        if review_id not in self.reviews:
            raise gl.vm.UserError("Review not found")
        review = self.reviews[review_id]
        return json.dumps({
            "review_id": review_id,
            "submitter": str(review.submitter),
            "contract_name": review.contract_name,
            "audit_firm": review.audit_firm,
            "report_url": review.report_url,
            "source_url": review.source_url,
            "status": review.status,
            "grade": review.grade,
            "overall_score": int(review.overall_score),
            "score_coverage": int(review.score_coverage),
            "score_findings": int(review.score_findings),
            "score_severity": int(review.score_severity),
            "score_remediation": int(review.score_remediation),
            "score_methodology": int(review.score_methodology),
            "confidence": int(review.confidence),
            "reasoning": review.reasoning,
            "missing_coverage": review.missing_coverage,
            "gap_count": int(review.gap_count),
            "source_readable": review.source_readable,
        })

    @gl.public.view
    def get_assessment(self, review_id: str) -> str:
        data = json.loads(self.get_review(review_id))
        if data["status"] == "PENDING":
            raise gl.vm.UserError("Not yet assessed")
        result = {key: data[key] for key in (
            "review_id", "contract_name", "audit_firm", "grade", "overall_score",
            "confidence", "reasoning", "missing_coverage", "gap_count",
            "source_readable", "status")}
        result["criteria"] = {key: data["score_" + key] for key in (
            "coverage", "findings", "severity", "remediation", "methodology")}
        return json.dumps(result)

    @gl.public.view
    def lookup_by_report(self, report_url: str) -> str:
        if report_url not in self.report_cache:
            return json.dumps({"found": False})
        return self.get_review(self.report_cache[report_url])

    @gl.public.view
    def list_reviews(self, grade_filter: str) -> str:
        items = []
        for number in range(1, int(self.next_id)):
            review_id = str(number)
            review = self.reviews[review_id]
            if grade_filter == "PENDING":
                if review.status != "PENDING":
                    continue
            elif grade_filter and review.grade != grade_filter:
                continue
            items.append({"review_id": review_id,
                          "contract_name": review.contract_name,
                          "audit_firm": review.audit_firm,
                          "status": review.status, "grade": review.grade,
                          "overall_score": int(review.overall_score)})
        return json.dumps({"reviews": items})

    @gl.public.view
    def get_count(self) -> int:
        return int(self.next_id) - 1
