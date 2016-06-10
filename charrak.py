#!/usr/bin/env python
import argparse
# import httplib
import logging
import pickle
import random
import re
import sys
import string
import signal
import time
import os
import shutil

from threading import Timer, RLock

import irc
import logger
import markov
from colortext import *

PARSER = argparse.ArgumentParser(description='A snarky IRC bot.')
PARSER.add_argument("--host", help="The server to connect to", default="irc.perl.org")
PARSER.add_argument("--port", type=int, help="The connection port", default=6667)
PARSER.add_argument("--nick", help="The bot's nickname", default="charrak")
PARSER.add_argument("--realname", help="The bot's real name", default="charrak the kobold")
PARSER.add_argument("--owners", help="The list of owner nicks", default="nrrd, nrrd_, mrdo, mrdo_")
PARSER.add_argument("--channels", help="The list of channels to join", default="#haplessvictims")
PARSER.add_argument("--save_period", help="How often (in seconds) to save databases", default=300)
PARSER.add_argument("--seendb", help="Path to seendb", default="./seendb.pkl")
PARSER.add_argument("--markovdb", help="Path to markovdb", default="./charrakdb")
PARSER.add_argument("--ignore", help="The optional list of nicks to ignore", default="")


class Bot(object):
    def __init__(self, args):
        # IRC settings
        self.irc = None
        self.HOST = args.host
        self.PORT = args.port
        self.NICK = args.nick
        self.REALNAME = args.realname
        self.OWNERS = [string.strip(owner) for owner in args.owners.split(",")]
        self.IGNORE = [string.strip(ignore) for ignore in args.ignore.split(",")]
        self.CHANNELINIT = [string.strip(channel) for channel in args.channels.split(",")]
        self.IDENT='pybot'

        # Caches of IRC status
        self.seen = {} # lists of who said what when

        # Markov chain settings
        self.p_reply = 0.1

        # Regular db saves
        self.SAVE_TIME = float(args.save_period)
        self.save_timer = None

        # Set up a lock for the seen db
        self.seendb_lock = RLock()
        self.SEENDB = args.seendb

        self.MARKOVDB = args.markovdb

        # signal handling
        signal.signal(signal.SIGINT, self.signalHandler)
        signal.signal(signal.SIGTERM, self.signalHandler)
        signal.signal(signal.SIGQUIT, self.signalHandler)

    # Picks a random confused reply
    def dunno(self, msg):
        replies = ["I dunno, $who",
                   "I'm not following you."
                   "I'm not following you, $who."
                   "I don't understand.",
                   "You're confusing, $who."]

        which = random.randint(0, len(replies)-1)
        reply = re.sub("$who", msg["speaker"], replies[which])
        self.irc.privmsg(msg["speaking_to"], reply)

    # Join the IRC network
    def joinIRC(self):
        self.irc = irc.Irc(self.HOST, self.PORT, self.NICK, self.IDENT,
                           self.REALNAME)

        # Join the initial channels
        for chan in self.CHANNELINIT:
            self.irc.join(chan)
            if not self.irc.isop(self.NICK, chan):
                op_reqs = [
                    'Op me!', 'Yo, ops?',
                    'What does a kobold have to do to get ops around here?']
                which = random.randint(0, len(op_reqs)-1)
                self.irc.privmsg(chan, op_reqs[which])

    def initMarkovChain(self):
        # Open our Markov chain database
        self.mc = markov.MarkovChain(self.MARKOVDB)

    def loadSeenDB(self):
        with self.seendb_lock:
            try:
                with open(self.SEENDB, 'rb') as seendb:
                    self.seen = pickle.load(seendb)
            except IOError:
                logging.error(WARNING +
                              ("Unable to open seen db '%s' for reading" %
                               self.SEENDB))

    def saveSeenDB(self):
        with self.seendb_lock:
            try:
                with open(self.SEENDB, 'wb') as seendb:
                    pickle.dump(self.seen, seendb)
            except IOError:
                logging.error(ERROR +
                              ("Unable to open seed db '%s' for writing" %
                               self.SEENDB))

    def signalHandler(self, unused_signal, unused_frame):
        self.quit()

    def quit(self):
        if self.save_timer:
            self.save_timer.cancel()
        self.saveDatabases()
        self.irc = None
        sys.exit(0)

    @staticmethod
    def createBackup(source):
        if os.path.isfile(source):
            dst = source + ".bak"
            shutil.copyfile(source, dst)

    def saveDatabases(self):
        logging.info('Saving databases')
        self.createBackup(self.MARKOVDB)
        self.mc.saveDatabase()

        self.createBackup(self.SEENDB)
        self.saveSeenDB()

    def handleSaveDatabasesTimer(self):
        self.saveDatabases()
        self.save_timer = Timer(self.SAVE_TIME, self.handleSaveDatabasesTimer)
        self.save_timer.start()

    @staticmethod
    def elapsedTime(ss):
        reply = ""
        startss = ss
        if ss > 31557600:
            years = ss // 31557600
            reply = reply + ("%g years " % years)
            ss = ss - years*31557600

        if ss > 2678400: # 31 days
            months = ss // 2678400
            reply = reply + ("%g months " % months)
            ss = ss - months*2678400

        if ss > 604800:
            weeks = ss // 604800
            reply = reply + ("%g weeks " % weeks)
            ss = ss - weeks*604800

        if ss > 86400:
            days = ss // 86400
            reply = reply + ("%g days " % days)
            ss = ss - days*86400

        if ss > 3600:
            hours = ss // 3600
            reply = reply + ("%g hours " % hours)
            ss = ss - hours*3600

        if ss > 60:
            minutes = ss // 60
            reply = reply + ("%g minutes " % minutes)
            ss = ss - minutes*60

        if ss != startss:
            reply = reply + "and "
        reply = reply + ("%.3f seconds ago" % ss)
        return reply

    def handleCommands(self, msg):
        # parse the message
        words = msg["text"].split()

        # Handle messages such as "charrak?"
        if len(words) < 1:
            return False

        if words[0] == '!op' and len(words) == 2:
            # Is the speaker an owner or an op?
            speaker = msg["speaker"]
            is_valid = (speaker in self.OWNERS) or self.irc.isop(speaker)

            if not is_valid:
                logging.info(YELLOW + speaker + " is not an op or owner")
                return False

            self.irc.makeop(words[1])
            return True

        elif words[0] == '!seen' and len(words) == 2:
            nick = words[1]
            key = nick.lower()
            seen_msg = ""
            if self.seen.has_key(key):
                seen_msg = nick + " was last seen in "
                seen_msg = seen_msg + self.seen[key][0] + " "
                last_seen = self.seen[key][1] # in seconds since epoch
                since = self.elapsedTime(time.time() - last_seen)
                seen_msg = seen_msg + since
                message = string.strip(self.seen[key][2])
                seen_msg = seen_msg + ' saying "' + message + '"'
            else:
                seen_msg = "I haven't seen " + nick + "."
            self.irc.privmsg(msg["speaking_to"], seen_msg)
            return True

        elif words[0] == '!owners':
            self.irc.privmsg(msg['speaking_to'],
                             ('I would give up my bucket for %s' %
                              ','.join(self.OWNERS)))

        return False

    @staticmethod
    def logChannel(speaker, msg):
        logging.debug(CYAN + speaker + PLAIN + " : " + BLUE + msg)

    def possiblyReply(self, msg):
        PUNCTUATION = ",./?><;:[]{}\'\"!@#$%^&*()_-+="
        words = string.strip(msg["text"], PUNCTUATION).split()

        leading_words = ""
        seed = None

        # If we have enough words and the random chance is enough, reply based on the message.
        if len(words) >= 2 and random.random() <= msg["p_reply"]:
            logging.info(GREEN + "Trying to reply to '" + str(words) + "'")
            # Use a random bigram of the input message as a seed for the Markov chain
            max_index = min(6, len(words)-1)
            index = random.randint(1, max_index)
            seed = (words[index-1], words[index])
            leading_words = string.join(words[0:index+1])

        # If not, and we weren't referenced explicitly in the message, return early.
        # TODO: fix issue where this doesn't match if NICK contains one of PUNCTUATION.
        if not seed and (self.NICK.lower() not in [string.strip(word, PUNCTUATION).lower() for word in words]):
            return

        # generate a response
        response = string.strip(self.mc.respond(seed))
        if len(leading_words) > 0:
            leading_words = leading_words + " "
        reply = leading_words + response
        #print string.join(seed) + " :: " + reply
        if len(response) == 0:
            self.logChannel(self.NICK, "EMPTY_REPLY")
        else:
            self.irc.privmsg(msg["speaking_to"], reply)
            self.logChannel(self.NICK, reply)

    # @staticmethod
    # def makeTinyUrl(url):
    #     # make a request to tinyurl.com to translate a url.
    #     # their API is of the format:
    #     # 'http://tinyurl.com/api-create.php?url=' + url
    #     conn = httplib.HTTPConnection("tinyurl.com")
    #     conn.request("GET", "api-create.php?url=" + url)
    #     r1 = conn.getresponse()
    #     if r1.status == 200:
    #         irc.send('PRIVMSG '+OWNER+' :' + r1.read() + '\r\n')
    #     else:
    #         msg = 'Tinyurl problem: status=' + str(r1.status)
    #         self.irc.privmsg(OWNER, msg)
    #     return


    def parsePublicMessage(self, msg):
        q = re.search('.*(http://\S*)', msg["text"])
        if q is not None:
            #self.makeTinyUrl( str(q.groups(0)[0]) )
            return

        # add the spoken phrase to the log
        self.logChannel(msg["speaker"], msg["text"])

        # If a user has issued a command, don't do anything else.
        if self.handleCommands(msg):
            return

        self.possiblyReply(msg)

        # add the phrase to the markov database
        self.mc.addLine(msg["text"])

    def parsePrivateOwnerMessage(self, msg):
        # The owner can issue commands to the bot, via strictly
        # constructed private messages
        words = msg["text"].split()

        logging.info("Received private message: '" +
                     string.strip(msg["text"]) + "'")

        # simple testing
        if len(words) == 1 and words[0] == 'ping':
            self.logChannel(msg["speaker"], GREEN + 'pong')
            self.irc.privmsg(msg["speaker"], 'pong')
            return

        # set internal variables
        elif len(words) == 3 and words[0] == "set":
            # set reply probability
            if words[1] == "p_reply":
                self.logChannel(msg["speaker"],
                                GREEN + "SET P_REPLY " + words[2])
                self.p_reply = float(words[2])
                self.irc.privmsg(msg["speaker"], str(self.p_reply))
            else:
                self.dunno(msg)
            return

        elif len(words) == 2 and words[0] == "get":
            # set reply probability
            if words[1] == "p_reply":
                self.logChannel(msg["speaker"],
                                GREEN + "GET P_REPLY " + str(self.p_reply))
                self.irc.privmsg(msg["speaker"], str(self.p_reply))
                return

        # leave a channel
        elif len(words) == 2 and (words[0] == 'leave' or words[0] == 'part'):
            self.logChannel(msg["speaker"], PURPLE + "PART " + words[1])
            self.irc.part(words[1])
            return

        # join a channel
        elif len(words) == 2 and words[0] == 'join':
            channel = str(words[1])
            if channel[0] != '#':
                channel = '#' + channel

            self.logChannel(msg["speaker"], PURPLE + "JOIN " + channel)
            self.irc.send('JOIN ' + channel + '\r\n')
            return

        # quit
        elif len(words) == 1 and (words[0] == 'quit' or words[0] == 'exit'):
            self.logChannel(msg["speaker"], RED + "QUIT")
            self.quit()

        # if we've hit no special commands, parse this message like it was public
        self.parsePublicMessage(msg)

    @staticmethod
    def preprocessText(text):
        # remove all color codes
        text = re.sub('\x03(?:\d{1,2}(?:,\d{1,2})?)?', '', text)
        return text

    def determineWhoIsBeingAddressed(self, msg):
        msg["addressing"] = ""
        words = msg["text"].split()
        if len(words) == 0:
            return

        # strip off direct addressing (i.e. "jeff: go jump in a lake")
        first_word = words[0].rstrip(":,!?")

        # if the person is speaking to the channel
        if msg["speaking_to"][0] == "#":
            # see if we're being spoken to.
            if first_word == self.NICK:
                msg["p_reply"] = 1.0
            #..search the channel for nicks matchig this word
            elif first_word in self.irc.who[msg["speaking_to"]]:
                #..and snip them out if they're found
                msg["addressing"] = first_word
                newline = string.join(words[1:], " ")
                msg["text"] = newline
                if first_word == self.NICK:
                    msg["p_reply"] = 1.0
        else:
            # ..otherwise we're being directly addressed
            msg["p_reply"] = 1.0

    # private message from user
    # :nrrd!~jeff@bacon2.burri.to PRIVMSG gravy :foo
    # public channel message
    # :nrrd!~jeff@bacon2.burri.to PRIVMSG #test333 :foo
    def parsePrivMessage(self, line):
        # ignore any line with a url in it
        m = re.search('^:(\w*)!.(\w*)@(\S*)\s(\S*)\s(\S*) :(.*)', line)
        if m is None:
            return

        text = m.group(6)
        text = self.preprocessText(text)

        msg = {
            "speaker"       : m.group(1) ,                # the nick of who's speaking
            "speaker_email" : m.group(2)+'@'+m.group(3),  # foo@bar.com
            "privmsg"       : m.group(4),                 # should be PRIVMSG
            "speaking_to"   : m.group(5),                 # could be self.NICK or a channel
            "text"          : text,                       # what's said
            "p_reply"       : self.p_reply                # probably of responding
        }

        if msg["privmsg"] != 'PRIVMSG':
            return

        if msg["speaking_to"][0] == "#":
            nick = msg["speaker"].lower()
            # Lock here to avoid writing to the seen database while pickling it.
            with self.seendb_lock:
                self.seen[nick] = [msg["speaking_to"], time.time(),
                                   string.strip(msg["text"])]

        if msg["speaker"] in self.IGNORE:
            return

        if msg["speaking_to"] == self.NICK and msg["speaker"] in self.OWNERS:
            self.parsePrivateOwnerMessage(msg)
        elif msg["speaking_to"] != self.NICK:
            self.parsePublicMessage(msg)

    # information about MODE changes (ops, etc.) in channels
    def parseModeMessage(self, words):
        # right now, we only care about ops
        if len(words) < 5:
            return
        channel = words[2]
        action = words[3]
        on_who = words[4]

        if action == "+o":
            if not self.irc.isop(on_who, channel=channel):
                self.irc.addop(channel, on_who)
                return

        if action == "-o":
            if self.irc.isop(on_who, channel=channel):
                self.irc.rmop(channel, on_who)
                return

    def main(self):
        logger.initialize("./")
        self.initMarkovChain()
        self.loadSeenDB()
        self.joinIRC()

        self.save_timer = Timer(self.SAVE_TIME, self.handleSaveDatabasesTimer)
        self.save_timer.start()

        # Loop forever, parsing input text
        while True:
            try:
                recv = self.irc.readlines()
            except irc.ConnectionClosedException:
                logging.warning(WARNING + "Connection closed: Trying to reconnect in 5 seconds...")
                time.sleep(5)
                self.joinIRC()
                continue

            for line in recv:
                # strip whitespace and split into words
                words = string.rstrip(line)
                words = string.split(words)

                if words[0]=="PING":
                    self.irc.pong(words[1])
                elif line.find('PRIVMSG')!=-1:  # Call a parsing function
                    self.parsePrivMessage(line)
                elif words[1] == "MODE":
                    self.parseModeMessage(words)

#####

if __name__ == "__main__":
    bot = Bot(PARSER.parse_args())
    bot.main()
