#!/usr/bin/env python
import sys
import markov
import string


FILES = sys.argv[1:]
if not FILES:
    FILES = ["/dev/stdin"]


MC = markov.MarkovChain("./traineddb")

for fi in FILES:
    f = open(fi)

    for line in f:
        words = line.split()
        # we have to handle charrak's replies specially (we want to ignore them)
        if words[0] == "charrak":
            empty_reply_index = line.find("EMPTY REPLY")
            if empty_reply_index > -1:
                line = line[empty_reply_index+11:]
            else:
                cr_index = line.find("\r")
                line = line[cr_index+1:]

            line = filter(string.printable.__contains__, line)
            words = line.split()

        if len(words) > 3:
            words = line.split()
            if words[3] == "ACTION":
                continue

            text = " ".join(words[3:])
            text = text.lstrip()
            if not text.isspace() and len(text) > 0:
                MC.addLine(text)

    f.close()

MC.saveDatabase()
