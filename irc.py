import errno
import logging
import socket
import string

import logger
from colortext import *

class ConnectionClosedException(Exception):
    def __init__(self, *args, **kwargs):
        Exception.__init__(self, *args, **kwargs)


class Irc:
    def __init__(self, host, port, nick, ident, realname):
        self.readbuffer = '' # store all the messages from server

        self._who = {} # lists of who is in what channels
        self._ops = {} # lists of ops is in what channels

        self.irc = socket.socket()
        self.irc.connect((host, port))
        self.send("NICK %s\r\n" % nick)
        self.send("USER %s %s bla :%s\r\n" % (ident, host, realname))

        # This is a hack, but how should I detect when I've successfully joined
        # a channel?
        self._eatLinesUntilText('End of /MOTD command')

    def __del__(self):
        if self.irc:
            self.irc.close()

    def _eatLinesUntilText(self, stopText):
        # Loop until we encounter the passed in 'stopText'
        while 1:
            temp = self.readlines()

            for line in temp:
                logging.info(YELLOW + line)
                words = string.rstrip(line)
                words = string.split(words)

                # TODO: pull this out into a method to check for pings
                if len(words) > 0 and (words[0] == "PING"):
                    self.pong(words[1])

                # This is a hack, but how should I detect when to join
                # a channel?
                if line.find(stopText) != -1:
                    return

    def _eatLinesUntilEndOfNames(self, population, operators):
        # get the current population of the channel
        # :magnet.llarian.net 353 gravy = #test333 :gravy @nrrd
        # :magnet.llarian.net 366 gravy #test333 :

        while 1:
            temp = self.readlines()
            for line in temp:
                logging.info(YELLOW + line)
                words = string.rstrip(line)
                words = string.split(words)

                if(words[0] == "PING"):
                    self.pong(words[1])

                # This is a hack, but how should I detect when we're
                # done joining?
                elif line.find('End of /NAMES list') != -1:
                    return

                elif len(words) > 4:
                    # get the current population of the channel
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

                        population.append(nick)
                        if op is True:
                            operators.append(nick)

    def join(self, channel):
        channel = str(channel)
        if channel[0] != '#':
            channel = '#' + channel
        self.send('JOIN ' + channel + '\n')

        population = []
        operators = []
        self._eatLinesUntilEndOfNames(population, operators)
        self._who[channel] = population
        self._ops[channel] = operators

    def part(self, channel):
        channel = str(channel)
        if channel[0] != '#':
            channel = '#' + channel
        self.send('PART ' + channel + '\r\n')

    def readlines(self):
        try:
            recv = self.irc.recv(1024)
            if len(recv) == 0:
                raise ConnectionClosedException()

            self.readbuffer = self.readbuffer + recv
        except socket.error as (code, msg):
            if code != errno.EINTR:
                raise

        temp = string.split(self.readbuffer, "\n")
        self.readbuffer = temp.pop()
        return temp

    def _uniquify(self, seq):
        # not order preserving
        s = {}
        map(s.__setitem__, seq, [])
        return s.keys()

    def isop(self, nick, channel=None):
        if channel:
            if nick in self._ops[channel]:
                return True
        else:
            for channel in self._ops:
                if nick in self._ops[channel]:
                    return True

        return False

    def addop(self, chan, nick):
        self._ops[chan].append(nick)
        self._ops[chan] = self._uniquify(self._ops[chan])

    def rmop(self, chan, nick):
        self._ops[chan].remove(nick)

    # TODO: take a channel arg?
    def makeop(self, nick):
        for chan in self._who:
            for who in self._who[chan]:
                if nick == who:
                    logging.info(YELLOW + '+o ' + nick)
                    self.send('MODE ' + chan + ' +o ' + nick + '\r\n')
                    self.addop(chan, nick)

    # Irc communication functions
    def privmsg(self, speaking_to, text):
        logging.debug(PURPLE + speaking_to + PLAIN + " : " + BLUE + text)
        self.send('PRIVMSG '+ speaking_to +' :' + text + '\r\n')

    def pong(self, server):
        #cprint(GREEN, "PONG " + server + "\n")
        self.send("PONG %s\r\n" % server)

    def send(self, msg):
        self.irc.sendall(msg)
