Backup Bucket Check
===================

I needed a quick way to check that all of my S3 buckets had been touched recently,
checking to see that cron'd duplicity backups were running as expected. Also needed
was an excuse to dig into writing Python. And thus bucketcheck.py was born.


TODO
====
 X Add a configuration file
 X Include/exclude buckets
 * Notifications (Email, Pushover)
  X Pushover
  * Email
 * Some more documentation
 X Command line options
  X Specify a configuration file
  X Debug/verbosity
 * Code cleanup
  X Move login into main()
  * Refactor into smaller, modular methods
