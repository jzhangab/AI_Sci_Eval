"""
Deep research synthesis for project-level evaluation.
Combines multiple project documents into a single synthesized intelligence
text covering all five framework domains, then evaluates the project as one.
"""
from lib.document_parser import parse_file
from lib.llm_client import call_llm

_PER_DOC_CHAR_LIMIT = 8000

_SYNTHESIS_PROMPT = """\
You are a technical research analyst conducting a comprehensive review of an AI/LLM system project.

You have been provided with {n_docs} document(s) from this project:
{file_list}

Your task: synthesize ALL documents into a single unified project intelligence report that gives a \
complete, accurate picture of this AI/LLM system. This report will be evaluated against the \
AI/LLM Scientific Review Framework across five domains: Accuracy, Safety, Transparency, \
Repeatability, and Trustworthiness.

## Project Documents:
{combined}

## Synthesis instructions:
Consolidate and reconcile information across all documents. Write in a factual, analytical style. \
Cover the following sections — be specific and cite evidence from the documents where it exists:

1. **System Overview** — purpose, intended users, deployment context, system architecture
2. **Accuracy & Correctness** — benchmarks, performance metrics, hallucination controls, \
calibration evidence, domain-specific testing results
3. **Safety Measures** — harm refusal mechanisms, jailbreak/adversarial testing, alignment \
validation, dual-use risk assessment, red-teaming results
4. **Transparency & Documentation** — model cards, audit trail completeness, explainability \
mechanisms, regulatory documentation (EU AI Act, 21 CFR Part 11, etc.)
5. **Repeatability & Stability** — output variance testing, cross-version regression results, \
environment reproducibility, paraphrase invariance
6. **Trustworthiness** — adversarial robustness, privacy preservation, bias/fairness evaluations, \
systemic reliability metrics

Rules:
- Where information is absent from all documents, state that explicitly — do not fabricate.
- Where documents contradict each other, describe the discrepancy.
- Do not pad with generic statements. Every sentence must be grounded in the provided materials.
"""


def synthesize_project(documents: dict) -> tuple:
    """
    Parse all documents and synthesize them into a unified project intelligence text.

    Returns (synthesized_text: str, parsed_docs: dict[filename, text]).
    """
    parsed = {}
    for filename, file_bytes in documents.items():
        parsed[filename] = parse_file(filename, file_bytes)

    # Shrink per-doc limit when many documents are present to stay within LLM context
    per_doc_limit = min(_PER_DOC_CHAR_LIMIT, 60000 // max(1, len(parsed)))

    file_list = "\n".join(
        f"  - {fname} ({len(text.split()):,} words)"
        for fname, text in parsed.items()
    )
    combined = "\n\n---\n\n".join(
        f"[Document {i + 1}: {fname}]\n{text[:per_doc_limit]}"
        + ("\n...[truncated]" if len(text) > per_doc_limit else "")
        for i, (fname, text) in enumerate(parsed.items())
    )

    prompt = _SYNTHESIS_PROMPT.format(
        n_docs=len(parsed),
        file_list=file_list,
        combined=combined,
    )

    synthesized = call_llm(prompt)
    return synthesized, parsed
