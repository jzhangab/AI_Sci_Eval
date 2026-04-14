"""
Core evaluation engine.
Uses the Dataiku LLM Mesh to evaluate documents against the framework criteria.
"""
import json
import math
from collections import OrderedDict
from lib.document_parser import parse_file
from lib.llm_client import call_llm
from lib.framework_config import (
    DOMAIN_CRITERIA,
    DOMAIN_WEIGHTS,
    CRITICAL_DOMAINS,
    CRITICAL_THRESHOLD,
    FULL_APPROVAL_THRESHOLD,
    CONDITIONAL_APPROVAL_THRESHOLD,
    SCORE_RUBRIC,
    DESIGN_PATTERNS,
    RISK_REGISTER,
)


# ---------------------------------------------------------------------------
# LLM-based domain evaluation
# ---------------------------------------------------------------------------

_DOMAIN_EVAL_PROMPT = """\
You are evaluating a document against the **{domain}** domain of the AI/LLM Scientific Review Framework.

## Domain: {domain} (Weight: {weight}%)
{domain_description}

## Criteria to evaluate:
{criteria_block}

## Document text (may be truncated):
---
{document_text}
---

## Instructions:
For EACH criterion listed above, evaluate how thoroughly the document addresses it.
Score each criterion from 0 to 100:
- 85-100: Excellent — criterion is comprehensively addressed with specific detail
- 70-84: Satisfactory — criterion is clearly addressed but may lack some depth
- 55-69: Marginal — criterion is partially addressed or only mentioned in passing
- 40-54: Poor — criterion is barely touched or only implied
- 0-39: Critical failure — criterion is not addressed at all

Return ONLY valid JSON in this exact format (no markdown, no commentary):
{{
  "criteria": [
    {{
      "key": "<criterion_key>",
      "score": <0-100>,
      "evidence": "<1-2 sentence quote or summary from the document supporting this score>",
      "gap": "<what is missing or could be improved, or 'None' if excellent>"
    }}
  ]
}}
"""

_DOMAIN_DESCRIPTIONS = {
    "Accuracy": "Evaluates factual correctness, calibration quality, and grounding relative to source data.",
    "Safety": "Assesses resistance to harmful output generation, misuse, and alignment failures. Safety is deployment-blocking.",
    "Transparency": "Measures explainability of model decisions, auditability of inference, and completeness of documentation.",
    "Repeatability": "Assesses output stability across repeated runs, prompt paraphrasing, and version changes.",
    "Trustworthiness": "Composite dimension spanning robustness, privacy, integrity, and systemic reliability.",
}


def _build_criteria_block(criteria):
    lines = []
    for c in criteria:
        lines.append(f"- **{c['name']}** (key: `{c['key']}`, rigor: {c['rigor']}/5): {c['description']}")
    return "\n".join(lines)


def _truncate_text(text, max_chars=30000):
    """Truncate document text to fit within LLM context window."""
    if len(text) <= max_chars:
        return text
    half = max_chars // 2
    return text[:half] + "\n\n[... document truncated for evaluation ...]\n\n" + text[-half:]


def _parse_llm_json(response_text):
    """Extract JSON from LLM response, handling markdown code fences."""
    text = response_text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        # Remove first and last fence lines
        start = 1
        end = len(lines)
        for i in range(len(lines) - 1, 0, -1):
            if lines[i].strip().startswith("```"):
                end = i
                break
        text = "\n".join(lines[start:end])
    return json.loads(text)


def evaluate_domain_criteria(text):
    """
    Evaluate document text against all 5 domain criteria using the LLM.
    Returns dict of domain -> {score, criteria_details, interpretation}.
    """
    truncated = _truncate_text(text)
    results = OrderedDict()

    for domain, criteria in DOMAIN_CRITERIA.items():
        prompt = _DOMAIN_EVAL_PROMPT.format(
            domain=domain,
            weight=int(DOMAIN_WEIGHTS[domain] * 100),
            domain_description=_DOMAIN_DESCRIPTIONS.get(domain, ""),
            criteria_block=_build_criteria_block(criteria),
            document_text=truncated,
        )

        raw_response = call_llm(prompt)
        parsed = _parse_llm_json(raw_response)

        # Build results keyed by criterion key for lookup
        llm_scores = {c["key"]: c for c in parsed["criteria"]}

        criteria_results = []
        weighted_sum = 0
        total_rigor = 0

        for c in criteria:
            llm_entry = llm_scores.get(c["key"], {})
            score = max(0, min(100, int(llm_entry.get("score", 0))))
            criteria_results.append({
                "key": c["key"],
                "name": c["name"],
                "description": c["description"],
                "rigor": c["rigor"],
                "score": score,
                "evidence": llm_entry.get("evidence", ""),
                "gap": llm_entry.get("gap", ""),
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


# ---------------------------------------------------------------------------
# LLM-based design pattern evaluation
# ---------------------------------------------------------------------------

_DESIGN_PATTERN_PROMPT = """\
You are evaluating a document against the **Modern Design Pattern Requirements** of the AI/LLM Scientific Review Framework.

## Design Pattern Pillars and Requirements:
{pillars_block}

## Document text (may be truncated):
---
{document_text}
---

## Instructions:
For EACH requirement across ALL pillars, determine whether the document addresses it.
Return ONLY valid JSON in this exact format (no markdown, no commentary):
{{
  "pillars": [
    {{
      "pillar": "<pillar name>",
      "items": [
        {{
          "requirement": "<requirement text>",
          "found": <true or false>,
          "evidence": "<brief quote or summary if found, or 'Not addressed' if not>"
        }}
      ]
    }}
  ]
}}
"""


def _build_pillars_block():
    lines = []
    for pillar, items in DESIGN_PATTERNS.items():
        lines.append(f"\n### {pillar}")
        for item in items:
            lines.append(f"- {item}")
    return "\n".join(lines)


def evaluate_design_patterns(text):
    """
    Evaluate document text against Section 3 design pattern checklists using the LLM.
    """
    truncated = _truncate_text(text)
    prompt = _DESIGN_PATTERN_PROMPT.format(
        pillars_block=_build_pillars_block(),
        document_text=truncated,
    )

    raw_response = call_llm(prompt)
    parsed = _parse_llm_json(raw_response)

    results = OrderedDict()
    for pillar_data in parsed["pillars"]:
        pillar_name = pillar_data["pillar"]
        matched = []
        for item in pillar_data["items"]:
            matched.append({
                "requirement": item["requirement"],
                "found": bool(item.get("found", False)),
                "evidence": item.get("evidence", ""),
            })

        found_count = sum(1 for m in matched if m["found"])
        total = len(matched)
        results[pillar_name] = {
            "items": matched,
            "matched_count": found_count,
            "total_count": total,
            "score": round((found_count / total) * 100) if total > 0 else 0,
        }

    return results


# ---------------------------------------------------------------------------
# LLM-based risk register evaluation
# ---------------------------------------------------------------------------

_RISK_REGISTER_PROMPT = """\
You are evaluating a document against the **Risk Register** of the AI/LLM Scientific Review Framework.

## Risk Register:
{risks_block}

## Document text (may be truncated):
---
{document_text}
---

## Instructions:
For EACH risk, determine whether the document addresses or mitigates it.
Return ONLY valid JSON in this exact format (no markdown, no commentary):
{{
  "risks": [
    {{
      "risk": "<risk name>",
      "severity": "<HIGH/MEDIUM/LOW>",
      "addressed": <true or false>,
      "evidence": "<brief quote or summary if addressed, or 'Not addressed' if not>"
    }}
  ]
}}
"""


def _build_risks_block():
    lines = []
    for r in RISK_REGISTER:
        lines.append(f"- **{r['risk']}** (Severity: {r['severity']}): {r['description']} Mitigation: {r['mitigation']}")
    return "\n".join(lines)


def evaluate_risk_register(text):
    """
    Check which risk register items are addressed using the LLM.
    """
    truncated = _truncate_text(text)
    prompt = _RISK_REGISTER_PROMPT.format(
        risks_block=_build_risks_block(),
        document_text=truncated,
    )

    raw_response = call_llm(prompt)
    parsed = _parse_llm_json(raw_response)

    results = []
    risk_lookup = {r["risk"]: r for r in RISK_REGISTER}
    for item in parsed["risks"]:
        risk_name = item["risk"]
        ref = risk_lookup.get(risk_name, {})
        results.append({
            "risk": risk_name,
            "severity": item.get("severity", ref.get("severity", "MEDIUM")),
            "description": ref.get("description", ""),
            "mitigation": ref.get("mitigation", ""),
            "addressed": bool(item.get("addressed", False)),
            "evidence": item.get("evidence", ""),
        })

    return results


# ---------------------------------------------------------------------------
# Composite scoring and verdicts
# ---------------------------------------------------------------------------

def compute_composite_score(domain_results):
    """Compute weighted composite score and overall verdict."""
    weighted_sum = sum(
        data["score"] * data["weight"]
        for data in domain_results.values()
    )
    composite = round(weighted_sum)

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


# ---------------------------------------------------------------------------
# Top-level orchestration
# ---------------------------------------------------------------------------

def run_full_evaluation(text):
    """
    Run the complete LLM-powered evaluation pipeline on document text.
    Returns a comprehensive results dict.
    """
    domain_results = evaluate_domain_criteria(text)
    composite = compute_composite_score(domain_results)
    design_results = evaluate_design_patterns(text)
    risk_results = evaluate_risk_register(text)

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


def evaluate_documents(documents):
    """
    Parse and evaluate all documents in a {filename: bytes} dict.
    Returns {filename: {"text": str, "results": dict}}.
    """
    from IPython.display import display, HTML

    if not documents:
        display(HTML(
            '<div style="background:#fff3e0;border:1px solid #e65100;border-radius:6px;'
            'padding:16px;color:#e65100"><strong>No documents loaded.</strong> '
            'Add files to the eval_documents folder or use the upload widget, '
            'then re-run this cell.</div>'
        ))
        return {}

    all_results = {}
    for filename, file_bytes in documents.items():
        print(f"Parsing: {filename} ...", end=" ")
        try:
            text = parse_file(filename, file_bytes)
            print(f"{len(text.split()):,} words extracted.")
            print(f"Evaluating with LLM (5 domains + design patterns + risk register)...")
            results = run_full_evaluation(text)
            all_results[filename] = {"text": text, "results": results}
            print(f"  -> Composite: {results['composite']['composite_score']} — {results['composite']['verdict']}")
        except Exception as exc:
            print(f"ERROR: {exc}")

    print(f"\nEvaluated {len(all_results)} document(s) successfully.")
    return all_results
