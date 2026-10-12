
from pathlib import Path
import re

from pyspark.sql import SparkSession, functions as F
from pyspark.sql.types import (
    IntegerType, LongType, DoubleType
)

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"
OUT_DIR = ROOT / "data" / "curated" / "customer_churn"

def snake_case(name: str) -> str:
    name = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name)
    name = re.sub(r"[^a-zA-Z0-9]+", "_", name)
    return name.strip("_").lower()

def main():
    spark = (
        SparkSession.builder
        .appName("FinTechCustomerChurnETL")
        .getOrCreate()
    )

    csv_files = [
        p for p in RAW_DIR.glob("*.csv")
        if p.name.lower() == "bankchurners.csv"
    ]
    if not csv_files:
        csv_files = list(RAW_DIR.glob("*.csv"))
    if not csv_files:
        raise FileNotFoundError("No input CSV found.")

    df = (
        spark.read
        .option("header", True)
        .option("inferSchema", True)
        .option("nullValue", "")
        .csv(str(csv_files[0]))
    )

    # Remove the two Naive Bayes helper columns.
    helper_cols = [
        c for c in df.columns
        if c.lower().startswith("naive_bayes_classifier")
    ]
    if len(helper_cols) != 2:
        raise ValueError(
            f"Expected 2 Naive Bayes columns, found {len(helper_cols)}"
        )
    df = df.drop(*helper_cols)

    # Normalize column names.
    for old_name in df.columns:
        new_name = snake_case(old_name)
        if old_name != new_name:
            df = df.withColumnRenamed(old_name, new_name)

    # Validate essential fields.
    required = {"clientnum", "attrition_flag"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    # Keep customer ID as a stable identifier.
    df = df.withColumn(
        "clientnum", F.col("clientnum").cast(LongType())
    )

    # Convert known numeric fields explicitly.
    numeric_types = {
        "customer_age": IntegerType(),
        "dependent_count": IntegerType(),
        "months_on_book": IntegerType(),
        "total_relationship_count": IntegerType(),
        "months_inactive_12_mon": IntegerType(),
        "contacts_count_12_mon": IntegerType(),
        "credit_limit": DoubleType(),
        "total_revolving_bal": DoubleType(),
        "avg_open_to_buy": DoubleType(),
        "total_amt_chng_q4_q1": DoubleType(),
        "total_ct_chng_q4_q1": DoubleType(),
        "total_trans_amt": DoubleType(),
        "total_trans_ct": IntegerType(),
        "avg_utilization_ratio": DoubleType(),
    }

    for col_name, data_type in numeric_types.items():
        if col_name in df.columns:
            df = df.withColumn(
                col_name, F.col(col_name).cast(data_type)
            )

    # Standardize the target label.
    df = df.withColumn(
        "attrition_flag",
        F.when(
            F.lower(F.trim(F.col("attrition_flag"))) ==
            "attrited customer", "Attrited Customer"
        ).when(
            F.lower(F.trim(F.col("attrition_flag"))) ==
            "existing customer", "Existing Customer"
        ).otherwise(F.col("attrition_flag"))
    )

    # Preserve unknown categories explicitly.
    categorical_cols = [
        "gender", "education_level", "marital_status",
        "income_category", "card_category"
    ]
    for col_name in categorical_cols:
        if col_name in df.columns:
            df = df.withColumn(
                col_name,
                F.when(
                    F.col(col_name).isNull() |
                    (F.trim(F.col(col_name)) == ""),
                    "Unknown"
                ).otherwise(F.trim(F.col(col_name)))
            )

    # Do not impute missing financial values with zero.
    # Report null counts for quality monitoring.
    null_counts = df.select([
        F.sum(
            F.when(F.col(c).isNull(), 1).otherwise(0)
        ).alias(c)
        for c in df.columns
    ]).first().asDict()

    print("Input rows:", df.count())
    print("Duplicate customer IDs:",
          df.count() - df.select("clientnum").distinct().count())
    print("Null counts:", null_counts)

    # Fail on missing/duplicate identifiers or missing target.
    if df.filter(F.col("clientnum").isNull()).limit(1).count():
        raise ValueError("Null clientnum detected.")
    if df.groupBy("clientnum").count().filter(
        F.col("count") > 1
    ).limit(1).count():
        raise ValueError("Duplicate clientnum detected.")
    if df.filter(F.col("attrition_flag").isNull()).limit(1).count():
        raise ValueError("Null attrition_flag detected.")

    OUT_DIR.parent.mkdir(parents=True, exist_ok=True)

    (
        df.write
        .mode("overwrite")
        .parquet(str(OUT_DIR))
    )

    # Optional CSV export for simpler handoff.
    (
        df.coalesce(1)
        .write
        .mode("overwrite")
        .option("header", True)
        .csv(str(OUT_DIR.parent / "customer_churn_csv"))
    )

    print(f"Parquet exported to: {OUT_DIR}")
    spark.stop()

if __name__ == "__main__":
    main()
