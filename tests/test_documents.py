from comment_agent.export.documents import DocumentExporter


def test_markdown_buffer_nonempty():
    exporter = DocumentExporter()
    buf = exporter.get_word_doc_buffer_from_markdown("# Title\n- bullet\n**bold** text")
    data = buf.getvalue()
    assert data[:2] == b"PK"  # docx is a zip
    assert len(data) > 0


def test_save_executive_summary_writes_file(tmp_path):
    exporter = DocumentExporter()
    path = exporter.save_executive_summary("## Summary\ncontent", "PnL Comment",
                                           output_dir=str(tmp_path))
    assert path.endswith(".docx")
