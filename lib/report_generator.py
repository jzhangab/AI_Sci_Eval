"""
Report generation utilities.
Produces styled HTML and DataFrame outputs for Dataiku notebook display.
"""
import datetime
import pandas as pd
from IPython.display import HTML, display


def _style_map(styler, func, **kwargs):
    """Compatibility wrapper: uses Styler.map (pandas >=2.1) or applymap (older)."""
    if hasattr(styler, "map"):
        return styler.map(func, **kwargs)
    return styler.applymap(func, **kwargs)


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
    s = df.style
    s = _style_map(s, lambda v: f"color: {_score_color(v)}" if isinstance(v, (int, float)) else "", subset=["Score"])
    s = _style_map(s, lambda v: "color: #c62828; font-weight: bold" if v == "FAIL" else "", subset=["Below 40"])
    display(HTML(s.hide(axis="index").to_html()))


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
                "Evidence": c.get("evidence", "")[:120] or "—",
                "Gap": c.get("gap", "")[:120] or "None",
            })
        s = pd.DataFrame(rows).style
        s = _style_map(s, lambda v: f"color: {_score_color(v)}" if isinstance(v, (int, float)) and v <= 100 else "", subset=["Score"])
        display(HTML(s.hide(axis="index").to_html()))


def display_full_report(filename, results):
    """Render the complete evaluation report."""
    display_header(filename)
    display_verdict(results["composite"])
    display_domain_summary(results["domains"])
    display(HTML("<hr><h3>Detailed Domain Evaluation</h3>"))
    display_domain_detail(results["domains"])


def results_to_dataframe(results):
    """Convert a single document's results to a flat DataFrame."""
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
                "evidence": c.get("evidence", ""),
                "gap": c.get("gap", ""),
            })
    df = pd.DataFrame(rows)
    df["composite_score"] = results["composite"]["composite_score"]
    df["verdict"] = results["composite"]["verdict"]
    return df


# ---------------------------------------------------------------------------
# Batch / orchestration functions (called directly from notebook cells)
# ---------------------------------------------------------------------------

def display_all_reports(all_results):
    """Render evaluation reports for every document in all_results."""
    for filename, data in all_results.items():
        display_full_report(filename, data["results"])
        display(HTML("<br><hr style='border:2px solid #ccc'><br>"))


def export_results(all_results):
    """
    Combine all document results into a single exportable DataFrame.
    Displays the table and returns the DataFrame.
    """
    frames = []
    for filename, data in all_results.items():
        df = results_to_dataframe(data["results"])
        df.insert(0, "document", filename)
        frames.append(df)

    if not frames:
        print("No results to export.")
        return pd.DataFrame()

    results_df = pd.concat(frames, ignore_index=True)
    display(HTML("<h3>Results DataFrame (exportable)</h3>"))
    display(results_df)
    return results_df


def display_comparison(all_results):
    """Show a side-by-side comparison table when multiple documents were evaluated."""
    if len(all_results) <= 1:
        print("Upload multiple documents to see a comparison table.")
        return

    rows = []
    for filename, data in all_results.items():
        r = data["results"]
        row = {"Document": filename}
        for domain, ddata in r["domains"].items():
            row[domain] = ddata["score"]
        row["Composite"] = r["composite"]["composite_score"]
        row["Verdict"] = r["composite"]["verdict"]
        rows.append(row)

    display(HTML("<h3>Multi-Document Comparison</h3>"))
    display(HTML(pd.DataFrame(rows).style.hide(axis="index").to_html()))


# ===========================================================================
# AI Artifact Evaluation — display and export functions
# ===========================================================================

def _artifact_header(filename):
    display(HTML(f"""
    <div style="background:linear-gradient(135deg,#b71c1c,#c62828);color:white;padding:24px 32px;border-radius:8px;margin-bottom:16px">
        <h1 style="margin:0;font-size:24px">AI Artifact Evaluation</h1>
        <p style="margin:4px 0 0;opacity:0.85">Artifact Review &mdash; {filename}</p>
        <p style="margin:2px 0 0;opacity:0.65;font-size:12px">Generated {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}</p>
    </div>
    """))


def _artifact_domain_detail(domain_results):
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
                "Evidence": c.get("evidence", "")[:120] or "—",
                "Issues": c.get("issues", "")[:120] or "None",
            })
        s = pd.DataFrame(rows).style
        s = _style_map(s, lambda v: f"color: {_score_color(v)}" if isinstance(v, (int, float)) and v <= 100 else "", subset=["Score"])
        display(HTML(s.hide(axis="index").to_html()))


def display_artifact_report(filename, results):
    """Render a single artifact evaluation report."""
    _artifact_header(filename)
    display_verdict(results["composite"])
    display_domain_summary(results["domains"])
    display(HTML("<hr><h3>Detailed Artifact Evaluation</h3>"))
    _artifact_domain_detail(results["domains"])


def artifact_results_to_dataframe(results):
    """Convert a single artifact's results to a flat DataFrame."""
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
                "evidence": c.get("evidence", ""),
                "issues": c.get("issues", ""),
            })
    df = pd.DataFrame(rows)
    df["composite_score"] = results["composite"]["composite_score"]
    df["verdict"] = results["composite"]["verdict"]
    return df


# --- Batch orchestration for artifacts ---

def display_all_artifact_reports(all_results):
    """Render artifact evaluation reports for every artifact."""
    for filename, data in all_results.items():
        display_artifact_report(filename, data["results"])
        display(HTML("<br><hr style='border:2px solid #ccc'><br>"))


def export_artifact_results(all_results):
    """Combine all artifact results into a single exportable DataFrame."""
    frames = []
    for filename, data in all_results.items():
        df = artifact_results_to_dataframe(data["results"])
        df.insert(0, "artifact", filename)
        frames.append(df)

    if not frames:
        print("No artifact results to export.")
        return pd.DataFrame()

    results_df = pd.concat(frames, ignore_index=True)
    display(HTML("<h3>Artifact Results DataFrame (exportable)</h3>"))
    display(results_df)
    return results_df


def display_artifact_comparison(all_results):
    """Side-by-side comparison for multiple artifacts."""
    if len(all_results) <= 1:
        print("Upload multiple artifacts to see a comparison table.")
        return

    rows = []
    for filename, data in all_results.items():
        r = data["results"]
        row = {"Artifact": filename}
        for domain, ddata in r["domains"].items():
            row[domain] = ddata["score"]
        row["Composite"] = r["composite"]["composite_score"]
        row["Verdict"] = r["composite"]["verdict"]
        rows.append(row)

    display(HTML("<h3>Multi-Artifact Comparison</h3>"))
    display(HTML(pd.DataFrame(rows).style.hide(axis="index").to_html()))
