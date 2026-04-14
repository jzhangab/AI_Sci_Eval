"""
Core evaluation engine.
Scans document text against the framework criteria and produces scores.
"""
import re
from collections import OrderedDict
from lib.framework_config import (
    DOMAIN_CRITERIA,
    DOMAIN_WEIGHTS,
    CRITICAL_DOMAINS,
    CRITICAL_THRESHOLD,
    FULL_APPROVAL_THRESHOLD,
    CONDITIONAL_APPROVAL_THRESHOLD,
    SCORE_RUBRIC,
    DESIGN_PATTERNS,
    DESIGN_PATTERN_KEYWORDS,
    RISK_REGISTER,
)


def _keyword_hits(text_lower, keywords):
    """Return list of keywords found in text."""
    return [kw for kw in keywords if kw in text_lower]


def _score_criterion(text_lower, keywords, rigor):
    """
    Score a single criterion (0-100) based on keyword coverage and depth.
    Keywords are intentionally broad (synonyms/variants), so matching ~40%
    of them already indicates solid coverage. The scoring curve reflects this:
    - 30% keyword coverage -> ~60 score (marginal)
    - 50% keyword coverage -> ~80 score (satisfactory)
    - 70%+ keyword coverage -> ~90+ score (excellent)
    Depth (repeat mentions) adds up to 15 bonus points.
    """
    hits = _keyword_hits(text_lower, keywords)
    if not hits:
        return 0, hits

    coverage = len(hits) / len(keywords)

    # Scaled coverage: use sqrt curve so partial matches score higher
    # sqrt(0.3)=0.55, sqrt(0.5)=0.71, sqrt(0.7)=0.84, sqrt(1.0)=1.0
    import math
    scaled_coverage = math.sqrt(coverage)

    # Depth: total occurrences of matched keywords (diminishing returns)
    total_occurrences = sum(text_lower.count(kw) for kw in hits)
    depth_bonus = min(total_occurrences / (rigor * 4), 1.0)

    # Combine: scaled coverage drives 85pts, depth adds up to 15pts
    raw = (scaled_coverage * 85) + (depth_bonus * 15)

    return min(round(raw), 100), hits


def evaluate_domain_criteria(text):
    """
    Evaluate document text against all 5 domain criteria.
    Returns dict of domain -> {score, criteria_details, interpretation}.
    """
    text_lower = text.lower()
    results = OrderedDict()

    for domain, criteria in DOMAIN_CRITERIA.items():
        criteria_results = []
        weighted_sum = 0
        total_rigor = 0

        for c in criteria:
            score, hits = _score_criterion(text_lower, c["keywords"], c["rigor"])
            criteria_results.append({
                "key": c["key"],
                "name": c["name"],
                "description": c["description"],
                "rigor": c["rigor"],
                "score": score,
                "keywords_found": hits,
                "keywords_total": len(c["keywords"]),
            })
            weighted_sum += score * c["rigor"]
            total_rigor += c["rigor"]

        domain_score = round(weighted_sum / total_rigor) if total_rigor > 0 else 0
        interpretation = _interpret_score(domain_score)

        results[domain] = {
            "score": domain_score,
            "weight": DOMAIN_WEIGHTS[domain],
            "interpretation": interpretation,
            "is_critical": domain in CRITICAL_DOMAINS,
            "below_threshold": domain_score < CRITICAL_THRESHOLD,
            "criteria": criteria_results,
        }

    return results


def evaluate_design_patterns(text):
    """
    Evaluate document text against Section 3 design pattern checklists.
    Returns dict of pillar -> {items, matched, score}.
    """
    text_lower = text.lower()
    results = OrderedDict()

    for pillar, items in DESIGN_PATTERNS.items():
        keyword_sets = DESIGN_PATTERN_KEYWORDS[pillar]
        matched = []
        for i, item in enumerate(items):
            kw_set = keyword_sets[i] if i < len(keyword_sets) else []
            found = any(kw in text_lower for kw in kw_set)
            matched.append({
                "requirement": item,
                "found": found,
                "keywords_matched": [kw for kw in kw_set if kw in text_lower],
            })

        found_count = sum(1 for m in matched if m["found"])
        total = len(items)
        results[pillar] = {
            "items": matched,
            "matched_count": found_count,
            "total_count": total,
            "score": round((found_count / total) * 100) if total > 0 else 0,
        }

    return results


def evaluate_risk_register(text):
    """
    Check which risk register items are addressed in the document.
    Returns list of risk entries with coverage status.
    """
    text_lower = text.lower()
    results = []

    for risk in RISK_REGISTER:
        hits = _keyword_hits(text_lower, risk["keywords"])
        results.append({
            "risk": risk["risk"],
            "severity": risk["severity"],
            "description": risk["description"],
            "mitigation": risk["mitigation"],
            "addressed": len(hits) > 0,
            "keywords_found": hits,
        })

    return results


def compute_composite_score(domain_results):
    """
    Compute weighted composite score and overall verdict.
    """
    weighted_sum = 0
    for domain, data in domain_results.items():
        weighted_sum += data["score"] * data["weight"]

    composite = round(weighted_sum)

    # Check blocking conditions
    critical_failure = any(
        data["is_critical"] and data["below_threshold"]
        for data in domain_results.values()
    )
    any_below_threshold = any(
        data["below_threshold"]
        for data in domain_results.values()
    )

    if critical_failure or composite < CONDITIONAL_APPROVAL_THRESHOLD:
        verdict = "Reject / Revise"
    elif composite >= FULL_APPROVAL_THRESHOLD and not any_below_threshold:
        verdict = "Full Approval"
    elif composite >= CONDITIONAL_APPROVAL_THRESHOLD and not any_below_threshold:
        verdict = "Conditional Approval"
    else:
        verdict = "Reject / Revise"

    return {
        "composite_score": composite,
        "verdict": verdict,
        "interpretation": _interpret_score(composite),
        "critical_failure": critical_failure,
        "any_domain_below_threshold": any_below_threshold,
    }


def _interpret_score(score):
    """Map a score to its rubric interpretation."""
    for low, high, label, action in SCORE_RUBRIC:
        if low <= score <= high:
            return {"label": label, "action": action}
    return {"label": "Unknown", "action": "Review manually"}


def run_full_evaluation(text):
    """
    Run the complete evaluation pipeline on document text.
    Returns a comprehensive results dict.
    """
    domain_results = evaluate_domain_criteria(text)
    composite = compute_composite_score(domain_results)
    design_results = evaluate_design_patterns(text)
    risk_results = evaluate_risk_register(text)

    # Design pattern overall score
    dp_scores = [v["score"] for v in design_results.values()]
    dp_overall = round(sum(dp_scores) / len(dp_scores)) if dp_scores else 0

    return {
        "domains": domain_results,
        "composite": composite,
        "design_patterns": design_results,
        "design_patterns_overall_score": dp_overall,
        "risk_register": risk_results,
        "risks_addressed": sum(1 for r in risk_results if r["addressed"]),
        "risks_total": len(risk_results),
    }
