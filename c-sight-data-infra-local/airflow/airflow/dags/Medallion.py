from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.models.param import Param
import logging
from datetime import datetime, timedelta
import trino


connect_id="trino_test_connection"
BRONZE_SCHEMA = "bronze"
SILVER_SCHEMA = "silver"
GOLD_SCHEMA = "gold"

# Trino Configuration
TRINO_HOST = "http://192.168.112.8"  # Trino HTTP API endpoint
TRINO_PORT = 8080
TRINO_USER = "iceberg"
TRINO_CATALOG = "iceberg"
TRINO_SCHEMA = "bronze"
TRINO_TABLE = "billing_data_billing"

def get_trino_columns(schema, table):
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
        cur.execute(f"DESCRIBE {TRINO_CATALOG}.{schema}.{table}")
        trino_columns = ','.join(row[0] for row in cur.fetchall())  # Extract column names
        cur.close()
        conn.close()
        logging.info(f"🛢️ Trino Table Columns: {trino_columns}")
        return trino_columns
    except Exception as e:
        logging.error(f"❌ Error fetching Trino table columns: {e}")
        return []

# Function to Execute SQL Queries on Trino
def execute_sql_query(query, source_schema=None, source_table=None, target_schema=None, target_table=None):
    """
    Executes a given SQL query in Trino.
    """
    try:
        if source_schema is not None:
            source_column_list = get_trino_columns(source_schema, source_table)
            query = query.replace("$source_column_list$", source_column_list)
        if target_schema is not None:
            target_column_list = get_trino_columns(target_schema, target_table)
            query = query.replace("$target_column_list$", target_column_list)
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
    
#
# DAG
#
with DAG(
    "MedalionFlow",
    schedule_interval="@daily",
    start_date=datetime(2024, 1, 1),
    catchup=False,
    params={
        "request_date": Param(f"{datetime.today().strftime('%Y-%m-%d')}", type="string", format="string")
    },
) as dag:

    trino__check_schemas = PythonOperator(
        task_id = 'trino__check_schemas',
        python_callable=lambda: execute_sql_query(f"CREATE SCHEMA IF NOT EXISTS {SILVER_SCHEMA}") or execute_sql_query(f"CREATE SCHEMA IF NOT EXISTS {GOLD_SCHEMA}"),
        dag = dag
    )

    trino__check_tables = PythonOperator(
        task_id = 'trino__check_tables',
        python_callable=lambda: execute_sql_query(f"CREATE TABLE IF NOT EXISTS {TRINO_CATALOG}.{SILVER_SCHEMA}.{TRINO_TABLE} as SELECT $source_column_list$ FROM {TRINO_CATALOG}.{BRONZE_SCHEMA}.{TRINO_TABLE} WHERE 1=0", BRONZE_SCHEMA, TRINO_TABLE) or execute_sql_query(f"CREATE TABLE IF NOT EXISTS {TRINO_CATALOG}.{GOLD_SCHEMA}.{TRINO_TABLE} as SELECT $source_column_list$ FROM {TRINO_CATALOG}.{BRONZE_SCHEMA}.{TRINO_TABLE} WHERE 1=0", BRONZE_SCHEMA, TRINO_TABLE),
        dag = dag
    )

    trino__bronze_to_silver = PythonOperator(
        task_id="trino__bronze_to_silver",
        op_args=[
            "{{ params.request_date }}",
        ],
        python_callable=lambda request_date: execute_sql_query("""INSERT INTO {0}.{1}.{2} ($target_column_list$)
            SELECT $source_column_list$
            FROM {0}.{3}.{2} WHERE ChargePeriodStart >= '{4}'
            """.format(TRINO_CATALOG, SILVER_SCHEMA, TRINO_TABLE, BRONZE_SCHEMA, request_date)
            , BRONZE_SCHEMA, TRINO_TABLE
            , SILVER_SCHEMA, TRINO_TABLE
            ),
    )

    trino__silver_to_gold = PythonOperator(
        task_id="trino__silver_to_gold",
        op_args=[
            "{{ params.request_date }}",
        ],
        python_callable=lambda request_date: execute_sql_query("""INSERT INTO {0}.{1}.{2} ($target_column_list$)
            SELECT $source_column_list$
            FROM {0}.{3}.{2} WHERE ChargePeriodStart >= '{4}'
            """.format(TRINO_CATALOG, GOLD_SCHEMA, TRINO_TABLE, SILVER_SCHEMA, request_date)
            , SILVER_SCHEMA, TRINO_TABLE
            , GOLD_SCHEMA, TRINO_TABLE
            ),
    )

    # Set task dependencies
    trino__check_schemas >> trino__check_tables >> trino__bronze_to_silver >> trino__silver_to_gold