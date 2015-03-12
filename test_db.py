#!/usr/bin/env python
import sys
import re
import markov
import random
import string


db_file = sys.argv[1]
if not db_file:
    db_file = "traineddb"

mc = markov.MarkovChain(db_file)

while True:
    text = raw_input(": ")
    text = string.strip(text, ",./?><;:[]{}\'\"!@#$%^&*()_-+=")
    words = text.split()

    if len(words) < 2:
        continue

    # Use a random bigram of the input message as a seed for the Markov chain
    max_index = min( 6, len(words)-1)
    index = random.randint( 1, max_index)
    seed = [ words[index-1], words[index]]
    leading_words = string.join(words[0:index+1])

    words = leading_words.split()
    seed = [words[-2], words[-1]]

    print ">>", seed
    # generate a response
    response = [""]
    mc.respond( seed, response )

    if response[0] == "":
        print "EMPTY REPLY"
    else:
        reply = leading_words + " " + response[0]
        print reply
