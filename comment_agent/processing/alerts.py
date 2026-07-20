import os
import re

import pandas as pd

from comment_agent.logging_config import get_logger
from comment_agent.processing.columns import EVIDENCE_COLUMNS

logger = get_logger(__name__)


_CERTIFICATION_REVIEW_TYPES = {
    "VAR": "VAR_SVAR Comment",
    "SVAR": "VAR_SVAR Comment",
    "STRESS TEST": "Stress Test Comment",
}


class AlertProcessor:
    """Build canonical, source-row-level review evidence for selected desks."""

    def __init__(self, cert_path, ia_path, pnl_path, output_dir="Outputs"):
        self.cert_df = pd.read_csv(cert_path)
        self.ia_alert_df = pd.read_csv(ia_path)
        self.pnl_comment_df = pd.read_csv(pnl_path)
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)

        self._require_columns(self.cert_df, [
            "perimeter_name", "trading_desk", "indicator_name", "error_message",
            "comment", "managerial_validation_comment", "related_scenario", "as_of_date",
        ], "certification alert")
        self._require_columns(self.ia_alert_df, [
            "perimeter_name", "mmg_bl_comment", "mmg_xbc_comment",
            "managerial_validation_comment", "as_of_date",
        ], "income attribution alert")
        self._require_columns(
            self.pnl_comment_df, ["Trading Desk", "Comments", "Date"], "PnL comment"
        )
        logger.info(
            "Loaded source CSVs | cert=%d rows | ia=%d rows | pnl=%d rows | output_dir=%s",
            len(self.cert_df), len(self.ia_alert_df), len(self.pnl_comment_df), output_dir,
        )

    @staticmethod
    def _require_columns(df, columns, source_name):
        missing = [column for column in columns if column not in df.columns]
        if missing:
            logger.error("%s CSV missing columns: %s", source_name, missing)
            raise ValueError(f"{source_name} CSV missing columns: {missing}")

    @staticmethod
    def _normalise_desks(desks) -> list[str]:
        if isinstance(desks, str):
            desks = [desks]
        normalised = [str(desk).strip() for desk in (desks or []) if str(desk).strip()]
        if not normalised:
            raise ValueError("At least one desk is required")
        return normalised

    @staticmethod
    def _desk_pattern(desks) -> str:
        return r"(?:" + "|".join(map(re.escape, desks)) + r")"

    @staticmethod
    def _value_or_default(value, default="No data") -> str:
        return default if pd.isna(value) or str(value).strip() == "" else str(value)

    @staticmethod
    def _source_row_id(source: str, index) -> str:
        """Return a stable, human-readable row ID for an uploaded CSV record."""
        return f"{source}:{int(index) + 2}"  # CSV header occupies the first line

    @staticmethod
    def wrap_comment(tag, date, comment):
        """Wrap one source record in the citation framing consumed by the review stage."""
        return f"<{tag} on {date}>\n{comment}\n</{tag} on {date}>"

    @staticmethod
    def to_excel(df, path):
        logger.debug("Writing %d rows to %s", len(df), path)
        df.to_excel(path, index=False)

    def _filter_certification(self, desks):
        exact_match = self.cert_df[["perimeter_name", "trading_desk"]].isin(desks).any(axis=1)
        comment_match = self.cert_df["comment"].astype("string").str.contains(
            self._desk_pattern(desks), na=False, regex=True,
        )
        return self.cert_df.loc[exact_match | comment_match].copy()

    def _filter_income_attribution(self, desks):
        return self.ia_alert_df.loc[
            self.ia_alert_df["perimeter_name"].isin(desks)
        ].copy()

    def _filter_pnl(self, desks):
        pnl = self.pnl_comment_df.dropna(subset=["Comments"]).copy()
        pattern = self._desk_pattern(desks)
        match = (
            pnl["Comments"].astype("string").str.contains(pattern, na=False, regex=True)
            | pnl["Trading Desk"].astype("string").str.contains(pattern, na=False, regex=True)
        )
        return pnl.loc[match].copy()

    def _write_source_extracts(self, cert, ia, pnl):
        """Preserve the existing source-extract workbooks outside the LLM pipeline."""
        self.to_excel(
            cert[cert["indicator_name"].isin(["VAR", "SVAR"])],
            os.path.join(self.output_dir, "Var_SVaR_Comments.xlsx"),
        )
        self.to_excel(
            cert[cert["indicator_name"] == "STRESS TEST"],
            os.path.join(self.output_dir, "Stress_Test_Comments.xlsx"),
        )
        self.to_excel(
            cert[~cert["indicator_name"].isin(["VAR", "SVAR", "STRESS TEST"])],
            os.path.join(self.output_dir, "Risk_Metrics_Comment.xlsx"),
        )
        self.to_excel(ia, os.path.join(self.output_dir, "Income_Attribution_Comment.xlsx"))
        self.to_excel(pnl, os.path.join(self.output_dir, "PnL_Comment.xlsx"))

    def _normalise_source(self, df, *, source, tag, date_column, desk_column,
                          perimeter_column, review_type, metric_name, detail_fields):
        """Map one source DataFrame to the shared internal evidence shape."""
        rows = pd.DataFrame(index=df.index)
        rows["as_of_date"] = pd.to_datetime(df[date_column]).dt.strftime("%Y-%m-%d")
        rows["desk"] = df[desk_column].map(
            lambda value: self._value_or_default(value, default="Unknown")
        )
        rows["perimeter_name"] = df[perimeter_column].map(
            lambda value: self._value_or_default(value, default="Unknown")
        )
        rows["source"] = source
        rows["source_row_id"] = [self._source_row_id(source, index) for index in df.index]
        rows["review_type"] = review_type
        rows["metric_name"] = metric_name.map(
            lambda value: self._value_or_default(value, default="Unknown")
        )
        rows["details"] = df.apply(
            lambda row: "\n".join(
                f"{label}: {self._value_or_default(row[column])}"
                for column, label in detail_fields
            ),
            axis=1,
        )
        rows["tag"] = tag
        return rows

    def _normalise_certification(self, cert):
        review_type = cert["indicator_name"].map(_CERTIFICATION_REVIEW_TYPES).fillna(
            "Risk Metrics Comment"
        )
        return self._normalise_source(
            cert,
            source="certification",
            tag="Certification Alert Comment",
            date_column="as_of_date",
            desk_column="trading_desk",
            perimeter_column="perimeter_name",
            review_type=review_type,
            metric_name=cert["indicator_name"],
            detail_fields=(
                ("error_message", "Error Message"),
                ("comment", "Comment"),
                ("managerial_validation_comment", "Managerial Validation Comment"),
                ("related_scenario", "Related Scenario"),
            ),
        )

    def _normalise_income_attribution(self, ia):
        return self._normalise_source(
            ia,
            source="income_attribution",
            tag="Income Attribution Alert Comment",
            date_column="as_of_date",
            desk_column="perimeter_name",
            perimeter_column="perimeter_name",
            review_type=pd.Series("IA Comment", index=ia.index),
            metric_name=pd.Series("Income Attribution", index=ia.index),
            detail_fields=(
                ("mmg_bl_comment", "MMG BL Comment"),
                ("mmg_xbc_comment", "MMG XBC Comment"),
                ("managerial_validation_comment", "Managerial Validation Comment"),
            ),
        )

    def _normalise_pnl(self, pnl):
        pnl = pnl.assign(_perimeter_name="Not provided")
        return self._normalise_source(
            pnl,
            source="pnl",
            tag="PnL Comment",
            date_column="Date",
            desk_column="Trading Desk",
            perimeter_column="_perimeter_name",
            review_type=pd.Series("PnL Comment", index=pnl.index),
            metric_name=pd.Series("PnL", index=pnl.index),
            detail_fields=(("Comments", "Comment"),),
        )

    def _render_evidence(self, source_rows):
        """Add citation framing to normalised source rows and expose the public contract."""
        if source_rows.empty:
            return pd.DataFrame(columns=EVIDENCE_COLUMNS)

        def render(row):
            metadata = [
                f"Evidence ID: {row['source_row_id']}",
                f"Source: {row['source']}",
                f"Desk: {row['desk']}",
                f"Perimeter: {row['perimeter_name']}",
                f"Metric: {row['metric_name']}",
            ]
            return self.wrap_comment(row["tag"], row["as_of_date"], "\n".join(
                metadata + [row["details"]]
            ))

        evidence = source_rows.copy()
        evidence["evidence_text"] = evidence.apply(render, axis=1)
        return evidence[EVIDENCE_COLUMNS].sort_values(
            ["as_of_date", "review_type", "source", "source_row_id"], kind="stable"
        ).reset_index(drop=True)

    def build_evidence(self, desks):
        """Return one prompt-ready evidence row for every in-scope source record.

        VAR and SVAR share ``VAR_SVAR Comment`` and are therefore reviewed in
        one task, while their individual metric names remain in the evidence.
        """
        desks = self._normalise_desks(desks)
        logger.info("Building canonical review evidence for desks=%s", desks)

        cert = self._filter_certification(desks)
        ia = self._filter_income_attribution(desks)
        pnl = self._filter_pnl(desks)
        self._write_source_extracts(cert, ia, pnl)

        source_rows = pd.concat([
            self._normalise_certification(cert),
            self._normalise_income_attribution(ia),
            self._normalise_pnl(pnl),
        ])
        evidence = self._render_evidence(source_rows)
        if evidence.empty:
            logger.warning("No in-scope evidence rows found for desks=%s", desks)
        else:
            logger.info(
                "Built canonical review evidence | %d row(s) | %d unique source record(s)",
                len(evidence), evidence["source_row_id"].nunique(),
            )
        return evidence
