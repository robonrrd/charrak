#!/usr/bin/env python
import argparse
import errno
import httplib
import logging
import pickle
import random
import re
import sys
import socket
import string
import signal
import time

from threading import Timer, RLock

import logger
import markov
from colortext import *

parser = argparse.ArgumentParser(description='A snarky IRC bot.')
parser.add_argument("--host", help="The server to connect to", default="irc.perl.org")
parser.add_argument("--port", type=int, help="The connection port", default=6667)
parser.add_argument("--nick", help="The bot's nickname", default="charrak")
parser.add_argument("--realname", help="The bot's real name", default="charrak the kobold")
parser.add_argument("--owners", help="The list of owner nicks", default="nrrd, nrrd_, mrdo")
parser.add_argument("--channels", help="The list of channels to join", default="#haplessvictims")
parser.add_argument("--save_period", help="How often (in seconds) to save databases", default=300)
parser.add_argument("--seendb", help="Path to seendb", default="./seendb.pkl")
parser.add_argument("--markovdb", help="Path to markovdb", default="./charrakdb")


class Bot:
    def __init__(self, args):
        # IRC settings
        self.irc = None
        self.HOST = args.host
        self.PORT = args.port
        self.NICK = args.nick
        self.REALNAME = args.realname
        self.OWNERS = [string.strip(owner) for owner in args.owners.split(",")]
        self.CHANNELINIT = [string.strip(channel) for channel in args.channels.split(",")]
        self.IDENT='pybot'
        self.readbuffer='' #Here we store all the messages from server

        # Caches of IRC status
        self.who =  {} # lists of who is in what channels
        self.ops =  {} # lists of ops is in what channels
        self.seen = {} # lists of who said what when

        # Markov chain settings
        self.p_reply = 0.1

        # Regular db saves
        self.SAVE_TIME = args.save_period
        self.save_timer = None

        # Set up a lock for the seen db
        self.seendb_lock = RLock()
        self.SEENDB = args.seendb

        self.MARKOVDB = args.markovdb

        # signal handling
        signal.signal(signal.SIGINT, self.signalHandler)
        signal.signal(signal.SIGTERM, self.signalHandler)
        signal.signal(signal.SIGQUIT, self.signalHandler)

    # Irc communication functions
    def privmsg(self, speaking_to, text):
        logging.debug(PURPLE + speaking_to + PLAIN + " : " + BLUE + text)
        self.irc.send('PRIVMSG '+ speaking_to +' :' + text + '\r\n')

    def pong(self, server):
        #cprint(GREEN, "PONG " + server + "\n")
        self.irc.send("PONG %s\r\n" % server)

    # Picks a random confused reply
    def dunno(self, msg):
        replies = [ "I dunno, $who",
                    "I'm not following you."
                    "I'm not following you, $who."
                    "I don't understand.",
                    "You're confusing, $who." ]

        which = random.randint(0 , len(replies)-1)
        reply = re.sub( "$who", msg["speaker"], replies[which] )
        #self.irc.send('PRIVMSG '+ msg["speaking_to"] +' :' + reply + '\r\n')
        self.privmsg(msg["speaking_to"], reply)

    def eatLinesUntilText(self, stopText):
        # Loop until we encounter the passed in 'stopText'
        while 1:
            self.readbuffer = self.readbuffer + self.irc.recv(1024)
            temp = string.split(self.readbuffer, "\n")
            self.readbuffer = temp.pop( )

            for line in temp:
                logging.info(YELLOW + line)
                words = string.rstrip(line)
                words = string.split(words)

                if len(words) > 0 and (words[0]=="PING"):
                    self.pong(words[1])

                # This is a hack, but how should I detect when to join
                # a channel?
                if line.find(stopText) != -1:
                    return

    def eatLinesUntilEndOfNames(self, population, operators):
        # get the current population of the channel
        # :magnet.llarian.net 353 gravy = #test333 :gravy @nrrd
        # :magnet.llarian.net 366 gravy #test333 :

        while 1:
            self.readbuffer = self.readbuffer + self.irc.recv(1024)
            temp = string.split(self.readbuffer, "\n")
            self.readbuffer = temp.pop( )
            for line in temp:
                logging.info(YELLOW + line)
                words = string.rstrip(line)
                words = string.split(words)

                if(words[0]=="PING"):
                    self.pong(words[1])

                # This is a hack, but how should I detect when we're
                # done joining?
                elif line.find('End of /NAMES list')!=-1:
                    return

                elif len(words) > 4:
                    # get the current population of the channel
                    channel = words[4]
                    count = 0
                    for ww in words:
                        count = count + 1
                        if ww is "=":
                            break

                    # parse nicks
                    for ii in range(count+1, len(words)):
                        op = False
                        nick = ""
                        if words[ii][0] == "@":
                            op = True
                            nick = words[ii][1:]
                        elif words[ii][0] == ":":
                            nick = words[ii][1:]
                        else:
                            nick = words[ii]

                        population.append( nick )
                        if op is True:
                            operators.append( nick )


    # Join the IRC network
    def joinIrc(self):
        if self.irc:
            self.irc.close()
        self.irc = socket.socket()
        self.irc.connect((self.HOST, self.PORT))
        self.irc.send("NICK %s\r\n" % self.NICK)
        self.irc.send("USER %s %s bla :%s\r\n" % (self.IDENT, self.HOST, self.REALNAME))

        # This is a hack, but how should I detect when I've successfully joined
        # a channel?
        self.eatLinesUntilText('End of /MOTD command')

        # Join the initial channel
        for c in self.CHANNELINIT:
          self.joinChannel(c)


    def joinChannel(self, channel):
        self.irc.send('JOIN ' + channel + '\n')
        
        population = []
        operators = []
        self.eatLinesUntilEndOfNames(population, operators)
        self.who[ channel ] = population
        self.ops[ channel ] = operators

    def initMarkovChain(self):
        # Open our Markov chain database        
        self.mc = markov.MarkovChain(self.MARKOVDB)

    def loadSeenDB(self):
        with self.seendb_lock:
            try:
                self.seendb_lock.acquire()
                with open(self.SEENDB, 'rb') as seendb:
                    self.seen = pickle.load(seendb)
            except IOError:
                logging.error(ERROR + ("Unable to open '%s' for reading" % self.SEENDB))
            self.seendb_lock.release()

    def saveSeenDB(self):
        with self.seendb_lock:
            try:
                self.seendb_lock.acquire()
                with open(self.SEENDB, 'wb') as seendb:
                    pickle.dump(self.seen, seendb)
            except IOError:
                logging.error(ERROR + ("Unable to open 'seendb.pkl' for writing"))
            self.seendb_lock.release()

    def signalHandler(self, signal, frame):
        self.quit()

    def quit(self):
        if self.save_timer:
            self.save_timer.cancel()
        self.saveDatabases()
        self.irc.close()
        sys.exit(0)

    def saveDatabases(self):
      logging.info('Saving databases')

      self.seendb_lock.acquire()
      self.mc.saveDatabase()
      self.seendb_lock.release()
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


    def handleCommands( self, msg ):
        # is the speaker an owner or an op?
        # parse the message
        words = msg["text"].split()
        if words[0] == "op" and len(words) == 2:
            print " +o", words[1]
            # step through all channels we'e in an op the named user when we see her
            for chan in self.who:
                for nick in self.who[chan]:
                    if words[1] == nick:
                        logging.info(YELLOW + "+o " + nick)
                        self.irc.send('MODE '+ chan +' +o ' + nick + '\r\n')
                        self.ops[ chan ].append(nick)
            return True

        if words[0] == "seen" and len(words) == 2:
            nick = words[1]
            key = nick.lower()
            seen_msg = ""
            if self.seen.has_key(key):
                seen_msg = nick + " was last seen in "
                seen_msg = seen_msg + self.seen[key][0] + " " 
                last_seen = self.seen[key][1] # in seconds since epoch
                since = self.elapsedTime( time.time() - last_seen )
                seen_msg = seen_msg + since
                message = string.strip(self.seen[key][2])
                seen_msg = seen_msg + " saying '" + message + "'"
            else:
                seen_msg = "I haven't seen " + nick + "."
            self.privmsg(msg["speaking_to"], seen_msg)
            return True

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
        response = self.mc.respond(seed)
        if len(leading_words) > 0:
            leading_words = leading_words + " "
        reply = leading_words + response
        #print string.join(seed) + " :: " + reply
        if len(response) == 0:
            self.logChannel(self.NICK, "EMPTY_REPLY")
        else:
            self.privmsg(msg["speaking_to"], reply)
            self.logChannel(self.NICK, reply)

    @staticmethod
    def makeTinyUrl(url):
        # make a request to tinyurl.com to translate a url.
        # their API is of the format:
        # 'http://tinyurl.com/api-create.php?url=' + url
        conn = httplib.HTTPConnection("tinyurl.com")
        conn.request("GET", "api-create.php?url=" + url)
        r1 = conn.getresponse()
        if r1.status == 200:
            irc.send('PRIVMSG '+OWNER+' :' + r1.read() + '\r\n')        
        else:
            msg = 'PRIVMSG '+OWNER+' :' + 'Tinyurl problem: '
            msg += 'status=' + str(r1.status) + '\r\n'
            irc.send(msg)
        return


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

    def parsePrivateOwnerMessage( self, msg ):
        # The owner can issue commands to the bot, via strictly
        # constructed private messages
        words = msg["text"].split()

        logging.info("Received private message: '" + string.strip(msg["text"]) + "'")

        # simple testing
        if len(words) == 1 and words[0] == 'ping':
            self.logChannel(msg["speaker"], GREEN + "pong")
            self.irc.send('PRIVMSG '+ msg["speaker"] +' :' + 'pong\r\n')
            return

        # set internal variables
        elif len(words) == 3 and words[0] == "set":
            # set reply probability
            if words[1] == "p_reply":
                self.logChannel(msg["speaker"], GREEN + "SET P_REPLY " + words[2])
                self.p_reply = float(words[2])
                self.irc.send('PRIVMSG '+ msg["speaker"] +' :' + str(self.p_reply) + '\r\n')
            else:
                self.dunno()
            return

        elif len(words) == 2 and words[0] == "get":
            # set reply probability
            if words[1] == "p_reply":
                self.logChannel(msg["speaker"], GREEN + "GET P_REPLY " + str(self.p_reply))
                self.irc.send('PRIVMSG '+ msg["speaker"] +' :' + str(self.p_reply) + '\r\n')
                return

        # leave a channel
        elif len(words) == 2 and words[0] == 'leave':
            channel = str(words[1]);
            if channel[0] != '#':
                channel = '#' + channel

            self.logChannel(msg["speaker"], PURPLE + "PART " + channel)
            self.irc.send('PART ' + channel + '\r\n')
            return

        # join a channel
        elif len(words) == 2 and words[0] == 'join':
            channel = str(words[1]);
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

    def determineWhoIsBeingAddressed( self, msg ):
        msg["addressing"] = ""
        words = msg["text"].split()

        # strip off direct addressing (i.e. "jeff: go jump in a lake")
        first_word = words[0].rstrip(":,!?")

        # if the person is speaking to the channel
        if msg["speaking_to"][0] == "#":
            #..search the channel for nicks matchig this word
            if first_word in self.who[ msg["speaking_to"] ]:
                #..and snip them out if they're found
                msg["addressing"] = first_word
                newline = string.join(words[1:], " ")
                msg["text"] = newline
                if first_word == self.NICK:
                    msg["p_reply"] = 1.0
        else:
            # ..otherwise we're being directly addressed
            msg["p_reply"] = 1.0

        return

    # private message from user
    # :nrrd!~jeff@bacon2.burri.to PRIVMSG gravy :foo
    # public channel message
    # :nrrd!~jeff@bacon2.burri.to PRIVMSG #test333 :foo
    def parsePrivMessage(self, line):
        m = re.search('^:(\w*)!.(\w*)@(\S*)\s(\S*)\s(\S*) :(.*)', line)

        if m is None:
            return

        text = m.group(6)
        text = self.preprocessText(text)
        
        msg = {
            "speaker"       : m.group(1) ,                 # the nick of who's speaking
            "speaker_email" : m.group(2)+'@'+m.group(3) ,  # foo@bar.com
            "privmsg"       : m.group(4) ,                 # should be PRIVMSG
            "speaking_to"   : m.group(5) ,                 # could be self.NICK or a channel
            "text"          : text ,                       # what's said
            "p_reply"       : self.p_reply                 # probably of responding
            }

        if msg["privmsg"] != 'PRIVMSG':
            return
      
        if msg["speaking_to"][0] == "#":
            nick = msg["speaker"].lower()
            self.seen[nick] = [ msg["speaking_to"], time.time(), string.strip(msg["text"]) ]
 
        self.determineWhoIsBeingAddressed( msg )

        if msg["speaking_to"] == self.NICK and msg["speaker"] in self.OWNERS: 
            self.parsePrivateOwnerMessage( msg )
        elif msg["speaking_to"] != self.NICK:
            self.parsePublicMessage( msg )

    # information about MODE changes (ops, etc.) in channels
    def parseModeMessage(self, words):
        # right now, we only care about ops
        if len(words) < 5:
            return
        channel = words[2]
        action = words[3]
        on_who = words[4]

        if action == "+o":
            if on_who not in self.ops[channel]:
                self.ops[channel].append(on_who)
                return

        if action == "-o":
            if on_who in self.ops[channel]:
                self.ops[channel].remove(on_who)
                return

    def main(self):
        logger.initialize("./")
        self.initMarkovChain()
        self.loadSeenDB()
        self.joinIrc()

        self.save_timer = Timer(self.SAVE_TIME, self.handleSaveDatabasesTimer)
        self.save_timer.start()

        # Loop forever, parsing input text
        while True:
            try:
                recv = self.irc.recv(1024)
                while len(recv) == 0:
                    logging.warning(WARNING + "Connection closed: Trying to reconnect in 5 seconds...")
                    time.sleep(5)
                    self.joinIrc()
                    recv = self.irc.recv(1024)

                self.readbuffer = self.readbuffer + self.irc.recv(1024)
            except socket.error as (code, msg):
                if code != errno.EINTR:
                    raise

            temp = string.split(self.readbuffer, "\n")
            self.readbuffer = temp.pop( )

            for line in temp:
                # strip whitespace and split into words
                words = string.rstrip(line)
                words = string.split(words)

                if words[0]=="PING":
                    self.pong(words[1])

                elif line.find('PRIVMSG')!=-1: #Call a parsing function
                    self.parsePrivMessage(line)
                    
                elif words[1] == "MODE":
                    self.parseModeMessage(words)


#####

if __name__ == "__main__":
    bot = Bot(parser.parse_args())
    bot.main()
