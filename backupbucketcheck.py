#!/usr/bin/env python2
"""
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
"""

import optparse
from datetime import datetime
from datetime import timedelta
import ConfigParser
import sys


def iso8601_to_datetime(iso8601):
    """ Interpret Amazon's ISO8601 date string into a datetime object.
    """
    return datetime.strptime(iso8601, "%Y-%m-%dT%H:%M:%S.%fZ")


def check_bucket(bucket):
    """ Examine each file (key) in the given bucket.
        Find the youngest (most recently modified) file
        Return early if we find one that's new enough - no need to waste time.
        num_files is used/incremented for informational purposes.
    """
    global minimum_date
    global options
    num_files = 0
    for k in bucket.list():
        num_files += 1
        lm = iso8601_to_datetime(k.last_modified)
        if lm > minimum_date:  # Check last_modified newer/younger than min_age
            if options.verbose:
                print "Checked %d files (keys) and found a match." % num_files
            return True
    if options.verbose:
        print "Checked %d files (keys) without a match." % num_files
    return False


def get_youngest_key_in_bucket(bucket):
    """ Examine each key in bucket and return the youngest key
    """
    youngest = 0    # Track the youngest we've found yet
    for k in bucket.list():
        if not youngest:    # Needs to be initialized to a Key() once
            youngest = k
        elif k.last_modified > youngest.last_modified:
            youngest = k
    return youngest


def get_num_keys_in_bucket(bucket):
    """ Iterate through every key in .list() and increment a counter.
        Return the total count of every key.
    """
    num_files = 0    # Informational
    for k in bucket.list():
        num_files += 1    # Informational
    return num_files


def send_email(email_to, email_from, email_subject, email_msg):
    """ Send the given message using e-mail
    """
    import smtplib
    from email.mime.text import MIMEText
    msg = MIMEText(email_msg)
    msg['Subject'] = email_subject
    msg['From'] = email_from
    msg['To'] = email_to
    try:
        smtp_conn = smtplib.SMTP('localhost')
        smtp_conn.sendmail(email_from, email_to, msg.as_string())
        smtp_conn.quit()
        return
    except Exception:
        raise


def send_pushover(user, appkey, message):
    """ Send the given message using Pushover
    """
    import httplib
    import urllib
    try:
        pushover = httplib.HTTPSConnection("api.pushover.net:443")
        pushover.request("POST", "/1/messages.json",
            urllib.urlencode({
                "token": appkey,
                "user": user,
                "message": message,
                }),
                {"Content-type": "application/x-www-form-urlencoded"}
            )
        pushover.getresponse()
        return
    except Exception:
        raise


def main():
    """ Our main() method, handles core execution.
    """
    global minimum_date
    global options
    parser = optparse.OptionParser(usage="usage: %prog [options]",
                                   version="%prog 1.1")
    parser.add_option("-v", "--verbose",
                      action="count", dest="verbose", default=0,
                      help="More noise and stuff, repeat for higher levels")
    parser.add_option("-c", "--config",
                      dest="configfile", default="config.ini", metavar="FILE",
                      help="Use this configuration file instead of %default")
    (options, args) = parser.parse_args()

    if options.verbose:
        print "Verbosity set to %i" % options.verbose

    # Load the configuration
    configuration_file = ConfigParser.SafeConfigParser()
    try:
        configuration_file.readfp(open(options.configfile))
    except IOError as e:
        print "Error opening %s for reading. I/O error({0}): {1}".\
              format(e.errno, e.strerror) % options.configfile
        sys.exit(1)
    except ConfigParser.Error as e:
        print "Error while parsing your %s: %s" % (options.configfile, e)
        sys.exit(1)

    # Establish the "minimum date" (1 week ago) that all buckets
    # need to be newer than
    try:
        min_age = configuration_file.getint('Buckets', 'age')
        minimum_date = datetime.today() - timedelta(days=min_age)
        if options.verbose:
            print "Must be newer than %s" % minimum_date
    except ConfigParser.Error as e:
        print "Error! No minimum/threshold age defined: %s" % e
        sys.exit(1)

    # Load urllib/httplib only if the user's configured Pushover notifications
    try:
        pushover_appkey = False
        pushover_user = False
        pushover_appkey = configuration_file.get('Notification',
                                                 'pushover_appkey')
        pushover_user = configuration_file.get('Notification', 'pushover')
        if options.verbose > 1:
            print "Pushover support loaded."
    except ConfigParser.Error as e:
        # Quietly pass through if Pushover isn't configured
        pass

    # Load the smtp stuff only if the user's configured an email address
    try:
        email_to = False
        email_from = False
        email_subject = False
        ## Probably need _to, _from, maybe _subject
        email_to = configuration_file.get('Notification', 'email_to')
        email_from = configuration_file.get('Notification', 'email_from')
        email_subject = configuration_file.get('Notification', 'email_subject')
        if options.verbose > 1:
            print "Email support loaded."
    except ConfigParser.Error as e:
        # Quietly pass through if Pushover isn't configured
        pass

    # Advanced use - include any [Boto] configs as configuration for boto
    if configuration_file.has_section('Boto'):
        if options.verbose > 2:
            print "Merging [Boto] from our configuration into boto's"
        import boto
        boto.config.add_section('Boto')
        for k, v in configuration_file.items('Boto'):
            if options.verbose > 2:
                print "[Boto] Merging in %s=%s" % (k, v)
            boto.config.set('Boto', k, v)

    # Connecting to AWS
    try:
        from boto.s3.connection import S3Connection
        import boto
        conn = S3Connection( \
            configuration_file.get('AWS', 'AWS_ACCESS_KEY_ID'), \
            configuration_file.get('AWS', 'AWS_SECRET_ACCESS_KEY') \
            )
        if options.verbose > 1:
            print "Connected using AWS keys stored in %s" % options.configfile
    except ConfigParser.Error as e:
        # Probably couldn't find the variables in configuration_file,
        # try using our helper method instead
        conn = boto.connect_s3()
        if options.verbose > 1:
            print "Connected using environment AWS keys"
    except ImportError as e:
        print "You need the BOTO library installed."
        sys.exit(1)

    # Read in the ex/include from configuration_file
    buckets_exclude = []
    try:
        for entry in configuration_file.get('Buckets', 'exclude').split(','):
            buckets_exclude.append(entry.strip())
    except Exception as e:
        pass
    if options.verbose:
        print "Excluding: %s" % buckets_exclude

    buckets_include = []

    # Track the buckets that failed the check
    buckets_error = []

    if len(buckets_include):
        if options.verbose:
            print "Checking only the %d buckets defined in include=" %\
                  len(buckets_include)
        for bucket_include in buckets_include:
            if bucket_include in buckets_exclude:
                if options.verbose:
                    print "Skipping bucket %s due to exclude=" % bucket_include
                continue
            if options.verbose:
                print "Checking bucket %s" % bucket_include
            bucket = conn.get_bucket(bucket_include)
            if not check_bucket(bucket):
                print "Error! Bucket %s failed check, no keys modified " +\
                      "since %s." % (bucket_include, minimum_date)
                buckets_error.append(bucket_include)
            else:
                if options.verbose:
                    print "Bucket %s passed check." % bucket_include
            # Verbosity, I guess
            if options.verbose > 1:
                print " * %s (%s)  %i keys.\n" %\
                      (bucket.name,
                       iso8601_to_datetime(\
                           get_youngest_key_in_bucket(bucket).last_modified),
                       get_num_keys_in_bucket(bucket))
    else:
        buckets = conn.get_all_buckets()
        if options.verbose:
            print "Inspecting %d buckets (pre-exclude)" % len(buckets)
        for bucket in buckets:
            if bucket.name in buckets_exclude:
                if options.verbose:
                    print "Skipping bucket %s" % bucket.name
                continue
            if options.verbose:
                print "Checking bucket %s" % bucket.name
            if not check_bucket(bucket):
                print "Error! Bucket %s failed check, no keys modified " +\
                      "since %s." % (bucket.name, minimum_date)
                buckets_error.append(bucket.name)
            else:
                if options.verbose:
                    print "Bucket %s passed check." % bucket.name
            # Verbosity, I guess
            if options.verbose > 1:
                print " * %s (%s) %i keys.\n" %\
                      (bucket.name,
                       iso8601_to_datetime(\
                           get_youngest_key_in_bucket(bucket).last_modified),
                       get_num_keys_in_bucket(bucket))

    if options.verbose:
        print "Check complete, %d buckets failed." %\
              len(buckets_error), buckets_error

    # Send notifications as appropriate
    if len(buckets_error):
        # Build the list of failed buckets
        buckets_error_string = ""
        for bucket_error in buckets_error:
            buckets_error_string += " * %s (%s)\\n" % (bucket_error, \
                iso8601_to_datetime(\
                    get_youngest_key_in_bucket(\
                        conn.get_bucket(bucket_error) \
                    ).last_modified \
                    ) \
                )
        message = configuration_file.get('Notification', 'template').\
                    format(since=minimum_date, age=min_age,
                           failedbuckets=buckets_error_string)
        message = message.replace('\\n', "\n")
        if options.verbose:
            print "Notification message:", message

        if pushover_user and pushover_appkey:
            try:
                send_pushover(user=pushover_user, appkey=pushover_appkey,
                              message=message)
            except Exception as e:
                print "Exception while pushing notification to Pushover: %s" %\
                      e
                pass

        if email_to and email_from and email_subject:
            try:
                send_email(email_to=email_to, email_from=email_from,
                           email_msg=message, email_subject=email_subject)
            except Exception as e:
                print "Exception while sending email notification: %s" % e
                pass

        sys.exit(1)
    else:
        if options.verbose:
            print "All buckets are current."
        sys.exit(0)


if __name__ == "__main__":
    main()
