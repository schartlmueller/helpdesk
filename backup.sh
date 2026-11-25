#!/bin/sh
# Sichert einmal täglich die Datenbank und die Anhänge nach /backups
# und löscht Sicherungen, die älter als BACKUP_KEEP_DAYS Tage sind.
while true; do
  stamp=$(date +%Y-%m-%d_%H%M)
  if pg_dump -Z 6 -f "/backups/db_${stamp}.sql.gz.tmp"; then
    mv "/backups/db_${stamp}.sql.gz.tmp" "/backups/db_${stamp}.sql.gz"
    tar -czf "/backups/anhaenge_${stamp}.tar.gz" -C /media .
    echo "Sicherung ${stamp} erstellt."
  else
    rm -f "/backups/db_${stamp}.sql.gz.tmp"
    echo "Sicherung ${stamp} fehlgeschlagen." >&2
  fi
  find /backups -type f -mtime "+${BACKUP_KEEP_DAYS:-14}" -delete
  sleep 86400
done
