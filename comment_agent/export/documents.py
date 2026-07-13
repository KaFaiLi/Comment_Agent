import re
from io import BytesIO
from docx import Document

from comment_agent.logging_config import get_logger

logger = get_logger(__name__)


class DocumentExporter:
    """
    Handles conversion of markdown-like content to Word documents,
    saving to disk, and generating download buffers.
    """

    def __init__(self):
        pass

    @staticmethod
    def convert_markdown_to_word(markdown_content: str) -> Document:
        """
        Convert markdown-like content to a Word document.
        Supports #, ##, ### headings, bullet lists, and bold (**).
        """
        doc = Document()
        for line in markdown_content.split("\n"):
            if line.startswith("### "):
                doc.add_heading(line[4:], level=3)
            elif line.startswith("## "):
                doc.add_heading(line[3:], level=2)
            elif line.startswith("# "):
                doc.add_heading(line[2:], level=1)
            elif line.startswith("- "):
                paragraph = doc.add_paragraph(line[2:])
                paragraph.style = "List Bullet"
            else:
                # Paragraph with bold support
                paragraph = doc.add_paragraph()
                DocumentExporter._add_bold_runs(paragraph, line)
        return doc

    @staticmethod
    def _add_bold_runs(paragraph, text: str):
        """
        Add runs with bold styling for text between **...** markers.
        """
        pattern = r"(.*?)\*\*(.*?)\*\*(.*)"
        while "**" in text:
            match = re.match(pattern, text)
            if match:
                pre, bold, post = match.groups()
                paragraph.add_run(pre)
                run = paragraph.add_run(bold)
                run.bold = True
                text = post
            else:
                break
        paragraph.add_run(text)

    @staticmethod
    def save_word_doc(doc: Document, file_path: str):
        """Persist a Word document to the specified file path."""
        doc.save(file_path)
        logger.debug("Saved Word document | %s", file_path)

    @staticmethod
    def get_word_download_buffer(doc: Document) -> BytesIO:
        """Return a BytesIO buffer for direct download."""
        buffer = BytesIO()
        doc.save(buffer)
        buffer.seek(0)
        return buffer

    def save_executive_summary(
        self, executive_summary: str, comment_type: str, output_dir: str = "Outputs"
    ) -> str:
        """
        Save executive summary to a Word document, returns the file path.
        """
        doc = self.generate_executive_summary_word(executive_summary, comment_type)
        safe_comment_type = comment_type.replace(" ", "_").lower()
        file_path = f"{output_dir}/executive_summary_{safe_comment_type}.docx"
        self.save_word_doc(doc, file_path)
        return file_path

    def generate_executive_summary_word(
        self, executive_summary: str, comment_type: str
    ) -> Document:
        """
        Generate a Word document for the executive summary.
        """
        doc = Document()
        doc.add_heading(f"Executive Summary for {comment_type}", level=1)
        for line in executive_summary.split("\n"):
            if line.startswith("### "):
                doc.add_heading(line[4:], level=3)
            elif line.startswith("## "):
                doc.add_heading(line[3:], level=2)
            elif line.startswith("# "):
                doc.add_heading(line[2:], level=1)
            elif line.startswith("- "):
                paragraph = doc.add_paragraph(line[2:])
                paragraph.style = "List Bullet"
            else:
                paragraph = doc.add_paragraph()
                self._add_bold_runs(paragraph, line)
        return doc

    def convert_and_save_markdown(
        self, markdown_content: str, comment_type: str, output_dir: str = "Outputs"
    ) -> str:
        """
        Convert markdown to Word and save it as a file. Returns path.
        """
        doc = self.convert_markdown_to_word(markdown_content)
        safe_comment_type = comment_type.replace(" ", "_").lower()
        file_path = f"{output_dir}/{safe_comment_type}_full_review.docx"
        self.save_word_doc(doc, file_path)
        return file_path

    def get_word_doc_buffer_from_markdown(self, markdown_content: str) -> BytesIO:
        """
        Convert markdown to Word and provide as BytesIO buffer for download.
        """
        doc = self.convert_markdown_to_word(markdown_content)
        return self.get_word_download_buffer(doc)

    def get_word_doc_buffer_from_executive_summary(
        self, executive_summary: str, comment_type: str
    ) -> BytesIO:
        """
        Generate a Word doc from executive summary and provide as BytesIO buffer for download.
        """
        doc = self.generate_executive_summary_word(executive_summary, comment_type)
        return self.get_word_download_buffer(doc)
