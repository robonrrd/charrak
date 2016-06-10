#!/usr/bin/python
import logging
import markov
import argparse
import string
import sys

try:
  import cPickle as pickle
except ImportError:
  import pickle

#

argparser = argparse.ArgumentParser(description='Convert databases.')
argparser.add_argument('--in', dest='db_in', default='./oldcharrakdb')
argparser.add_argument('--out', dest='db_out', default='./newcharrakdb')
args = argparser.parse_args()

#

db_in = str(args.db_in)
db_out = str(args.db_out)

try:
  with open(db_in, 'rb') as dbfile:
    db = pickle.load(dbfile)
except IOError:
  logging.error('Unable to read database file "%s"' % db_in)
  sys.exit(1)
except ValueError:
  logging.error('Database "%s" corrup or unreadable' % db_in)
  sys.exit(2)

mc = markov.MarkovChain(db_out)
mc.db = db[0]
mc.saveDatabase()

