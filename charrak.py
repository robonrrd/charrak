#!/usr/bin/env python
import pickle
import sys
import socket
import string
import signal
import re
import httplib
import random
import time
import markov
from colortext import *

class Bot:
    def __init__(self):
        # IRC settings
        self.irc = None
        self.HOST='irc.perl.org' # The server we want to connect to
        self.PORT=6667           # The connection port (usually 6667)
        self.NICK='charrak'      # The bot's nickname
        self.REALNAME='charrak the kobold'
        self.IDENT='pybot'
        self.OWNERS=[ "nrrd", "nrrd-", "nrrd_" ] # The bot owners
        self.CHANNELINIT='#haplessvictims' #The default channel for the bot
        self.readbuffer='' #Here we store all the messages from server

        # Caches of IRC status
        self.who =  {} # lists of who is in what channels
        self.ops =  {} # lists of ops is in what channels
        self.seen = {} # lists of who said what when

        # Markov chain settings
        self.P_REPLY = 0.1

        # Logging file settings
        self.LOGFILE_MAX_LINES = 1000

        # signal handling
        signal.signal(signal.SIGINT, self.signalHandler)
        signal.signal(signal.SIGTERM, self.signalHandler)
        signal.signal(signal.SIGQUIT, self.signalHandler)

    # Irc communication functions
    def privmsg(self, speaking_to, text):
        cprint(PURPLE, speaking_to)
        cprint(PLAIN, ": "+text)
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
                cprint(YELLOW, line + "\n")
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
                cprint(YELLOW, line + "\n")
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
        self.irc = socket.socket( )
        self.irc.connect((self.HOST, self.PORT))
        self.irc.send("NICK %s\r\n" % self.NICK)
        self.irc.send("USER %s %s bla :%s\r\n" % (self.IDENT, self.HOST, self.REALNAME))

        # This is a hack, but how should I detect when I've successfully joined
        # a channel?
        self.eatLinesUntilText('End of /MOTD command')

        # Join the initial channel
        self.joinChannel( self.CHANNELINIT )


    def joinChannel(self, channel):
        self.irc.send('JOIN ' + channel + '\n')
        
        population = []
        operators = []
        self.eatLinesUntilEndOfNames(population, operators)
        self.who[ channel ] = population
        self.ops[ channel ] = operators

    def initMarkovChain(self):
        # Open our Markov chain database        
        self.mc = markov.MarkovChain("./charrakdb")

    def initLogging(self):
        # Open a logging file
        self.logfilename = time.strftime("%y.%m.%d") + "_" + time.strftime("%H:%M:%S") + ".log"
        self.logfile = open(self.logfilename, "a")
        self.logfilecount = 0

    def loadSeenDB(self):
        try:
            seendb = open('seendb.pkl', 'rb')
        except IOError:
            cprint(RED, 'Unable to open \'seendb.pkl\'\n')
            return
        self.seen = pickle.load(pkl_file)
        seendb.close()

    def signalHandler(self, signal, frame):
        self.Quit()

    def Quit(self):
        self.mc.saveDatabase()
        self.logfile.close()
        seendb = open('seendb.pkl', 'wb')
        # Pickle dictionary using protocol 0.
        pickle.dump(self.seen, seendb)
        seendb.close()
        sys.exit()

    def elapsedTime(self, ss):
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
                        cprint(YELLOW, "+o " + nick + "\n")
                        self.irc.send('MODE '+ chan +' +o ' + nick + '\r\n')
                        self.ops[ chan ].append(nick)
            return True

        if words[0] == "seen" and len(words) == 2:
            nick = words[1]
            if self.seen.has_key(nick):
                seen_msg = nick + " was last seen in "
                seen_msg = seen_msg + self.seen[nick][0] + " " 
                last_seen = self.seen[nick][1] # in seconds since epoch
                since = self.elapsedTime( time.time() - last_seen )
                seen_msg = seen_msg + since
                seen_msg = seen_msg + " saying '" + self.seen[nick][2] + "'"
                self.privmsg( msg["speaking_to"], seen_msg )
            return True

        return False

    def reply(self, msg):
        text =  msg["text"]
        text = string.strip(text, ",./?><;:[]{}\'\"!@#$%^&*()_-+=")
        words = text.split()

        if len(words) < 2:
            return

        # Use a random bigram of the input message as a seed for the Markov chain
        max_index = min( 6, len(words)-1)
        index = random.randint( 1, max_index)
        seed = [ words[index-1], words[index]]
        leading_words = string.join(words[0:index+1])

        # generate a response
        response = [""]
        self.mc.respond( seed, response )
        reply = leading_words + " " + response[0]
        #print string.join(seed) + " :: " + reply
        if response[0] == "":
            cprint(PLAIN, time.strftime("%H:%M:%S") + " : EMPTY REPLY\n")
            self.logfile.write(self.NICK + " " + time.strftime("%H:%M:%S") + " : EMPTY REPLY")
        else:
            self.privmsg(msg["speaking_to"], reply)
            self.logfile.write(self.NICK + " " + time.strftime("%H:%M:%S") + " : " + reply)

    def makeTinyUrl(self, url):
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
        cprint(CYAN, msg["speaker"] + " ")
        cprint(PLAIN, time.strftime("%H:%M:%S") + " : ")
        cprint(BLUE, msg["text"] + "\n")
        self.logfile.write(msg["speaker"] + " " + time.strftime("%H:%M:%S") + " : " + msg["text"] + "\n")
        self.logfilecount = self.logfilecount + 1

        doRemember = True
        doReply = (random.random() <= msg["p_reply"])

        # If a user has issued a command, we don't reply to it
        if self.handleCommands(msg):
            doReply = False
            doRemember = False

        # and possibly reply
        if doReply:
           self.reply(msg)
        #else:
        #    cprint(BG_GREEN, "No reply\n")

        # add the phrase to the markov database
        if doRemember:
            self.mc.addLine( msg["text"] )

        # if we've exceeded our log file size limit, close it and open a new one 
        if self.logfilecount > self.LOGFILE_MAX_LINES:
            self.logfile.close()
            self.logfilename = time.strftime("%y.%m.%d") + "_" + time.strftime("%H:%M:%S") + ".log"
            self.logfile = open( self.logfilename, "a" )
            self.logfilecount = 0


    def parsePrivateOwnerMessage( self, msg ):
        # The owner can issue commands to the bot, via strictly
        # constructed private messages
        words = msg["text"].split()

        # simple testing
        if len(words) == 1 and words[0] == 'ping':
            self.irc.send('PRIVMSG '+ msg["speaker"] +' :' + 'pong\r\n')
            return

        # set internal variables
        elif len(words) == 3 and  words[0] == "set":
            # set reply probability
            if words[1] == "p_reply":
                cprint(CYAN, msg["speaker"] + " ")
                cprint(PLAIN, time.strftime("%H:%M:%S") + " : ")
                cprint(RED, "SET P_REPLY " + words[2] + "\n")
                self.P_REPLY = float(words[2])
            else:
                self.dunno()
            return

        elif len(words) == 2 and  words[0] == "get":
            # set reply probability
            if words[1] == "p_reply":
                cprint(CYAN, msg["speaker"] + " ")
                cprint(PLAIN, time.strftime("%H:%M:%S") + " : ")
                cprint(RED, "GET P_REPLY " + str(self.P_REPLY) + "\n")

                self.irc.send('PRIVMSG '+ msg["speaker"] +' :' + str(self.P_REPLY) + '\r\n')
                return

        # leave a channel
        elif len(words) == 2 and words[0] == 'leave':
            channel = str(words[1]);
            if channel[0] != '#':
                channel = '#' + channel

            cprint(CYAN, msg["speaker"] + " ")
            cprint(PLAIN, time.strftime("%H:%M:%S") + " : ")
            cprint(RED, "PART " + channel + "\n")
            self.irc.send('PART ' + channel + '\r\n')
            return

        # join a channel
        elif len(words) == 2 and words[0] == 'join':
            channel = str(words[1]);
            if channel[0] != '#':
                channel = '#' + channel
            
            cprint(CYAN, msg["speaker"] + " ")
            cprint(PLAIN, time.strftime("%H:%M:%S") + " : ")
            cprint(RED, "JOIN " + channel + "\n")
            self.irc.send('JOIN ' + channel + '\r\n')
            return

        # quit
        elif len(words) == 1 and (words[0] == 'quit' or words[0] == 'exit'):
            cprint(CYAN, msg["speaker"] + " ")
            cprint(PLAIN, time.strftime("%H:%M:%S") + " : ")
            cprint(RED, "QUIT" + "\n")
            self.Quit()

        # if we've hit no special commands, parse this message like it was public
        self.parsePublicMessage(msg)
        
    def preprocessText(self, text):
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
            "p_reply"       : self.P_REPLY                 # probably of responding
            }

        if msg["privmsg"] != 'PRIVMSG':
            return
      
        if msg["speaking_to"][0] == "#":
            self.seen[ msg["speaker"] ] = [ msg["speaking_to"], time.time(), msg["text"] ]
 
        self.determineWhoIsBeingAddressed( msg )

        if msg["speaking_to"] == self.NICK and msg["speaker"] in self.OWNERS: 
            self.parsePrivateOwnerMessage( msg )
            return    
        elif msg["speaking_to"] != self.NICK:
            self.parsePublicMessage( msg )
            return
        return

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
        self.initMarkovChain()
        self.initLogging()
        self.loadSeenDB()
        self.joinIrc()

        # Loop forever, parsing input text
        while 1:
            self.readbuffer = self.readbuffer + self.irc.recv(1024)
            temp = string.split(self.readbuffer, "\n")
            self.readbuffer = temp.pop( )

            for line in temp:
                # strip whitespace and split into words
                words = string.rstrip(line)
                words = string.split(words)

                if words[0]=="PING":
                    self.pong(words[1])
                    # flush logfile
                    self.logfile.flush()

                elif line.find('PRIVMSG')!=-1: #Call a parsing function
                    self.parsePrivMessage(line)
                    
                elif words[1] == "MODE":
                    self.parseModeMessage(words)


#####

if __name__ == "__main__":
    bot = Bot()
    bot.main()
