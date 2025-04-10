FROM apache/airflow:slim-latest-python3.9

# Switch to root user for installing system dependencies
USER root

# Install required system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    python3-dev \
    libffi-dev \
    libssl-dev \
    libxml2-dev \
    libxslt1-dev \
    libxmlsec1-dev \
    libxmlsec1-openssl \
    xmlsec1 \
    pkg-config \
    libtool \
    && rm -rf /var/lib/apt/lists/*

# Switch to the airflow user for installing Python packages
USER airflow

# Upgrade pip
RUN pip install --upgrade pip

# Install additional Airflow providers and Python packages
RUN pip install --no-cache-dir \
    apache-airflow-providers-amazon==9.4.0 \
    apache-airflow-providers-apache-spark==5.0.0 \
    apache-airflow-providers-trino==6.0.1 \
    apache-airflow-providers-sqlite==4.0.0 \
    requests==2.32.3 \
    boto3==1.37.4 \
    pandas==2.1.2 \
    psycopg2-binary \
    apache-airflow-providers-celery\
    pyarrow==11.0.0\
    azure-servicebus
USER root

# Ensure Airflow directories exist and have correct permissions
RUN mkdir -p /opt/airflow/dags /opt/airflow/plugins /opt/airflow/logs \
    && chown -R 50000:50000 /opt/airflow

# Switch back to the airflow user
USER airflow

# Copy entrypoint script and make it executable