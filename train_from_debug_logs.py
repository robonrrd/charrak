#!/usr/bin/python
import sys
import re
import markov
import argparse
import datetime
import dateutil
from dateutil.parser import *
import string

#

argparser = argparse.ArgumentParser(description='Process debug logs.')
argparser.add_argument('files', nargs='?', type=argparse.FileType('r'), default=sys.stdin)
argparser.add_argument('--before', dest='beforedate', default=datetime.date.max)
argparser.add_argument('--after', dest='afterdate', default=datetime.date.min)
argparser.add_argument('--db', dest='db', default='./traineddb')
argparser.add_argument('--nick', dest='nick', default='charrak')
args = argparser.parse_args()

#

before_date = str(args.beforedate)
after_date = str(args.afterdate)

before = dateutil.parser.parse(before_date)
after = dateutil.parser.parse(after_date)

mc = markov.MarkovChain(str(args.db))

for line in args.files:
    time_text = line.split(':')
    if len(time_text) < 3:
        continue

    timestamp = time_text[0] + ":" + time_text[1]+ ":" + time_text[2].split(',')[0]
    cur_time = dateutil.parser.parse(timestamp)

    if cur_time > before or cur_time < after:
        continue

    words = line.split(':')

    if (words[3] == 'INFO' or words[3] == 'WARNING' or words[3] == 'ERROR'):
        continue

    # '20:1b:5b:39:36:6d:' nick '1b:5b:30:6d:20'
    who = words[4][6:len(words[4])-5]

    if who == str(args.nick):
        continue

    color_what = ''.join(words[5:])
    what = color_what[6:len(color_what)-5]

    if not what.isspace() and len(what) > 0:
        mc.addLine(what)

mc.saveDatabase()

