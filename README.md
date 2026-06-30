# Comment Review Tool

Streamlit tool that turns trading-desk risk-comment CSVs into per-quarter AI reviews and executive summaries (downloadable as Word docs).

## Setup

    uv sync
    cp .env.example .env   # fill in Azure OpenAI values

## Run

    uv run streamlit run frontend/app.py

## Sample data

    uv run python -m scripts.generate_sample_data --out sample_data

## Tests

    uv run pytest
