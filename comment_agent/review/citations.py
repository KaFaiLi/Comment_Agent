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
