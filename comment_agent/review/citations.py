import re

CITATION_RE = re.compile(r"\[(C\d+)\]")

_BLOCK_RE = re.compile(
    r"<([^>]+?) on (\d{4}-\d{2}-\d{2})>\n(.*?)\n</\1 on \2>",
    re.DOTALL,
)


def build_citation_index(combined_text):
    index = {}
    annotated_blocks = []
    for i, m in enumerate(_BLOCK_RE.finditer(combined_text or ""), start=1):
        cid = f"C{i}"
        tag, date, body = m.group(1), m.group(2), m.group(3)
        index[cid] = {"id": cid, "tag": tag, "date": date, "text": body}
        annotated_blocks.append(f"[{cid}] {m.group(0)}")
    if not index:
        return combined_text, index
    return "\n\n".join(annotated_blocks), index


def resolve_topic_references(topics, index):
    """Ground each topic item's `references` in the citation index in place.
    Returns the number of unsupported references dropped."""
    topics = topics or []
    cleaned, dropped = resolve_references([t.references for t in topics], index)
    for topic, refs in zip(topics, cleaned):
        topic.references = refs
    return dropped


def resolve_references(ref_lists, index):
    cleaned = []
    dropped = 0
    for refs in (ref_lists or []):
        topic_refs = []
        seen = set()
        for ref in (refs or []):
            valid = [cid for cid in CITATION_RE.findall(str(ref)) if cid in index]
            if not valid:
                dropped += 1
                continue
            for cid in valid:
                if cid not in seen:
                    seen.add(cid)
                    topic_refs.append(f"[{cid}] ({index[cid]['date']})")
        cleaned.append(topic_refs)
    return cleaned, dropped
