#!/usr/bin/env python2
from boto.s3.connection import S3Connection
import boto
from datetime import datetime
from datetime import timedelta
import ConfigParser
import os
import sys

# Load the configuration
Config = ConfigParser.SafeConfigParser()
try:
	Config.readfp(open("config.ini"))
except IOError as e:
	print "Error opening config.ini for reading. I/O error({0}): {1}".format(e.errno, e.strerror)
	sys.exit(1)
except ConfigParser.Error as e:
	print "Error while parsing your config.ini", e
	sys.exit(1)

# Establish the "minimum date" (1 week ago) that all buckets need to be newer than
try:
	min_age = Config.getint('Buckets', 'age')
	minimum_date = datetime.today()-timedelta(days=min_age)
	print "Must be newer than:", minimum_date
except ConfigParser.Error as e:
	print "No minimum/threshold age defined:", e
	sys.exit(1)

# Advanced use - include any [Boto] configs as configuration for boto
if Config.has_section('Boto'):
	print "Merging [Boto] from our configuration into boto's"
	boto.config.add_section('Boto')
	for k, v in Config.items('Boto'):
		print "[Boto] Merging in "+k+"="+v
		boto.config.set('Boto', k, v)

# Connecting to AWS
try:
	conn = S3Connection( 
		Config.get('AWS', 'AWS_ACCESS_KEY_ID'), \
		Config.get('AWS', 'AWS_SECRET_ACCESS_KEY') \
		)
	print "Connected using AWS keys stored in config.ini"
except ConfigParser.Error as e:
	# Probably couldn't find the variables in Config, try using our helper method instead
	conn = boto.connect_s3()
	print "Connected using environment AWS keys"


buckets = conn.get_all_buckets()

print "Inspecting", len(buckets), "buckets."


for bucket in buckets:
	print "Checking bucket:", bucket.name
	
	# Initialize
	last_mod = 0
	
	"""
	Examine each file:
	If the file is new enough, we're done (break)
	If the file is not new enough, make a note (last_mod) so we can check post-loop, and move on
	"""
	for k in bucket.list():
		#print bucket.name, "::", k.name, "::", k.last_modified
		# Initialize if needed
		if not last_mod:
			last_mod = k
		# Parse S3's response in ISO8601 into datetime
		lm = datetime.strptime(k.last_modified, "%Y-%m-%dT%H:%M:%S.%fZ")
		# Is this file's last_modified date newer than the newest we've seen yet?
		if k.last_modified > last_mod.last_modified:
			# Update last_mod
			last_mod = k
			#print "Updated last_mod:", k.name, k.last_modified
		# Check whether last_modified is within our window, and break if we're godo
		if lm > minimum_date:
			#print "File is definitely new enough"
			break
	# We reach here if we broke with a certain-to-be-good date, or we ran out of files, so we double check
	# Note "Last modified" file may just be the first file we find within the window. We aren't thorough, just quick.
	#print "Last modified file was " + last_mod.name + " on", last_mod.last_modified
	# Again, parse S3 ISO8601 into datetime
	lm = datetime.strptime(last_mod.last_modified, "%Y-%m-%dT%H:%M:%S.%fZ")
	# Perform the comparison
	if lm < minimum_date:
		print "!!! Error, " + bucket.name + " has no keys modified since", minimum_date

