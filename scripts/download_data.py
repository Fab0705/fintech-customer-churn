
from pathlib import Path
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"
DATASET = "sakshigoyal7/credit-card-customers"

def main():
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    subprocess.run(
        [
            "kaggle", "datasets", "download",
            "-d", DATASET,
            "-p", str(RAW_DIR),
        ],
        check=True,
    )

    zip_files = list(RAW_DIR.glob("*.zip"))
    if not zip_files:
        raise FileNotFoundError(
            "Kaggle did not produce a ZIP file."
        )

    for zip_path in zip_files:
        with zipfile.ZipFile(zip_path) as archive:
            archive.extractall(RAW_DIR)

    csv_files = list(RAW_DIR.glob("*.csv"))
    if not csv_files:
        raise FileNotFoundError(
            "No CSV file was found after extraction."
        )

    print(f"Dataset ready: {csv_files[0]}")

if __name__ == "__main__":
    main()
