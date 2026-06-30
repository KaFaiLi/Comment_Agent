def format_key_metrics(data):
    output = ["### Overview", data.Summary, ""]

    topics = data.KeyMetricTopic or []
    variations_list = data.KeyMetricVariation or []
    references_list = getattr(data, "Reference", []) or []

    for i, topic in enumerate(topics):
        variations = variations_list[i] if i < len(variations_list) else []
        reference = references_list[i] if i < len(references_list) else []

        output.append(f"### Key Metric Topic {i + 1}: {topic}")
        output.append("**Variations:**")
        output.append("\n".join(f"- {v}" for v in variations))
        output.append("")
        output.append(f"**Reference for Topic {i + 1}:** " + ", ".join(reference))
        output.append("")

    return "\n".join(output)


def format_recurrent_topics(data):
    output = ["### Overview", data.Summary, ""]

    topics = data.RecurrentTopic or []
    explains = data.RecurrentTopicExplain or []
    references = getattr(data, "Reference", []) or []
    patterns = getattr(data, "pattern", []) or []

    for i, topic in enumerate(topics):
        explanation_list = explains[i] if i < len(explains) else []
        reference_list = references[i] if i < len(references) else []
        pattern_list = patterns[i] if i < len(patterns) else []

        output.append(f"### Recurrent Topic {i + 1}: {topic}")
        output.append("**Explanations:**")
        output.append("\n".join(f"- {e}" for e in explanation_list))
        output.append("")
        output.append(f"**Pattern for Topic {i + 1}:** " + ", ".join(pattern_list))
        output.append("")
        output.append(f"**Reference for Topic {i + 1}:** " + ", ".join(reference_list))
        output.append("")

    output.append("### Technical Issues")
    tech_issues = getattr(data, "Tech_issue", []) or []
    output.append(
        tech_issues[0] if tech_issues else "No specific technical issues reported."
    )

    return "\n".join(output)
