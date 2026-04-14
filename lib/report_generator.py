"""
Report generation utilities.
Produces styled HTML and DataFrame outputs for Dataiku notebook display.
"""
import datetime
import pandas as pd
from IPython.display import HTML, display


# ---------------------------------------------------------------------------
# Color helpers
# ---------------------------------------------------------------------------

def _score_color(score):
    if score >= 85:
        return "#2e7d32"  # green
    if score >= 70:
        return "#1565c0"  # blue
    if score >= 55:
        return "#f9a825"  # amber
    if score >= 40:
        return "#e65100"  # orange
    return "#c62828"      # red


def _severity_color(severity):
    return {"HIGH": "#c62828", "MEDIUM": "#e65100", "LOW": "#f9a825"}.get(severity, "#666")


def _verdict_color(verdict):
    if "Full Approval" in verdict:
        return "#2e7d32"
    if "Conditional" in verdict:
        return "#1565c0"
    return "#c62828"


def _bar_html(score, width=200):
    color = _score_color(score)
    filled = int(width * score / 100)
    return (
        f'<div style="background:#e0e0e0;border-radius:4px;width:{width}px;display:inline-block">'
        f'<div style="background:{color};height:16px;border-radius:4px;width:{filled}px"></div>'
        f'</div> <strong style="color:{color}">{score}</strong>'
    )


# ---------------------------------------------------------------------------
# Display functions
# ---------------------------------------------------------------------------

def display_header(filename):
    display(HTML(f"""
    <div style="background:linear-gradient(135deg,#1a237e,#283593);color:white;padding:24px 32px;border-radius:8px;margin-bottom:16px">
        <h1 style="margin:0;font-size:24px">AI / LLM Scientific Review Framework</h1>
        <p style="margin:4px 0 0;opacity:0.85">Evaluation Report &mdash; {filename}</p>
        <p style="margin:2px 0 0;opacity:0.65;font-size:12px">Generated {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}</p>
    </div>
    """))


def display_verdict(composite):
    verdict = composite["verdict"]
    score = composite["composite_score"]
    color = _verdict_color(verdict)
    interp = composite["interpretation"]
    crit = " | CRITICAL DOMAIN FAILURE" if composite["critical_failure"] else ""
    display(HTML(f"""
    <div style="border:3px solid {color};border-radius:8px;padding:20px;margin-bottom:16px;text-align:center">
        <h2 style="margin:0;color:{color}">{verdict}</h2>
        <p style="font-size:36px;margin:8px 0;font-weight:bold;color:{color}">{score} / 100</p>
        <p style="margin:0;color:#555">{interp['label']} &mdash; {interp['action']}{crit}</p>
    </div>
    """))


def display_domain_summary(domain_results):
    rows = []
    for domain, data in domain_results.items():
        rows.append({
            "Domain": domain,
            "Weight": f"{int(data['weight']*100)}%",
            "Score": data["score"],
            "Interpretation": data["interpretation"]["label"],
            "Critical": "Yes" if data["is_critical"] else "",
            "Below 40": "FAIL" if data["below_threshold"] else "Pass",
        })
    df = pd.DataFrame(rows)
    display(HTML("<h3>Domain Scores</h3>"))
    display(df.style.applymap(
        lambda v: f"color: {_score_color(v)}" if isinstance(v, (int, float)) else "",
        subset=["Score"]
    ).applymap(
        lambda v: "color: #c62828; font-weight: bold" if v == "FAIL" else "",
        subset=["Below 40"]
    ).hide(axis="index").to_html())


def display_domain_detail(domain_results):
    for domain, data in domain_results.items():
        color = _score_color(data["score"])
        display(HTML(f"""
        <div style="border-left:4px solid {color};padding:8px 16px;margin:12px 0">
            <h4 style="margin:0">{domain} — {_bar_html(data['score'], 180)}</h4>
        </div>
        """))
        rows = []
        for c in data["criteria"]:
            rows.append({
                "Criterion": c["name"],
                "Rigor": c["rigor"],
                "Score": c["score"],
                "Keywords Found": len(c["keywords_found"]),
                "Keywords Total": c["keywords_total"],
                "Matches": ", ".join(c["keywords_found"][:5]) or "None",
            })
        display(pd.DataFrame(rows).style.applymap(
            lambda v: f"color: {_score_color(v)}" if isinstance(v, (int, float)) and v <= 100 else "",
            subset=["Score"]
        ).hide(axis="index").to_html())


def display_design_patterns(design_results):
    display(HTML("<h3>Modern Design Pattern Requirements</h3>"))
    for pillar, data in design_results.items():
        color = _score_color(data["score"])
        display(HTML(f"""
        <div style="border-left:4px solid {color};padding:8px 16px;margin:12px 0">
            <h4 style="margin:0">{pillar} — {data['matched_count']}/{data['total_count']} ({data['score']}%)</h4>
        </div>
        """))
        rows = []
        for item in data["items"]:
            rows.append({
                "Requirement": item["requirement"][:80],
                "Found": "Yes" if item["found"] else "No",
                "Matched Keywords": ", ".join(item["keywords_matched"][:3]) or "—",
            })
        display(pd.DataFrame(rows).style.applymap(
            lambda v: "color: #2e7d32" if v == "Yes" else ("color: #c62828" if v == "No" else ""),
            subset=["Found"]
        ).hide(axis="index").to_html())


def display_risk_register(risk_results, addressed_count, total_count):
    display(HTML(f"<h3>Risk Register Coverage — {addressed_count}/{total_count} Addressed</h3>"))
    rows = []
    for r in risk_results:
        rows.append({
            "Risk": r["risk"],
            "Severity": r["severity"],
            "Addressed": "Yes" if r["addressed"] else "No",
            "Keywords Found": ", ".join(r["keywords_found"][:3]) or "—",
        })
    display(pd.DataFrame(rows).style.applymap(
        lambda v: f"color: {_severity_color(v)}" if v in ("HIGH", "MEDIUM", "LOW") else "",
        subset=["Severity"]
    ).applymap(
        lambda v: "color: #2e7d32" if v == "Yes" else ("color: #c62828" if v == "No" else ""),
        subset=["Addressed"]
    ).hide(axis="index").to_html())


def display_full_report(filename, results):
    """Render the complete evaluation report."""
    display_header(filename)
    display_verdict(results["composite"])
    display_domain_summary(results["domains"])
    display(HTML("<hr><h3>Detailed Domain Evaluation</h3>"))
    display_domain_detail(results["domains"])
    display(HTML("<hr>"))
    display_design_patterns(results["design_patterns"])
    display(HTML("<hr>"))
    display_risk_register(
        results["risk_register"],
        results["risks_addressed"],
        results["risks_total"],
    )


def results_to_dataframe(results):
    """Convert results to a flat DataFrame suitable for Dataiku dataset export."""
    rows = []
    for domain, data in results["domains"].items():
        for c in data["criteria"]:
            rows.append({
                "domain": domain,
                "domain_weight": data["weight"],
                "domain_score": data["score"],
                "criterion": c["name"],
                "criterion_rigor": c["rigor"],
                "criterion_score": c["score"],
                "keywords_found": len(c["keywords_found"]),
                "keywords_total": c["keywords_total"],
                "keyword_matches": "; ".join(c["keywords_found"]),
            })
    df = pd.DataFrame(rows)
    df["composite_score"] = results["composite"]["composite_score"]
    df["verdict"] = results["composite"]["verdict"]
    return df
