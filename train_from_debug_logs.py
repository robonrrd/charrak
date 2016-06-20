#!/usr/bin/python
import sys
import markov
import argparse
import datetime
import dateutil
import dateutil.parser

#

ARGPARSER = argparse.ArgumentParser(description='Process debug logs.')
ARGPARSER.add_argument('files', nargs='?', type=argparse.FileType('r'),
                       default=sys.stdin)
ARGPARSER.add_argument('--before', dest='beforedate', default=datetime.date.max)
ARGPARSER.add_argument('--after', dest='afterdate', default=datetime.date.min)
ARGPARSER.add_argument('--db', dest='db', default='./traineddb')
ARGPARSER.add_argument('--nick', dest='nick', default='charrak')
ARGS = ARGPARSER.parse_args()

#

BEFORE_DATE = str(ARGS.beforedate)
AFTER_DATE = str(ARGS.afterdate)

BEFORE = dateutil.parser.parse(BEFORE_DATE)
AFTER = dateutil.parser.parse(AFTER_DATE)

MC = markov.MarkovChain(str(ARGS.db))

for line in ARGS.files:
    time_text = line.split(':')
    if len(time_text) < 3:
        continue

    timestamp = (time_text[0] + ":" + time_text[1]+ ":" +
                 time_text[2].split(',')[0])
    cur_time = dateutil.parser.parse(timestamp)

    if cur_time > BEFORE or cur_time < AFTER:
        continue

    words = line.split(':')

    if words[3] == 'INFO' or words[3] == 'WARNING' or words[3] == 'ERROR':
        continue

    # '20:1b:5b:39:36:6d:' nick '1b:5b:30:6d:20'
    who = words[4][6:len(words[4])-5]

    if who == str(ARGS.nick):
        continue

    color_what = ''.join(words[5:])
    what = color_what[6:len(color_what)-5]

    if not what.isspace() and len(what) > 0:
        MC.addLine(what)

MC.saveDatabase()

