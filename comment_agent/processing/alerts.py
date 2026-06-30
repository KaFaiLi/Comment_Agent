import os
import re
import pandas as pd

from comment_agent.processing.columns import (
    VAR_SVAR_COL, STRESS_TEST_COL, RISK_METRICS_COL, IA_COL, PNL_COL,
)


class AlertProcessor:
    """Processes various alert and comment data for one or more trading desks."""

    def __init__(self, cert_path, ia_path, pnl_path, output_dir="Outputs"):
        self.cert_df = pd.read_csv(cert_path)
        self.ia_alert_df = pd.read_csv(ia_path)
        self.pnl_comment_df = pd.read_csv(pnl_path)
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)
        self._require_columns(self.cert_df, ["perimeter_name", "trading_desk",
            "indicator_name", "comment", "as_of_date"], "certification alert")
        self._require_columns(self.ia_alert_df, ["perimeter_name", "as_of_date"],
            "income attribution alert")
        self._require_columns(self.pnl_comment_df, ["Trading Desk", "Comments", "Date"],
            "PnL comment")

    @staticmethod
    def _require_columns(df, cols, name):
        missing = [c for c in cols if c not in df.columns]
        if missing:
            raise ValueError(f"{name} CSV missing columns: {missing}")

    @staticmethod
    def to_excel(df, path):
        df.to_excel(path, index=False)

    @staticmethod
    def wrap_comment(tag, date, comment):
        """Wraps a comment with tags indicating its source and date."""
        return f"<{tag} on {date}>\n{comment}\n</{tag} on {date}>"

    def _filter_by_desks(self, df, desks, columns_to_search, comment_col=None):
        """
        Reusable filter operation:
         - Converts the input to a list if necessary.
         - Filters the specified columns for an exact match.
         - If `comment_col` is provided, applies a regex filter over that column.
        """
        if isinstance(desks, str):
            desks = [desks]
        mask = pd.Series(False, index=df.index)
        for col in columns_to_search:
            mask |= df[col].isin(desks)
        if comment_col:
            # Build regex with word boundaries to avoid partial matches when possible
            pattern = r"(" + "|".join(map(re.escape, desks)) + r")"
            mask |= df[comment_col].str.contains(pattern, na=False, regex=True)
        return df[mask]

    def _prepare_as_of_date(self, df, date_col="as_of_date"):
        """Converts the given date column to ISO string representation."""
        df[date_col] = pd.to_datetime(df[date_col]).dt.date.astype(str)
        return df

    def _concatenate_fields(self, df, fields, headers, default="No data"):
        """
        Concatenates columns from a DataFrame row.
        `fields` is a list of column names, and `headers` is a list with corresponding header labels.
        """
        result = ""
        for field, header in zip(fields, headers):
            value = df[field] if pd.notna(df[field]) else default
            result += f"{header}: {value}\n"
        return result.strip()

    def _group_comments_by_date(self, df, date_col, comment_field, aggfunc):
        """
        Groups comments by a date column using the provided aggregation function.
        """
        return df.groupby(date_col)[comment_field].apply(aggfunc).reset_index()

    def process_var_svar(self, desks):
        # Filter for desks and the indicators needed
        cert = self._filter_by_desks(
            self.cert_df,
            desks,
            ["perimeter_name", "trading_desk"],
            comment_col="comment",
        )
        cert = cert[cert["indicator_name"].isin(["VAR", "SVAR"])]
        self.to_excel(cert, os.path.join(self.output_dir, "Var_SVaR_Comments.xlsx"))

        # Create concatenated comment using the helper for a standardized format
        cert["Comment_concated"] = cert.apply(
            lambda row: self._concatenate_fields(
                row,
                fields=[
                    "indicator_name",
                    "error_message",
                    "comment",
                    "managerial_validation_comment",
                    "related_scenario",
                ],
                headers=[
                    "Indicator Type",
                    "Error Message",
                    "Comment",
                    "Managerial Validation Comment",
                    "Related Scenario",
                ],
            ),
            axis=1,
        )
        cert = self._prepare_as_of_date(cert)
        grouped = self._group_comments_by_date(
            cert, "as_of_date", "Comment_concated", lambda x: " ".join(x)
        )
        grouped[VAR_SVAR_COL] = grouped.apply(
            lambda row: self.wrap_comment(
                "Risk Metrics Alert Comment", row["as_of_date"], row["Comment_concated"]
            ),
            axis=1,
        )
        return grouped[["as_of_date", VAR_SVAR_COL]].drop_duplicates()

    def process_stress_test(self, desks):
        # Filter for stress test indicator
        stress = self._filter_by_desks(
            self.cert_df,
            desks,
            ["perimeter_name", "trading_desk"],
            comment_col="comment",
        )
        stress = stress[stress["indicator_name"] == "STRESS TEST"]
        self.to_excel(
            stress, os.path.join(self.output_dir, "Stress_Test_Comments.xlsx")
        )

        stress["Comment_concated"] = stress.apply(
            lambda row: self._concatenate_fields(
                row,
                fields=[
                    "error_message",
                    "comment",
                    "managerial_validation_comment",
                    "related_scenario",
                ],
                headers=[
                    "Error Message",
                    "Comment",
                    "Managerial Validation Comment",
                    "Related Scenario",
                ],
            ),
            axis=1,
        )
        stress = self._prepare_as_of_date(stress)
        grouped = (
            stress.groupby(["as_of_date", "indicator_name"])["Comment_concated"]
            .apply(list)
            .reset_index()
        )
        grouped[STRESS_TEST_COL] = [
            [
                self.wrap_comment(
                    f"{row['indicator_name']} Alert Comment", row["as_of_date"], c
                )
                for c in comments
            ]
            for comments, (_, row) in zip(
                grouped["Comment_concated"], grouped.iterrows()
            )
        ]
        # Flatten comments per date
        result = (
            grouped.groupby("as_of_date")[STRESS_TEST_COL]
            .sum()
            .reset_index()
        )
        return result

    def process_risk_comments(self, desks):
        # Filter out risk metrics that are not VAR, SVAR, or STRESS TEST
        risk = self._filter_by_desks(
            self.cert_df,
            desks,
            ["perimeter_name", "trading_desk"],
            comment_col="comment",
        )
        risk = risk[~risk["indicator_name"].isin(["VAR", "SVAR", "STRESS TEST"])]
        self.to_excel(risk, os.path.join(self.output_dir, "Risk_Metrics_Comment.xlsx"))

        risk["Comment_concated"] = risk.apply(
            lambda row: self._concatenate_fields(
                row,
                fields=[
                    "indicator_name",
                    "error_message",
                    "comment",
                    "managerial_validation_comment",
                    "related_scenario",
                ],
                headers=[
                    "Risk Type",
                    "Error Message",
                    "Comment",
                    "Managerial Validation Comment",
                    "Related Scenario",
                ],
            ),
            axis=1,
        )
        risk = self._prepare_as_of_date(risk)
        grouped = self._group_comments_by_date(
            risk, "as_of_date", "Comment_concated", lambda x: " ".join(x)
        )
        grouped[RISK_METRICS_COL] = grouped.apply(
            lambda row: self.wrap_comment(
                "Risk Metrics Alert Comment", row["as_of_date"], row["Comment_concated"]
            ),
            axis=1,
        )
        return grouped[["as_of_date", RISK_METRICS_COL]].drop_duplicates()

    def process_ia_alerts(self, desks):
        # Filter using only perimeter_name column
        if isinstance(desks, str):
            desks = [desks]
        ia = self.ia_alert_df[self.ia_alert_df["perimeter_name"].isin(desks)]
        self.to_excel(
            ia, os.path.join(self.output_dir, "Income_Attribution_Comment.xlsx")
        )

        ia["Comment_concated"] = ia.apply(
            lambda row: self._concatenate_fields(
                row,
                fields=[
                    "mmg_bl_comment",
                    "mmg_xbc_comment",
                    "managerial_validation_comment",
                ],
                headers=[
                    "mmg bl comment",
                    "mmg xbc comment",
                    "Managerial Validation Comment",
                ],
            ),
            axis=1,
        )
        ia = self._prepare_as_of_date(ia)
        grouped = ia.groupby("as_of_date")["Comment_concated"].apply(list).reset_index()
        grouped[IA_COL] = [
            [
                self.wrap_comment(
                    "Income Attribution Alert Comment", row["as_of_date"], c
                )
                for c in comments
            ]
            for comments, (_, row) in zip(
                grouped["Comment_concated"], grouped.iterrows()
            )
        ]
        return grouped[["as_of_date", IA_COL]]

    def process_pnl_comments(self, desks):
        df = self.pnl_comment_df.dropna(subset=["Comments"])
        df["Comments"] = df["Comments"].astype(str)
        df["Trading Desk"] = df["Trading Desk"].astype(str)
        # Use filtering with regex for PnL comments
        if isinstance(desks, str):
            desks = [desks]
        pattern = r"(" + "|".join(map(re.escape, desks)) + r")"
        filtered = df[
            df["Comments"].str.contains(pattern, na=False)
            | df["Trading Desk"].str.contains(pattern, na=False)
        ]
        self.to_excel(filtered, os.path.join(self.output_dir, "PnL_Comment.xlsx"))
        filtered = self._prepare_as_of_date(filtered, date_col="Date")
        filtered[PNL_COL] = filtered.apply(
            lambda row: self.wrap_comment("PnL comments", row["Date"], row["Comments"]),
            axis=1,
        )
        return filtered[["Date", PNL_COL]].rename(
            columns={"Date": "as_of_date"}
        )

    def merge_comments(self, desks):
        var_svar = self.process_var_svar(desks)
        stress_test = self.process_stress_test(desks)
        risk = self.process_risk_comments(desks)
        ia = self.process_ia_alerts(desks)
        pnl = self.process_pnl_comments(desks)

        # Merge all on as_of_date with outer joins
        merged = ia.merge(var_svar, on="as_of_date", how="outer")
        merged = merged.merge(stress_test, on="as_of_date", how="outer")
        merged = merged.merge(pnl, on="as_of_date", how="outer")
        merged = merged.merge(risk, on="as_of_date", how="outer")
        return merged

    @staticmethod
    def create_final_comment(merged_df):
        def is_valid_comment(value):
            return (
                pd.notna(value)
                and str(value).strip()
                and str(value).strip().lower() != "nan"
            )

        def build_comment(
            cert_comment, stress_test_comment, ia_comment, pnl_comment, risk_comment
        ):
            comments = []

            if is_valid_comment(cert_comment):
                comments.append("VAR_SVAR Alert and Comment:\n" + str(cert_comment))

            if is_valid_comment(stress_test_comment):
                comments.append(
                    "Stress Test Alert and Comment:\n" + str(stress_test_comment)
                )

            if is_valid_comment(ia_comment):
                comments.append(
                    "Income Attribution Alert and Comment:\n" + str(ia_comment)
                )

            if is_valid_comment(pnl_comment):
                comments.append("PnL Comment:\n" + str(pnl_comment))

            if is_valid_comment(risk_comment):
                comments.append("Risk Metrics Comment:\n" + str(risk_comment))

            return "\n\n".join(comments) if comments else pd.NA

        comment_columns = [
            "VAR_SVAR Comment for LLM",
            "Stress Test Comment for LLM",
            "Income Attribution Alert Comment for LLM",
            "PnL Comment for LLM",
            "Risk Metrics Comment for LLM",
        ]

        for col in comment_columns:
            if col in merged_df.columns:
                merged_df = merged_df.explode(col)

        merged_df["All Comment for LLM"] = merged_df.apply(
            lambda row: build_comment(
                row.get("VAR_SVAR Comment for LLM"),
                row.get("Stress Test Comment for LLM"),
                row.get("Income Attribution Alert Comment for LLM"),
                row.get("PnL Comment for LLM"),
                row.get("Risk Metrics Comment for LLM"),
            ),
            axis=1,
        )

        return merged_df
