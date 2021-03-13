#!/bin/bash
export AIRFLOW_HOME="/srv/app/airflow"

if [ ! -d $AIRFLOW_HOME ]
then
    mkdir $AIRFLOW_HOME
fi

if [ ! -f $AIRFLOW_HOME/"airflow.cfg" ] 
then
    airflow db init
fi

# airflow db reset
airflow db init

# airflow scheduler
airflow scheduler &

# airflow webserver
exec airflow webserver


