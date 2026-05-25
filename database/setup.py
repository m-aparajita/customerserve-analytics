import os
from pathlib import Path
from database.connection import get_connection

DATA_DIR = Path(os.getenv("DATA_DIR", Path(__file__).parent.parent / "Data"))

TABLES = {
    "orders": DATA_DIR / "orders.csv",
    "order_items": DATA_DIR / "order_items.csv",
    "products": DATA_DIR / "products.csv",
}

CSV_FILES = ["orders.csv", "order_items.csv", "products.csv"]


def _download_from_hf_dataset() -> None:
    """Download CSV files from a HuggingFace Dataset if HF_DATASET_REPO is set."""
    repo = os.getenv("HF_DATASET_REPO", "").strip()
    print(f"  HF_DATASET_REPO = '{repo}'")
    if not repo:
        print("  HF_DATASET_REPO not set — skipping download.")
        return

    from huggingface_hub import hf_hub_download

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    for filename in CSV_FILES:
        target = DATA_DIR / filename
        if not target.exists():
            print(f"  Downloading {filename} from HuggingFace Dataset ...")
            hf_hub_download(
                repo_id=repo,
                repo_type="dataset",
                filename=filename,
                local_dir=str(DATA_DIR),
            )
            print(f"  {filename} downloaded.")


def setup_database(force_reload: bool = False) -> None:
    _download_from_hf_dataset()

    conn, lock = get_connection()
    with lock:
        existing = {row[0] for row in conn.execute("SHOW TABLES").fetchall()}

        for table, csv_path in TABLES.items():
            if not csv_path.exists():
                raise FileNotFoundError(
                    f"Data file not found: {csv_path}\n"
                    f"Set the HF_DATASET_REPO environment variable to auto-download."
                )
            if table not in existing or force_reload:
                print(f"  Loading {table} from {csv_path.name} ...")
                conn.execute(f"""
                    CREATE OR REPLACE TABLE {table} AS
                    SELECT * FROM read_csv_auto('{csv_path.as_posix()}', header=true)
                """)
                count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                print(f"  {table}: {count:,} rows loaded")

        conn.execute("""
            CREATE TABLE IF NOT EXISTS query_logs (
                log_id        VARCHAR PRIMARY KEY,
                ts            TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                username      VARCHAR,
                role          VARCHAR,
                user_query    TEXT,
                generated_sql TEXT,
                exec_ms       INTEGER,
                rows_returned INTEGER,
                chart_type    VARCHAR,
                status        VARCHAR,
                guardrail_layer  VARCHAR,
                guardrail_reason TEXT,
                error_message    TEXT
            )
        """)

    print("Database ready.")


if __name__ == "__main__":
    setup_database()
