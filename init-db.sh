#!/bin/bash
# Імпортує setup_db.sql у MySQL контейнер при старті
set -e

# Очікуємо запуск MySQL
until mysql -h db -u root -proot -e "SELECT 1"; do
  echo "Waiting for MySQL..."
  sleep 2
done

mysql -h db -u root -proot mydb < setup_db.sql

echo "Database initialized!"