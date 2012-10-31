#!/usr/bin/env python2
#
# Backup Bucket Check
#
# Copyright (c) 2012, Bryce Chidester <bryce@cobryce.com>
#
# Permission to use, copy, modify, and/or distribute this software for any
# purpose with or without fee is hereby granted, provided that the above
# copyright notice and this permission notice appear in all copies.
#
# THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES WITH
# REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF MERCHANTABILITY
# AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR ANY SPECIAL, DIRECT,
# INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES WHATSOEVER RESULTING FROM
# LOSS OF USE, DATA OR PROFITS, WHETHER IN AN ACTION OF CONTRACT, NEGLIGENCE OR
# OTHER TORTIOUS ACTION, ARISING OUT OF OR IN CONNECTION WITH THE USE OR
# PERFORMANCE OF THIS SOFTWARE.

import optparse
from boto.s3.connection import S3Connection
import boto
from datetime import datetime
from datetime import timedelta
import ConfigParser
import os
import sys

#parser = optparse.OptionParser()
#(options, args) = parser.parse_args()

# Load the configuration
Config = ConfigParser.SafeConfigParser()
try:
	Config.readfp(open("config.ini"))
except IOError as e:
	print "Error opening config.ini for reading. I/O error({0}): {1}".format(e.errno, e.strerror)
	sys.exit(1)
except ConfigParser.Error as e:
	print "Error while parsing your config.ini: %s" % e
	sys.exit(1)

# Establish the "minimum date" (1 week ago) that all buckets need to be newer than
try:
	min_age = Config.getint('Buckets', 'age')
	minimum_date = datetime.today()-timedelta(days=min_age)
	print "Must be newer than %s" % minimum_date
except ConfigParser.Error as e:
	print "Error! No minimum/threshold age defined: %s" % e
	sys.exit(1)

# Load urllib/httplib only if the user's configured Pushover notifications
try:
	pushover_appkey = False
	pushover_user = False
	pushover_appkey = Config.get('Notification', 'pushover_appkey')
	pushover_user = Config.get('Notification', 'pushover')
	import httplib, urllib
	print "Pushover support loaded."
except ConfigParser.Error as e:
	# Quietly pass through if Pushover isn't configured
	pass

# Load the smtp stuff only if the user's configured an email address
try:
	email = False
	## Probably need _to, _from, maybe _subject
	email = Config.get('Notification', 'email')
	#import httplib, urllib
	print "Email support loaded."
except ConfigParser.Error as e:
	# Quietly pass through if Pushover isn't configured
	pass


# Advanced use - include any [Boto] configs as configuration for boto
if Config.has_section('Boto'):
	print "Merging [Boto] from our configuration into boto's"
	boto.config.add_section('Boto')
	for k, v in Config.items('Boto'):
		print "[Boto] Merging in %s=%s" % (k, v)
		boto.config.set('Boto', k, v)

# Connecting to AWS
try:
	conn = S3Connection( \
		Config.get('AWS', 'AWS_ACCESS_KEY_ID'), \
		Config.get('AWS', 'AWS_SECRET_ACCESS_KEY') \
		)
	print "Connected using AWS keys stored in config.ini"
except ConfigParser.Error as e:
	# Probably couldn't find the variables in Config, try using our helper method instead
	conn = boto.connect_s3()
	print "Connected using environment AWS keys"

# Read in the ex/include from Config
buckets_exclude = []
try:
	for entry in Config.get('Buckets', 'exclude').split(','):
		buckets_exclude.append(entry.strip())
except Exception as e:
	pass
print "Excluding: %s" % buckets_exclude

buckets_include = []# 'com.cobryce.backups.vps2' ]

# Track the buckets that failed the check
buckets_error = []

def iso8601_to_datetime(iso8601):
	return datetime.strptime(iso8601, "%Y-%m-%dT%H:%M:%S.%fZ")

def check_bucket(bucket):
	"""
	Examine each file (key) in the given bucket.
	Find the youngest (most recently modified) file
		Return early if we find one that's new enough - no need to waste time.
	"""
	num_files = 0	# Informational
	for k in bucket.list():
		num_files += 1	# Informational
		lm = iso8601_to_datetime(k.last_modified)	# Parse S3's response in ISO8601 into datetime
		if lm > minimum_date:	# Is k.last_modified newer (younger) than min_age?
			print "Checked %d files (keys) and found a match." % num_files
			return True
	print "Checked %d files (keys) without a match." % num_files
	return False

def get_youngest_key_in_bucket(bucket):
	"""
	Examine each key in bucket and return the youngest key
	"""
	youngest = 0	# Track the youngest we've found yet
	for k in bucket.list():
		if not youngest:	# Needs to be initialized to a Key() once
			youngest = k
		elif k.last_modified > youngest.last_modified:
			youngest = k
	return youngest

if len(buckets_include):
	print "Checking only the %d buckets defined in include=" % len(buckets_include)
	for bucket_include in buckets_include:
		if bucket_include in buckets_exclude:
			print "Skipping bucket %s due to exclude=" % bucket_include
			continue
		print "Checking bucket %s" % bucket_include
		bucket = conn.get_bucket(bucket_include)
		if not check_bucket(bucket):
			print "Error! Bucket %s failed check, no keys modified since %s." % (bucket_include, minimum_date)
			buckets_error.append(bucket_include)
		else:
			print "Bucket %s passed check." % bucket_include
else:
	buckets = conn.get_all_buckets()
	print "Inspecting %d buckets (pre-exclude)" % len(buckets)
	for bucket in buckets:
		if bucket.name in buckets_exclude:
			print "Skipping bucket %s" % bucket.name
			continue
		print "Checking bucket %s" % bucket.name
		if not check_bucket(bucket):
			print "Error! Bucket %s failed check, no keys modified since %s." % (bucket.name, minimum_date)
			buckets_error.append(bucket.name)
		else:
			print "Bucket %s passed check." % bucket.name

print "Check complete, %d buckets failed." % len(buckets_error), buckets_error

# Build the 
buckets_error_string = ""
for b in buckets_error:
	buckets_error_string += " * %s (%s)\\n" % (b, \
		iso8601_to_datetime(\
			get_youngest_key_in_bucket(\
				conn.get_bucket(b) \
			).last_modified \
			) \
		)
message = Config.get('Notification', 'template').\
			format(since=minimum_date, age=min_age, failedbuckets=buckets_error_string)
message = message.replace('\\n', "\n")
print "Notification message:",message

# Send notifications as appropriate
if len(buckets_error):
	if pushover_user and pushover_appkey:
		try:
			pushover = httplib.HTTPSConnection("api.pushover.net:443")
			pushover.request("POST", "/1/messages.json",
				urllib.urlencode({
					"token": pushover_appkey,
					"user": pushover_user,
					"message": message,
					}),
				{ "Content-type": "application/x-www-form-urlencoded" }
				)
			conn.getresponse()
		except Exception as e:
			print "Exception while pushing notification to Pushover: %s", e
			pass
	
	if email:
		print "I'd send an email, if I knew how to. Sorry chap."

