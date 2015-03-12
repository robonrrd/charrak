#!/usr/bin/env python
import sys
import re
import markov


files = sys.argv[1:]
if not files:
    files = ["/dev/stdin"]


mc = markov.MarkovChain("./traineddb")

for file in files:
    f = open(file)

    for line in f:
        words = line.split()
        # we have to handle charrak's replies specially (we want to ignore them)
        if words[0] == "charrak":
            empty_reply_index = line.find("EMPTY REPLY")
            if empty_reply_index > -1:
                line = line[empty_reply_index+11:]
                words = line.split()

            else:
                cr_index = line.find("\r")
                line = line[cr_index+1:]
                words = line.split()

        if len(words) > 3:
            text = " ".join(words[3:])
            #text = re.sub(r'[^a-zA-Z ]+', '', text).lstrip().lower()
            text = text.lstrip()
            if not text.isspace() and len(text) > 0:
                mc.addLine(text)

    f.close()

mc.saveDatabase()
