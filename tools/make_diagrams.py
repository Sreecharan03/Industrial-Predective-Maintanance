"""Generate the architecture diagrams for the technical walkthrough.

Kept in the repo so the diagrams can be regenerated when the architecture
changes, rather than drifting from it as hand-drawn images would.
"""

from __future__ import annotations

import pathlib

from graphviz import Digraph

OUT = pathlib.Path(__file__).resolve().parent.parent / "docs" / "diagrams"
OUT.mkdir(parents=True, exist_ok=True)

INK = "#1C1917"
MUTED = "#57534E"
BRAND = "#7C3AED"
TEAL = "#0F9D8F"
AMBER = "#B45309"
CRIT = "#BE123C"
OK = "#15803D"
BLUE = "#0284C7"
LINE = "#D6D3D1"

FONT = "Helvetica"


def base(name: str, rankdir: str = "TB", size: str = "7,9") -> Digraph:
    g = Digraph(name, format="png")
    g.attr(rankdir=rankdir, bgcolor="white", size=size, dpi="200",
           fontname=FONT, splines="true", nodesep="0.28", ranksep="0.38")
    g.attr("node", shape="box", style="rounded,filled", fontname=FONT,
           fontsize="11", color=LINE, fillcolor="#FAFAF9", fontcolor=INK,
           margin="0.16,0.10", penwidth="1.2")
    g.attr("edge", color=MUTED, arrowsize="0.7", penwidth="1.1", fontname=FONT,
           fontsize="9", fontcolor=MUTED)
    return g


def box(g, name, label, fill="#FAFAF9", border=LINE, font=INK, **kw):
    g.node(name, label, fillcolor=fill, color=border, fontcolor=font, **kw)


# ----------------------------------------------------------------- 1
def architecture() -> None:
    """The whole platform on one page."""
    g = base("architecture", size="7.2,10")

    box(g, "assets", "INDUSTRIAL ASSETS\\n6 machines · compressors, chillers, N₂ plant",
        fill="#F5F5F4", font=MUTED, border=MUTED)

    with g.subgraph(name="cluster_l1") as c:
        c.attr(label="  LAYER 1 · DATA FOUNDATION  ", style="rounded", color=LINE,
               fontname=FONT, fontsize="10", fontcolor=MUTED, bgcolor="#FEFEFE")
        box(c, "ingest", "Ingestion\\nCSV · REST · (OPC-UA planned)")
        box(c, "validate", "Validation\\nmissing · duplicate · timestamp · units · quality")
        box(c, "tsdb", "TimescaleDB\\nsensor_history schema · hypertable",
            fill="#EFF6FF", border=BLUE, font="#075985")

    with g.subgraph(name="cluster_l2") as c:
        c.attr(label="  LAYER 2 · DETERMINISTIC ANALYTICS  ", style="rounded", color=LINE,
               fontname=FONT, fontsize="10", fontcolor=MUTED)
        box(c, "engines",
            "7 Engines\\nQuality · Statistics · Operating State · Envelope\\n"
            "Threshold · Timeline · Reliability",
            fill="#F5F3FF", border=BRAND, font="#5B21B6")
        box(c, "health", "Health Engine\\ncomposes the four above", fill="#F5F3FF",
            border=BRAND, font="#5B21B6")
        box(c, "findings", "FINDINGS\\nimmutable · evidence-backed · append-only",
            fill="#EDE9FE", border=BRAND, font="#5B21B6", penwidth="2")

    with g.subgraph(name="cluster_l3") as c:
        c.attr(label="  LAYER 3 · KNOWLEDGE  ", style="rounded", color=LINE,
               fontname=FONT, fontsize="10", fontcolor=MUTED)
        box(c, "kg", "Knowledge Graph\\nequipment → subsystem → sensor → condition",
            fill="#E7F6F4", border=TEAL, font="#0B6E63")
        box(c, "rules", "Rule Engine\\nFinding A + Finding B → diagnosis",
            fill="#E7F6F4", border=TEAL, font="#0B6E63")

    with g.subgraph(name="cluster_l4") as c:
        c.attr(label="  LAYER 4 · MACHINE LEARNING (advisory only)  ", style="rounded",
               color=LINE, fontname=FONT, fontsize="10", fontcolor=MUTED)
        box(c, "features", "Feature Pipeline\\nwindow → normalise → reliability-weight")
        box(c, "ml", "Isolation Forest · Gaussian Mixture\\nForecasting (backtest-selected)",
            fill="#FDF4FF", border="#C026D3", font="#86198F")

    with g.subgraph(name="cluster_l5") as c:
        c.attr(label="  LAYER 5 · REASONING  ", style="rounded", color=LINE,
               fontname=FONT, fontsize="10", fontcolor=MUTED)
        box(c, "llm", "Grounded LLM\\nevidence → prompt → citation validation",
            fill="#FFF7ED", border=AMBER, font="#9A3412")

    box(g, "out", "DASHBOARD · REST API · ESCALATION EMAIL",
        fill="#F5F5F4", font=INK, border=MUTED, penwidth="1.5")

    g.edge("assets", "ingest")
    g.edge("ingest", "validate")
    g.edge("validate", "tsdb")
    g.edge("tsdb", "engines", label="  IngestedSeries")
    g.edge("engines", "health")
    g.edge("health", "findings")
    g.edge("engines", "findings")
    g.edge("findings", "kg", label="  projection")
    g.edge("findings", "rules")
    g.edge("rules", "findings", label="  diagnoses  ", style="dashed", constraint="false")
    g.edge("tsdb", "features", style="dashed")
    g.edge("features", "ml")
    g.edge("ml", "findings", label="  hypotheses  ", style="dashed")
    g.edge("kg", "llm")
    g.edge("findings", "llm", label="  evidence")
    g.edge("llm", "out")
    g.edge("findings", "out", style="dashed")

    g.render(OUT / "01-architecture", cleanup=True)


# ----------------------------------------------------------------- 2
def reading_lifecycle() -> None:
    """One real reading, end to end."""
    g = base("lifecycle", size="7.2,10")

    steps = [
        ("r", "SENSOR READING\\n280.45 — discharge pressure, SC-126\\n2026-07-20 06:01:00",
         "#F5F5F4", MUTED, MUTED),
        ("v", "VALIDATION\\ntimestamp aligned · unit checked · quality = 0 (good)", None, None, None),
        ("s", "STORED\\nsensor_history.sensor_reading (hypertable chunk)",
         "#EFF6FF", BLUE, "#075985"),
        ("e", "THRESHOLD ENGINE\\n280.45 > 280.0 protection setpoint → CRITICAL",
         "#F5F3FF", BRAND, "#5B21B6"),
        ("f", "FINDING 7a2b317cca6cd33b\\n\"discharge_pressure reached a critical threshold state\"\\n"
         "severity=critical · confidence=1.0 · evidence=280.45",
         "#EDE9FE", BRAND, "#5B21B6"),
        ("k", "KNOWLEDGE GRAPH\\ncondition:2536… --observed_on--> sensor:SC-126:discharge_pressure\\n"
         "condition:2536… --has_evidence--> artifact:SC-126__threshold",
         "#E7F6F4", TEAL, "#0B6E63"),
        ("ru", "RULE ENGINE\\npressure critical + condenser-side degradation\\n→ condenser fouling suspected",
         "#E7F6F4", TEAL, "#0B6E63"),
        ("h", "HEALTH CASCADE\\nsensor → compression subsystem → equipment SC-126",
         "#F5F3FF", BRAND, "#5B21B6"),
        ("a", "ALERT POLICY\\nnewly critical → 3 alert rows, same transaction",
         "#FEF2F2", CRIT, "#9F1239"),
        ("m", "EMAIL 06:01:05\\none report, three conditions, delivered",
         "#FEF2F2", CRIT, "#9F1239"),
        ("l", "COPILOT\\n\"discharge pressure has breached a protection setpoint\"\\n"
         "cited: 7a2b317cca6cd33b", "#FFF7ED", AMBER, "#9A3412"),
        ("d", "DASHBOARD\\n\"Discharge pressure has gone past its safe limit —\\nit is at 280.45 right now\"",
         "#F0FDF4", OK, "#166534"),
    ]
    for name, label, fill, border, font in steps:
        if fill:
            box(g, name, label, fill=fill, border=border, font=font)
        else:
            box(g, name, label)

    order = [s[0] for s in steps]
    labels = {
        ("r", "v"): "  arrives",
        ("s", "e"): "  loaded as IngestedSeries",
        ("e", "f"): "  assembled",
        ("f", "k"): "  projected",
        ("a", "m"): "  after commit",
    }
    for a, b in zip(order, order[1:], strict=False):
        g.edge(a, b, label=labels.get((a, b), ""))

    g.render(OUT / "02-reading-lifecycle", cleanup=True)


# ----------------------------------------------------------------- 3
def health_engine() -> None:
    """How a health score is composed."""
    g = base("health", rankdir="LR", size="7,3.4")
    for n, lbl in (("t", "Threshold\\nstate"), ("e", "Operating\\nenvelope"),
                   ("r", "Sensor\\nreliability"), ("ti", "Operational\\ntimeline")):
        box(g, n, lbl, fill="#F5F3FF", border=BRAND, font="#5B21B6")
    box(g, "h", "HEALTH ENGINE\\nweighted, deterministic\\nno ML", fill="#EDE9FE",
        border=BRAND, font="#5B21B6", penwidth="2")
    box(g, "s", "Sensor\\nhealth")
    box(g, "sub", "Subsystem\\nhealth")
    box(g, "eq", "Equipment\\nhealth", fill="#E7F6F4", border=TEAL, font="#0B6E63")
    for n in ("t", "e", "r", "ti"):
        g.edge(n, "h")
    g.edge("h", "s")
    g.edge("s", "sub", label="  roll-up")
    g.edge("sub", "eq", label="  roll-up")
    g.render(OUT / "03-health-engine", cleanup=True)


# ----------------------------------------------------------------- 4
def rule_engine() -> None:
    """Multi-signal diagnosis."""
    g = base("rules", size="6.6,5")
    box(g, "a", "FINDING A\\ndischarge pressure critical\\n(threshold engine)",
        fill="#EDE9FE", border=BRAND, font="#5B21B6")
    box(g, "b", "FINDING B\\ncondenser-side degradation\\n(envelope + statistics)",
        fill="#EDE9FE", border=BRAND, font="#5B21B6")
    box(g, "c", "FINDING C\\nsuction conditions normal\\n(rules out alternatives)",
        fill="#EDE9FE", border=BRAND, font="#5B21B6")
    box(g, "r", "RULE\\nsustained high discharge pressure\\n+ condenser-side degradation\\n"
        "+ normal suction\\n= classic fouling signature",
        fill="#E7F6F4", border=TEAL, font="#0B6E63", penwidth="2")
    box(g, "d", "DIAGNOSIS  (origin = diagnosed)\\n\"Condenser fouling suspected\"\\n"
        "triggered_by = [A, B, C]", fill="#CCFBF1", border=TEAL, font="#0B6E63", penwidth="2")
    box(g, "g", "KNOWLEDGE GRAPH\\ntriggered_by edges preserve the reasoning chain",
        fill="#E7F6F4", border=TEAL, font="#0B6E63")
    for n in ("a", "b", "c"):
        g.edge(n, "r")
    g.edge("r", "d")
    g.edge("d", "g")
    g.render(OUT / "04-rule-engine", cleanup=True)


# ----------------------------------------------------------------- 5
def feature_pipeline() -> None:
    """What the ML models actually consume."""
    g = base("features", rankdir="LR", size="7.4,2.6")
    seq = [
        ("h", "Sensor history\\n(validated only)", "#EFF6FF", BLUE, "#075985"),
        ("w", "Window\\n48 readings", None, None, None),
        ("a", "Aggregate\\nper-sensor mean", None, None, None),
        ("z", "Normalise\\nz-score", None, None, None),
        ("rw", "Reliability\\nweighting", "#FEF3C7", AMBER, "#92400E"),
        ("f", "FeatureFrame", "#FDF4FF", "#C026D3", "#86198F"),
        ("m", "Isolation Forest\\nGaussian Mixture", "#FDF4FF", "#C026D3", "#86198F"),
    ]
    for n, lbl, fill, border, font in seq:
        if fill:
            box(g, n, lbl, fill=fill, border=border, font=font)
        else:
            box(g, n, lbl)
    names = [s[0] for s in seq]
    for a, b in zip(names, names[1:], strict=False):
        g.edge(a, b)
    g.render(OUT / "05-feature-pipeline", cleanup=True)


# ----------------------------------------------------------------- 6
def llm_pipeline() -> None:
    """ADR-018: how an answer is grounded."""
    g = base("llm", size="6.8,7.5")
    box(g, "f", "Findings\\n(facts, diagnoses, hypotheses)", fill="#EDE9FE",
        border=BRAND, font="#5B21B6")
    box(g, "k", "Knowledge graph\\n(relationships, evidence links)", fill="#E7F6F4",
        border=TEAL, font="#0B6E63")
    box(g, "er", "EVIDENCE RETRIEVER\\nselects relevant findings for the question\\n"
        "— never raw sensor values")
    box(g, "pb", "PROMPT BUILDER\\npersona · absolute rules · evidence JSON\\n"
        "\"never escalate what the engines did not\"")
    box(g, "m", "LANGUAGE MODEL\\nGroq llama-3.3-70b  |  offline stub",
        fill="#FFF7ED", border=AMBER, font="#9A3412")
    box(g, "cv", "CITATION VALIDATOR\\nevery claim must cite a finding id\\n"
        "uncited claims are DELETED", fill="#FEF2F2", border=CRIT, font="#9F1239",
        penwidth="2")
    box(g, "ans", "GROUNDED ANSWER\\nclaims + citations + what it could not answer",
        fill="#F0FDF4", border=OK, font="#166534", penwidth="2")
    g.edge("f", "er")
    g.edge("k", "er")
    g.edge("er", "pb", label="  EvidenceItems")
    g.edge("pb", "m")
    g.edge("m", "cv", label="  draft claims")
    g.edge("cv", "ans", label="  survivors only")
    g.render(OUT / "06-llm-pipeline", cleanup=True)


# ----------------------------------------------------------------- 7
def why_graph() -> None:
    """Why a graph rather than another table."""
    g = base("whygraph", rankdir="LR", size="7.2,4.2")
    box(g, "eq", "Equipment\\nSC-126", fill="#E7F6F4", border=TEAL, font="#0B6E63")
    box(g, "sub", "Subsystem\\ncompression", fill="#E7F6F4", border=TEAL, font="#0B6E63")
    box(g, "sen", "Sensor\\ndischarge_pressure", fill="#E7F6F4", border=TEAL, font="#0B6E63")
    box(g, "th", "Threshold\\n280 critical")
    box(g, "c1", "Condition\\npressure critical", fill="#EDE9FE", border=BRAND, font="#5B21B6")
    box(g, "c2", "Condition\\ncondenser fouling", fill="#EDE9FE", border=BRAND, font="#5B21B6")
    box(g, "ar", "Evidence\\nthreshold artifact")
    box(g, "val", "Engineer verdict\\nconfirmed", fill="#F0FDF4", border=OK, font="#166534")
    g.edge("eq", "sub", label="has_subsystem")
    g.edge("sub", "sen", label="has_sensor")
    g.edge("sen", "th", label="governed_by")
    g.edge("c1", "sen", label="observed_on")
    g.edge("c1", "ar", label="has_evidence")
    g.edge("c2", "c1", label="triggered_by")
    g.edge("c2", "val", label="validated_by")
    g.render(OUT / "07-knowledge-graph", cleanup=True)


if __name__ == "__main__":
    architecture()
    reading_lifecycle()
    health_engine()
    rule_engine()
    feature_pipeline()
    llm_pipeline()
    why_graph()
    for p in sorted(OUT.glob("*.png")):
        print(f"  {p.name}  {p.stat().st_size // 1024} KB")
