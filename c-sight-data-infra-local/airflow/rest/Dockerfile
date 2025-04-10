# Use the iceberg-rest base image
FROM tabulario/iceberg-rest:1.6.0

# Switch to the root user to install packages
USER root

# Update package lists and install curl & PostgreSQL client
RUN apt-get update && apt-get install -y curl postgresql-client

# Ensure the necessary directory exists and is writable
RUN mkdir -p /opt/iceberg-rest/lib && chown -R iceberg:iceberg /opt/iceberg-rest/lib

# Download the PostgreSQL JDBC driver
RUN curl -o /opt/iceberg-rest/lib/postgresql-42.2.23.jar https://jdbc.postgresql.org/download/postgresql-42.2.23.jar

# Verify PostgreSQL client installation
RUN psql --version

# Switch back to the iceberg user
USER iceberg