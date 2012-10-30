Backup Bucket Check
===================

I needed a quick way to check that all of my S3 buckets had been touched recently,
checking to see that cron'd duplicity backups were running as expected. Also needed
was an excuse to dig into writing Python. And thus bucketcheck.py was born.


TODO
====
 * Add a configuration file
 * Include/exclude backets
 * Notifications (Email, Pushover)
 * Some more documentation
