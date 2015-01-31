#!/usr/bin/env python
import os
import sys
import math
import random
import re
try:
    # use cPickle when using python2 for better performance
    import cPickle as pickle
except ImportError:
    import pickle


class MarkovChain:
    def __init__(self, dbFilePath=None):
        self.cache = { ("","") : [] }
        self.total = { ("","") : 1 }

        self.dbFilePath = dbFilePath
        if not dbFilePath:
            self.dbFilePath = os.path.join(os.path.dirname(__file__), "markovdb")
        try:
            with open(self.dbFilePath, 'rb') as dbfile:
                db = pickle.load(dbfile)
                self.cache = db[0]
                self.total = db[1]
                dbfile.close()

        except IOError:
            print('Database file not found, using empty database')
        except ValueError:
            print('Database corrupt or unreadable, using empty database')


    def parseLineIntoSentences(self, line):
        line = re.sub('[\',@#<>!@#^&*]', '', line.lower())
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

                if self.cache.get( bg[ii] ) == None: 
                    # we've never seen this bigram
                    self.cache[ bg[ii] ] = [ [1, newValue] ]
                    self.total[ bg[ii] ] = 1
                else:
                    # seen it:
                    val = self.cache[ bg[ii] ]
                    found = False
                    for rr in val:
                        if rr[1] == newValue:
                            rr[0] = rr[0] + 1
                            found = True
                            break
                    if not found:
                        val.append( [1, bg[ii+1][1]] )

                    self.cache[ bg[ii] ] = val
                    self.total[ bg[ii] ] = self.total[ bg[ii] ] + 1

    def saveDatabase(self):
        db = [ self.cache, self.total ]
        try:
            with open(self.dbFilePath, 'wb') as dbfile:
                pickle.dump(db, dbfile)
            # It looks like db was written successfully
            return True
        except IOError:
            sys.stderr.write('Database file could not be written')
            return False

    def respond(self, line, response):
        if len(line) != 2:
            return ""

        self._respondHelper(line, response)
        return line[0] + " " + line[1] + " " + response[0]

    def _respondHelper(self, line, response):
        # create the bigram
        bg = (line[0], line[1])

        # does it exist in our cache?
        if self.cache.get( bg ) == None: 
            # end?
            return
            '''
            #  pick a random bigram?
            which = random.random()*len(self.cache)
            ii = 0
            for k, v in self.cache.iteritems():
                if ii == which:
                    bg = k
                    break
                ii = ii + 1
            '''

        # pick a random response
        which = int( math.floor(random.random()*self.total[bg]) + 1)
        values = self.cache[ bg ]
        ii = 0
        for v in values:
            ii = ii + v[0]
            if ii >= which:
                if response[0] == "":
                    response[0] = v[1]
                else:
                    response[0] = response[0] + " " + v[1]
                newline = [line[1], v[1]]
                self._respondHelper( newline, response )
                return
