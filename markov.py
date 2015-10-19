#!/usr/bin/env python
import logging
import math
import os
import random
import re
import sys

from threading import RLock

from colortext import *

try:
    # use cPickle when using python2 for better performance
    import cPickle as pickle
except ImportError:
    import pickle


class MarkovChain:
    def __init__(self, dbFilePath=None):
        self.db = {("","") : ([], 1)}
        self.db_lock = RLock()

        self.dbFilePath = dbFilePath
        if not dbFilePath:
            self.dbFilePath = os.path.join(os.path.dirname(__file__),
                                           "markovdb")

        with self.db_lock:
            try:
                with open(self.dbFilePath, 'rb') as dbfile:
                    self.db = pickle.load(dbfile)
            except IOError:
                logging.warn(WARNING + ("Unable to read database file '%s': "
                                        "Using empty database" % self.dbFilePath))
            except ValueError:
                logging.warn(WARNING + ("Database '%s' corrupt or unreadable: "
                                        "Using empty database" % self.dbFilePath))

    def parseLineIntoSentences(self, line):
        line = re.sub('[\'/,@#<>!@#^&*]', '', line.lower())
        return line.split('.!?()')

    def bigrams(self, sentence):
        input = sentence.split(' ')
        output = []
        for i in range(len(input)-1):
            output.append( (input[i], input[i+1]) )
        return output

    def addLine(self, line):
        sentences = self.parseLineIntoSentences(line)
        for ss in sentences:
            bg = self.bigrams(ss)
            for ii in range(0,len(bg)-1):
                # if we're the last bigram, we map to EOL
                newValue = ""
                if ii == len(bg)-1:
                    newValue = "\n"
                else:
                    newValue = bg[ii+1][1]

                with self.db_lock:
                    if self.db.get(bg[ii]) == None:
                        # we've never seen this bigram
                        self.db[bg[ii]] = ([[1, newValue]], 1)
                    else:
                        # seen it:
                        val = self.db[bg[ii]]
                        found = False
                        for rr in val[0]:
                            if rr[1] == newValue:
                                rr[0] = rr[0] + 1
                                found = True
                                break
                        if not found:
                            val[0].append([1, bg[ii+1][1]])

                        self.db[bg[ii]] = (val[0], val[1]+1)

    def saveDatabase(self):
        with self.db_lock:
            try:
                with open(self.dbFilePath, 'wb') as dbfile:
                    pickle.dump(self.db, dbfile)
                return True
            except IOError:
                logging.error(ERROR +
                              ("Failed to write markov db to '%s'\n" %
                               self.dbFilePath))
                return False

    def respond(self, bigram):
        includeBigram = False
        # If no bigram given as a seed, pick a random one.
        if not bigram:
            with self.db_lock:
                bigram = random.sample(self.db, 1)[0]
                includeBigram = True
                logging.info(BLUE + "Picking " + str(bigram) + " as seed")

        # Must be a bigram
        if len(bigram) != 2:
            logging.error(ERROR +
                          ("Invalid bigram %s passed as seed" % str(bigram)))
            return ""

        response = [""]
        self._respondHelper(bigram, response)
        if includeBigram:
            response[0] = bigram[0] + " " + bigram[1] + " " + response[0]
        return response[0]

    def _respondHelper(self, bigram, response):
        # does it exist in our cache?
        with self.db_lock:
            if self.db.get(bigram) == None:
                # end?
                return
                '''
                #  pick a random bigram?
                which = random.random() * len(self.cache)
                ii = 0
                for k, v in self.cache.iteritems():
                  if ii == which:
                    bg = k
                    break
                  ii = ii + 1
                '''

        # pick a random response
        which = int(math.floor(random.random()*self.db[bigram][1]) + 1)
        values = self.db[bigram][0]
        ii = 0
        for v in values:
            ii = ii + v[0]
            if ii >= which:
                if response[0] == "":
                    response[0] = v[1]
                else:
                    response[0] = response[0] + " " + v[1]
                newbigram = (bigram[1], v[1])
                self._respondHelper(newbigram, response)
                return
