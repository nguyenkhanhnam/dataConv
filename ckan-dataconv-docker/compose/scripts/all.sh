#!/bin/bash
exec "/srv/app/start_ckan.sh" & exec "/airflow-entrypoint.sh"