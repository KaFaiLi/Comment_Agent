import os


def save_intermediates(final_df, output_dir: str) -> str:
    os.makedirs(output_dir, exist_ok=True)
    path = os.path.join(output_dir, "All comments.xlsx")
    final_df.to_excel(path, index=False)
    return path


def save_results(quarterly_reviews: dict, markdown_by_type: dict,
                 summary_by_type: dict, output_dir: str, exporter) -> None:
    os.makedirs(output_dir, exist_ok=True)
    for comment_type, markdown in markdown_by_type.items():
        safe = comment_type.replace(" ", "_").lower()

        md_path = os.path.join(output_dir, f"quarterly_reviews_summary_{safe}.md")
        with open(md_path, "w", encoding="utf-8") as fh:
            fh.write(markdown)

        exporter.convert_and_save_markdown(markdown, comment_type, output_dir=output_dir)
        summary = summary_by_type.get(comment_type, "")
        exporter.save_executive_summary(summary, comment_type, output_dir=output_dir)
