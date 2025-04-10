from airflow import DAG
from airflow.operators.dummy import DummyOperator
from airflow.operators.python import PythonOperator
import logging
import boto3
import pandas as pd
import pyarrow.parquet as pq
import trino
from datetime import datetime
from io import BytesIO


# MinIO Configuration
MINIO_ENDPOINT = "storage-api.dev.hitachi-ai.io"
MINIO_ACCESS_KEY = "csight-b"
MINIO_SECRET_KEY = "YB6RuT2c0omB+yvADmaU4AQ9830="
MINIO_BUCKET = "csight"
MINIO_FILE_PATH = "billingdata/cloud/azure/0f8c3763-9eeb-40f9-9037-2a5426da75e9/2025/02/part_0_0001.snappy.parquet"  # Path in MinIO bucket

# Trino Configuration
TRINO_HOST = "http://csight-trinodb-dev.dev.hitachi-ai.io"
TRINO_PORT = 80
TRINO_USER = "iceberg"
TRINO_CATALOG = "iceberg"
TRINO_SCHEMA = "bronze"
TRINO_TABLE = "billing_data_bronze"

# SQL Statements for Truncating Table
TRUNCATE_TABLE_SQL = f"TRUNCATE TABLE {TRINO_CATALOG}.{TRINO_SCHEMA}.{TRINO_TABLE}"

# ----------------------------
# Fetch Column Names from Trino
# ----------------------------
def get_trino_columns():
    """
    Fetches column names from the Trino table.
    """
    try:
        conn = trino.dbapi.connect(
            host=TRINO_HOST,
            port=TRINO_PORT,
            user=TRINO_USER,
            catalog=TRINO_CATALOG,
            schema=TRINO_SCHEMA
        )
        cur = conn.cursor()
        cur.execute(f"DESCRIBE {TRINO_CATALOG}.{TRINO_SCHEMA}.{TRINO_TABLE}")
        trino_columns = [row[0] for row in cur.fetchall()]  # Extract column names
        cur.close()
        conn.close()
        logging.info(f"🛢️ Trino Table Columns: {trino_columns}")
        return trino_columns
    except Exception as e:
        logging.error(f"❌ Error fetching Trino table columns: {e}")
        return []

# ----------------------------
# Fetch Parquet from MinIO
# ----------------------------
def fetch_and_insert_data():
    """
    Fetches data from MinIO, aligns with Trino schema, and inserts 50 rows into Trino.
    """
    print("📡 Fetching data from MinIO and inserting into Trino...")

    # Fetch column names from Trino
    trino_columns = get_trino_columns()
    if not trino_columns:
        print("❌ No columns found for Trino table.")
        return

    # Connect to MinIO and fetch the Parquet file
    s3_client = boto3.client(
        "s3",
        endpoint_url=MINIO_ENDPOINT,
        aws_access_key_id=MINIO_ACCESS_KEY,
        aws_secret_access_key=MINIO_SECRET_KEY
    )
    
    try:
        print(f"📂 Fetching Parquet file: {MINIO_FILE_PATH} from bucket: {MINIO_BUCKET}")
        obj = s3_client.get_object(Bucket=MINIO_BUCKET, Key=MINIO_FILE_PATH)
        raw_data = obj["Body"].read()
        
        df = pq.read_table(BytesIO(raw_data)).to_pandas()
        print(f"✅ Data loaded from MinIO! Shape: {df.shape}")
        
        # Limit the data to the first 50 rows
        df = df.head(50)
        
        # Align the DataFrame with Trino table schema
        df = align_dataframe(df, trino_columns)
        
        # Insert data into Trino
        load_data_into_trino(df)
        
    except Exception as e:
        logging.error(f"❌ Error fetching or processing data from MinIO: {e}")
        print(f"❌ Error fetching or processing data: {e}")

# ----------------------------
# Align DataFrame with Trino Table
# ----------------------------
def align_dataframe(df, trino_columns):
    """
    Aligns DataFrame columns with Trino table:
    - Drops extra columns that are not in Trino.
    - Adds missing columns and fills them with NULL values.
    """
    df.columns = [col.lower() for col in df.columns]
    trino_columns = [col.lower() for col in trino_columns]  # Convert Trino column names to lowercase

    # Drop extra columns
    df = df[[col for col in df.columns if col in trino_columns]]

    # Add missing columns with NULL values
    for col in trino_columns:
        if col not in df.columns:
            df[col] = None  # Fill missing columns with NULL

    # Reorder DataFrame columns to match Trino order
    df = df[trino_columns]
    print(f"🔄 DataFrame aligned with Trino table: {df.shape}")
    return df

# ----------------------------
# Insert Data into Trino
# ----------------------------
def load_data_into_trino(df):
    """
    Inserts data into Trino Iceberg table in batches.
    """
    print(f"🚀 Inserting data into Trino table: {TRINO_SCHEMA}.{TRINO_TABLE}")

    if df.empty:
        print("⚠️ No records to insert!")
        return

    # Convert DataFrame to List of Tuples for batch insert
    records = df.where(pd.notna(df), None).values.tolist()

    # Generate INSERT query
    full_table_name = f"{TRINO_CATALOG}.{TRINO_SCHEMA}.{TRINO_TABLE}"
    columns = ", ".join(df.columns)
    
    try:
        conn = trino.dbapi.connect(
            host=TRINO_HOST,
            port=TRINO_PORT,
            user=TRINO_USER,
            catalog=TRINO_CATALOG,
            schema=TRINO_SCHEMA
        )
        cur = conn.cursor()

        # Insert the data (only 50 rows at a time)
        batch_records = records[:50]  # Limit to 50 rows
        values = ", ".join(
            "({})".format(", ".join("'{}'".format(str(value).replace("'", "''")) if value is not None else "NULL" for value in row))
            for row in batch_records
        )

        insert_query = f"INSERT INTO {full_table_name} ({columns}) VALUES {values}"
        cur.execute(insert_query)  # Execute the query for the batch

        conn.commit()
        print("✅ Data inserted successfully into Trino Iceberg table!")

    except Exception as e:
        logging.error(f"❌ Error inserting data into Trino: {e}")
        print(f"❌ Error inserting data: {e}")

    finally:
        cur.close()
        conn.close()
        
def execute_sql_query(query):
    """
    Executes a given SQL query in Trino.
    """
    try:
        conn = trino.dbapi.connect(
            host=TRINO_HOST,
            port=TRINO_PORT,
            user=TRINO_USER,
            catalog=TRINO_CATALOG,
            schema=TRINO_SCHEMA
        )
        cur = conn.cursor()
        cur.execute(query)
        conn.commit()
        cur.close()
        conn.close()
        logging.info(f"✅ Successfully executed query: {query}")
    except Exception as e:
        logging.error(f"❌ Error executing query: {query}, Error: {e}")
        raise

# Define Airflow DAG
dag = DAG(
    "minio_parquet_to_iceberg_dag",
    schedule_interval="@daily",
    start_date=datetime(2024, 1, 1),
    catchup=False,
)

# Start Task
start_task = DummyOperator(task_id="start", dag=dag)

# Truncate Task
truncate_table_task = PythonOperator(
    task_id="truncate_table",
    python_callable=lambda: execute_sql_query(TRUNCATE_TABLE_SQL),
    dag=dag,
)

# Fetch and Insert Task
fetch_and_insert_task = PythonOperator(
    task_id="fetch_and_insert_data",
    python_callable=fetch_and_insert_data,
    dag=dag,
)

# End Task
end_task = DummyOperator(task_id="end", dag=dag)

# DAG Execution Flow
start_task >> truncate_table_task >> fetch_and_insert_task >> end_task
