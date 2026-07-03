from comment_agent.review.citations import CITATION_RE


def _sources_appendix(reference_lists, index):
    if not index:
        return ""
    cited = []
    seen = set()
    for refs in (reference_lists or []):
        for ref in (refs or []):
            for cid in CITATION_RE.findall(str(ref)):
                if cid in index and cid not in seen:
                    seen.add(cid)
                    cited.append(cid)
    if not cited:
        return ""
    lines = ["", "## Sources"]
    for cid in cited:
        e = index[cid]
        text = " ".join(e["text"].split())
        lines.append(f'- [{cid}] — {e["tag"]} on {e["date"]}: "{text}"')
    return "\n".join(lines)


def format_key_metrics(data, index=None):
    output = ["### Overview", data.summary, ""]

    topics = data.topics or []
    for i, item in enumerate(topics):
        output.append(f"### Key Metric Topic {i + 1}: {item.topic}")
        output.append("**Variations:**")
        output.append("\n".join(f"- {v}" for v in (item.analysis or [])))
        output.append("")
        output.append(f"**Reference for Topic {i + 1}:** " + ", ".join(item.references or []))
        output.append("")

    appendix = _sources_appendix([t.references or [] for t in topics], index)
    if appendix:
        output.append(appendix)
    return "\n".join(output)


def format_recurrent_topics(data, index=None):
    output = ["### Overview", data.summary, ""]

    topics = data.topics or []
    for i, item in enumerate(topics):
        explanations = [
            f"Contextual Explanation: {item.context}",
            f"Reasons for Recurrence: {item.recurrence_reason}",
            f"Implications and Significance: {item.implications}",
        ]
        output.append(f"### Recurrent Topic {i + 1}: {item.topic}")
        output.append("**Explanations:**")
        output.append("\n".join(f"- {e}" for e in explanations))
        output.append("")
        output.append(f"**Pattern for Topic {i + 1}:** {item.pattern}")
        output.append("")
        output.append(f"**Reference for Topic {i + 1}:** " + ", ".join(item.references or []))
        output.append("")

    output.append("### Technical Issues")
    tech_issues = data.tech_issues or []
    output.append(
        tech_issues[0] if tech_issues else "No specific technical issues reported."
    )

    appendix = _sources_appendix([t.references or [] for t in topics], index)
    if appendix:
        output.append(appendix)
    return "\n".join(output)
