#!/usr/bin/env python
# -*- coding:utf-8 -*-

from noilib.parse import parse_irc_line, parse_modes, parse_prefix
from sys import stdout, stderr

import sys
import socket
import ssl

class IRCConnection:
  """Connects to an IRC server and allows you to send and receive messages."""

  def __init__(self, server='localhost', port=6667, ssl=False, password=None, nick=None, realname=None, user=None, channels=[]):
    self.server = server
    self.port = port
    self.ssl = ssl
    self.password = password
    self.nick = nick
    self.realname = realname
    self.user = user
    self.channels = channels
    self.callbacks = {}

    self.ended = False

    self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

  def log_send(self, line):
    stderr.write(" -> %s\n" % line)

  def log_recv(self, line):
    stderr.write("<-  %s\n" % line)

  def log_debug(self, line):
    #stderr.write("??? %s\n" % line)
    pass

  def log_error(self, line):
    stderr.write("!!! %s\n" % line)

  def end(self):
    self.ended = True

  def sendline(self, line):
    self.log_send(line)
    self.socket.send(line + "\r\n")

  def send(self, *args):
    self.sendline(' '.join([str(x) for x in args]))

  def recv(self, line):
    self.log_recv(line)

  def on(self, command, func):
    if not command in self.callbacks:
      self.callbacks[command.upper()] = []
    self.callbacks[command.upper()].append(func)

  def dispatch(self, prefix, cmd, args, **kwargs):
    lookup_cmd = cmd
    if 'fallback' in kwargs:
      lookup_cmd = '*'

    if prefix:
      nick, userhost = parse_prefix(prefix)
    else:
      nick, userhost = (None, None)

    #self.log_debug('dispatch(prefix="%s", cmd="%s", lookup_cmd="%s")' % (prefix, cmd, lookup_cmd))

    if lookup_cmd in self.callbacks:
      if cmd == 'PRIVMSG' or cmd == 'KICK':
        fargs = [nick, userhost, args[0], ' '.join(args[1:])]

      elif cmd == 'JOIN' or cmd == 'PART':
        fargs = [nick, userhost, args[0]]

      elif cmd == 'MODE':
        modes = parse_modes(args[1:])
        fargs = [nick, userhost, args[0], modes]

      else:
        fargs = [nick, userhost, cmd, args]

      if lookup_cmd == '*':
        fargs = [prefix, cmd, args]

      fargs.insert(0, self)

      for func in self.callbacks[lookup_cmd]:
        self.log_debug('func=%s fargs=%s' % (func.__name__, repr(fargs)))
        if func(*fargs):
          return True
    return False

  def join_channels(self, *args):
    for channel in self.channels:
      self.join(channel)

  def update_nick(self, irc, user, userhost, event, args):
    self.nick = args[0]

  def connect(self):
    try:
      self.socket.settimeout(300)
      try:
        self.socket.connect((self.server, self.port))
        if self.ssl:
          self.socket = ssl.wrap_socket(self.socket)

        # TODO error handling :o
        if self.password:
          self.send('PASS', self.password)
        self.send('NICK', self.nick)
        # 12 = +iw
        self.send('USER', self.user, '12', '*', ':' + self.realname)
        self.on('RPL_WELCOME', self.join_channels)
        self.on('RPL_WELCOME', self.update_nick)
        self.on('NICK', self.update_nick)
      except socket.timeout:
        self.log_error("Timeout connecting. Check your config and internet connection and try again.")
        sys.exit(1)

      buffer = ''
      while not self.ended:
        try:
          buffer += self.socket.recv(1024)
          lines = buffer.split("\n")
          buffer = lines.pop()

          for raw in lines:
            self.recv(raw)

            (prefix, command, args) = parse_irc_line(raw)

            handled = self.dispatch(prefix, command, args)

            if not handled:
              handled &= self.dispatch(prefix, command, args, fallback=True)

            if not handled:
              if command == 'PING':
                self.send('PONG', ':' + args[0])

        except KeyboardInterrupt:
          self.log_error("Caught keyboard interrupt, quitting...")
          sys.exit(0)
    except socket.timeout as e:
      self.log_error("Timeout (%s), reconnecting..." % e)
      self.reconnect()
    except socket.error as e:
      self.log_error("Socket error (%s), reconnecting..." % e)
      self.reconnect()
    finally:
      self.socket.close()

  def reconnect(self):
    try:
      self.socket.close()
    except socket.error:
      pass
    finally:
      self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
      self.connect()

  def join(self, channel, password=None):
    if password:
      self.send('JOIN', channel, password)
    else:
      self.send('JOIN', channel)

  def part(self, channel):
    self.send('PART', channel)

  def privmsg(self, target, message):
    self.send('PRIVMSG', target, ':' + message)

  def notice(self, target, message):
    self.send('NOTICE', target, ':' + message)

