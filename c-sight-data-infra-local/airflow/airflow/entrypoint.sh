#!/bin/bash
# Ensure the database is upgraded before running any Airflow command
airflow db upgrade

# Start the Airflow webserver, scheduler, or other commands (you can customize this as per your needs)
exec "$@"