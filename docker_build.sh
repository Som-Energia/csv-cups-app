#!/bin/bash

docker compose build
docker tag csv-cups-app-app:latest harbor.somenergia.coop/erp/csv-cups-app:latest
docker push harbor.somenergia.coop/erp/csv-cups-app:latest
