"""
Core evaluation engine.
Uses the Dataiku LLM Mesh to evaluate documents against the framework criteria.
"""
import json
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
    Run the LLM-powered evaluation pipeline on document text.
    Evaluates the 5 framework domains and computes the composite verdict.
    """
    domain_results = evaluate_domain_criteria(text)
    composite = compute_composite_score(domain_results)

    return {
        "domains": domain_results,
        "composite": composite,
    }


def evaluate_documents_deep_research(documents):
    """
    Deep research mode: synthesize all documents in the folder into a unified
    project intelligence text, then evaluate the project as a single entity.

    Returns {project_key: {"text": str, "results": dict, "source_files": list}}.
    """
    from IPython.display import display, HTML
    from lib.deep_research import synthesize_project

    if not documents:
        display(HTML(
            '<div style="background:#fff3e0;border:1px solid #e65100;border-radius:6px;'
            'padding:16px;color:#e65100"><strong>No documents loaded.</strong> '
            'Add files to the eval_documents folder or use the upload widget, '
            'then re-run this cell.</div>'
        ))
        return {}

    filenames = list(documents.keys())
    n = len(filenames)
    print(f"Deep Research mode: synthesizing {n} document(s) as a single project...")
    for fn in filenames:
        print(f"  - {fn}")

    try:
        print("\nStep 1/2: Synthesizing project intelligence across all documents...")
        synthesized_text, _ = synthesize_project(documents)
        print(f"  -> Synthesis complete ({len(synthesized_text.split()):,} words)")

        print("Step 2/2: Evaluating synthesized project "
              "(5 domains: Accuracy, Safety, Transparency, Repeatability, Trustworthiness)...")
        results = run_full_evaluation(synthesized_text)

        label = ", ".join(filenames[:3]) + ("..." if n > 3 else "")
        project_key = f"[Project — {n} file(s): {label}]"

        print(f"\n  -> Composite: {results['composite']['composite_score']} "
              f"— {results['composite']['verdict']}")
        print(f"\nDeep research evaluation complete. {n} document(s) evaluated as 1 project.")

        return {
            project_key: {
                "text": synthesized_text,
                "results": results,
                "source_files": filenames,
                "mode": "deep_research",
            }
        }

    except Exception as exc:
        print(f"ERROR in deep research evaluation: {exc}")
        return {}


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
            print(f"Evaluating with LLM (5 domains: Accuracy, Safety, Transparency, Repeatability, Trustworthiness)...")
            results = run_full_evaluation(text)
            all_results[filename] = {"text": text, "results": results}
            print(f"  -> Composite: {results['composite']['composite_score']} — {results['composite']['verdict']}")
        except Exception as exc:
            print(f"ERROR: {exc}")

    print(f"\nEvaluated {len(all_results)} document(s) successfully.")
    return all_results
