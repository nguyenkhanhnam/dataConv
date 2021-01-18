cd compose
docker-compose build
docker-compose up
docker-compose down
docker cp ../setup/production.ini ckan:/srv/app/production.ini
docker cp ../setup/ckanext-mysql2mongodb ckan:/srv/app/src/