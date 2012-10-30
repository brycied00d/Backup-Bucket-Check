#!/usr/bin/env python
import boto
from datetime import datetime
from datetime import timedelta

# Establish the "minimum date" (1 week ago) that all buckets need to be newer than
minimum_date = datetime.today()-timedelta(weeks=1)
print "Must be newer than:", minimum_date

#boto.config.add_section('Boto')
#boto.config.set('Boto', 'debug', '2')

conn = boto.connect_s3()
rs = conn.get_all_buckets()

print "Inspecting", len(rs), "buckets."

for b in rs:
	print "Checking bucket:", b.name
	
	# Initialize
	last_mod = 0
	
	"""
	Examine each file:
	If the file is new enough, we're done (break)
	If the file is not new enough, make a note (last_mod) so we can check post-loop, and move on
	"""
	for k in b.list():
		#print b.name, "::", k.name, "::", k.last_modified
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
		print "!!! Error, " + b.name + " has no keys modified since", minimum_date

