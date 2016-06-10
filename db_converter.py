#!/usr/bin/python
import logging
import markov
import argparse
import sys

try:
    import cPickle as pickle
except ImportError:
    import pickle

#

ARGPARSER = argparse.ArgumentParser(description='Convert databases.')
ARGPARSER.add_argument('--in', dest='db_in', default='./oldcharrakdb')
ARGPARSER.add_argument('--out', dest='db_out', default='./newcharrakdb')
ARGS = ARGPARSER.parse_args()

#

DB_IN = str(ARGS.db_in)
DB_OUT = str(ARGS.db_out)

try:
    with open(DB_IN, 'rb') as dbfile:
        DB = pickle.load(dbfile)
except IOError:
    logging.error('Unable to read database file "%s"', DB_IN)
    sys.exit(1)
except ValueError:
    logging.error('Database "%s" corrupt or unreadable', DB_IN)
    sys.exit(2)

MC = markov.MarkovChain(DB_OUT)
MC.db = DB[0]
MC.saveDatabase()

