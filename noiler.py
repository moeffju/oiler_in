#!/usr/bin/env python
# -*- coding:utf-8 -*-

import config

import threading
import tweepy

# for the title tag extraction
import requests
import html5lib
import elementtree

from noilib.helpers import *
from noilib.connection import IRCConnection
from random import randint
from time import sleep
from datetime import datetime, timedelta
from fnmatch import fnmatchcase
from sys import stdout, stderr

def log(s):
	stdout.write("--- " + str(s) + "\n")

def log_error(s):
	stderr.write("!!! ERROR: " + str(s) + "\n")

class Quotes:
	def __init__(self, target):
		self.fn = './quotes_' + target + '.txt'
		self.f = open(self.fn, 'a+')
		self.f.seek(0)
		self.quotes = self.f.read().splitlines()

	def save(self):
		self.f.seek(0)
		self.f.truncate()
		self.f.write('\n'.join(self.quotes))
		self.f.flush()

	def add(self, quote):
		self.quotes.append(quote)

	def delete(self, idx):
		try:
			if idx < 1 or idx > self.count():
				raise IndexError
			del self.quotes[idx - 1]
			return True
		except IndexError:
			return False

	def count(self):
		return len(self.quotes)

	def show(self, idx):
		"""1-indexed for hu-mons!"""
		if idx < 1 or idx > self.count():
			raise IndexError
		return self.quotes[idx - 1].rstrip("\r\n")


class Ignores:
	def __init__(self, target):
		self.fn = './ignored_' + target + '.txt'
		self.f = open(self.fn, 'a+')
		self.f.seek(0)
		self.ignored = self.f.read().splitlines()

	def save(self):
		self.f.seek(0)
		self.f.truncate()
		self.f.write('\n'.join(self.ignored))
		self.f.flush()

	def match(self, usermask):
		return (self.index(usermask) is not None)

	def index(self, usermask):
		try:
			return (i for i,mask in enumerate(self.ignored) if fnmatchcase(usermask, mask)).next()
		except StopIteration:
			return None

	def add(self, usermask):
		self.ignored.append(usermask)

	def delete(self, idx):
		del self.ignored[idx]

	def delete_mask(self, usermask):
		x = self.index(usermask)
		if x:
			self.delete(x)
			return True
		return False


def twitter(irc, nick, userhost, target, cmd, args, what):
	# print '--- twitter <%s!%s/%s> (%s, %s) (%s)' % (nick, userhost, target, cmd, args, what)

	if args == None:
		irc.notice(target, 'Bitte was?')
		return

	f = None
	a = []
	k = {}
	args = args.split(' ')
	success = 'Tweet ist raus.'

	m = re.match(r"(?:https?://(?:[^.]+.)?twitter.com/(?P<username>[^/]*)/status(?:es)?/)?(?P<status_id>\d+)", args[0])
	if what == 'tweet' or what == 'reply':
		f = api.update_status
		if what == 'reply':
			sucess = 'Reply ist raus.'
			try:
				if m.group('status_id'):
					k['in_reply_to_status_id'] = m.group('status_id')
					k['in_reply_to_status_id_str'] = m.group('status_id')
				if m.group('username'):
					k['in_reply_to_screen_name'] = m.group('username')
					a = '@' + m.group('username') + ' ' + ' '.join(args[1:])
				elif args[1].startswith('@'):
					k['in_reply_to_screen_name'] = args[1]
					a = ' '.join(args[1:])
				else:
					irc.notice(target, 'Entweder brauche ich eine URL mit nem Username, oder du musst den User selbst @-mentionen.')
					return False
			except AttributeError:
				irc.notice(target, 'Ich brauche eine Tweet-URL oder die Tweet-ID + @username.')
				return False
		else:
			success = 'Tweet ist raus.'
			a = ' '.join(args)
	elif what == 'rt' or what == 'fav':
		if m:
			if what == 'fav':
				success = 'Fav ist raus.'
				f = api.create_favorite
				a = m.group('status_id')
			elif what == 'rt':
				success = 'Retweet ist raus.'
				f = api.retweet
				a = m.group('status_id')
		else:
			irc.notice(target, 'Vielleicht mal eine Twitter-URL oder Tweet-ID mitgeben, wa?')
			return False
	else:
		return False

	def sub():
		try:
			aa = [a]
			f(*aa, **k)
			irc.notice(target, success)
		except tweepy.TweepError as e:
			irc.notice(target, 'Das hat nicht geklappt: %s' % e.reason)

	vetoable(irc, target, sub)
	return True

def vetoable(irc, target, f):
	global veto_timer

	# print 'vetoable f=%s' % (f)
	if veto_timer and veto_timer.is_alive():
		irc.notice(target, 'Äh, warte kurz!')
	else:
		irc.notice(target, '%d Sekunden Vetophase läuft.' % (config.vetotime,))
		veto_timer = threading.Timer(config.vetotime, f)
		veto_timer.start()

def veto(irc, nick, userhost, target, cmd, args):
	global veto_timer
	
	# print '--- veto <%s!%s/%s> (%s, %s)' % (nick, userhost, target, cmd, args)

	if veto_timer and veto_timer.is_alive():
		veto_timer.cancel()
		irc.notice(target, 'Anzeige ist raus!')
	else:
		irc.notice(target, 'Läuft doch jar nüscht.')
	return False

def info(irc, nick, userhost, target, cmd, args):
	irc.notice(target, 'Quote(s) und mehr durch '+config.nick+'!')
	return True

def help(irc, nick, userhost, target, cmd, args):
	if is_channel(target):
		# show only commands that trigger from channel
		flag = CMD_CHANNEL
	else:
		# show everything
		flag = CMD_QUERY | CMD_CHANNEL
		target = nick

	irc.notice(target, 'Mögliche Befehle:')
	cmd_list = []
	for cmd in msg_triggers:
		if cmd[1] and cmd[2] & flag == flag:
			if type(cmd[1]) == list:
				x = ' oder '.join(cmd[0]) + ' ' + cmd[1][0]
				y = cmd[1][1]
			else:
				x = ' oder '.join(cmd[0])
				y = cmd[1]
			cmd_list.append(x)
	irc.notice(target, ', '.join(cmd_list))

	return True

def quote_add(irc, nick, userhost, target, cmd, args):
	# print '--- quote_add <%s!%s/%s> %s: (%s)' % (nick, userhost, target, cmd, args)
	q = Quotes(target)
	q.add(args)
	q.save()
	irc.notice(target, "Quote #%d hinzugefügt." % q.count())
	return True

def quote_del(irc, nick, userhost, target, cmd, args):
	# print '--- quote_del <%s!%s/%s> %s: (%s)' % (nick, userhost, target, cmd, args)
	q = Quotes(target)
	q.delete(int(args))
	q.save()
	irc.notice(target, "Quote #%d gelöscht." % int(args))
	return True

def quote_show(irc, nick, userhost, target, cmd, args):
	# print '--- quote_show <%s!%s/%s> %s: (%s)' % (nick, userhost, target, cmd, args)
	q = Quotes(target)
	try:
		if args:
			try:
				r = int(args)
				irc.notice(target, "Quote #%d: %s" % (r, q.show(r)))
			except ValueError:
				irc.notice(target, "Lernu Ganzzahl Style! (!quote 1234)")
		else:
			r = randint(0, q.count()) + 1
			irc.notice(target, "Quote #%d: %s" % (r, q.show(r)))
		return True
	except IndexError:
		irc.notice(target, "Diese Quote gibt es nicht. Es gibt %d Quotes." % q.count())
		return True

def time(irc, nick, userhost, target, cmd, args):
	if not is_channel(target):
		target = nick
	irc.notice(target, datetime.now().strftime("%Y-%m-%d %H:%M"))
	return True

def ignore(irc, nick, userhost, target, cmd, args):
	# print '--- ignore <%s!%s/%s> %s: (%s)' % (nick, userhost, target, cmd, args)
	try:
		usermask, channel, pw = args.split()
		if not '!' in usermask:
			usermask += '!*@*'
		if not '@' in usermask:
			usermask += '@*'
		if pw == config.ownerpw:
			ignores = Ignores(channel)
			ignores.add(usermask)
			ignores.save()
			irc.notice(nick, "Added %s to ignore list for %s." % (usermask, channel))
			return True
		else:
			irc.notice(nick, "Nice try.")
		return False
	except ValueError, AttributeError:
		irc.notice(nick, "Süntaks, kennst du es? Fersuche !help.")
		return True

def check_ignored(target, usermask):
	ignores = Ignores(target)
	return ignores.match(usermask)

def ignored(irc, nick, userhost, target, cmd, args):
	# print '--- ignored <%s!%s/%s> %s: (%s)' % (nick, userhost, target, cmd, args)
	try:
		usermask, channel, pw = args.split()
		if not '!' in usermask:
			usermask += '!*@*'
		if not '@' in usermask:
			usermask += '@*'
		if pw == config.ownerpw:
			if check_ignored(channel, usermask):
				irc.notice(nick, "Yup, %s is ignored in %s." % (usermask, channel))
			else:
				irc.notice(nick, "Nope, %s is not ignored in %s." % (usermask, channel))
			return True
		else:
			irc.notice(nick, "Nice try.")
		return False
	except ValueError:
		irc.notice(nick, "Süntaks, kennst du es? Fersuche !help.")
		return True

def quit(irc, nick, userhost, target, cmd, args):
	if args == config.ownerpw:
		irc.send('QUIT', ':Sit. Stay. Good girl.')
		raise SystemExit
		return True

def handle_privmsg(irc, nick, userhost, target, message):
	if check_ignored(target, nick + '!' + userhost):
		# silently ignore
		log('### ignored command from %s!%s' % (nick, userhost))
		return True

	if is_channel(target):
		m = re.search(r"https?://(?:[^.]+.)?twitter.com/(?P<username>[^/]*)/status(?:es)?/(?P<status_id>\d+)", message)
		if m:
			try:
				tweet = api.get_status(m.group('status_id'))
				irc.notice(target, ("Tweet von @%s: %s" % (tweet.user.screen_name, unescape(tweet.text).replace('\n', ' '))).encode('utf-8'))
			except Exception as e:
				irc.notice(target, 'Das hat nicht geklappt: %s' % e)
		else:
			m = re.search(r"((?<=\()https?://(?:[A-Za-z0-9\.\-_~:/\?#\[\]@!\$&'\(\)\*\+,;=]|%[A-Fa-f0-9]{2})+(?=\)))|(?:https?://(?:[A-Za-z0-9\.\-_~:/\?#\[\]@!\$&'\(\)\*\+,;=]|%[A-Fa-f0-9]{2})+)", message)
			if m:
				def lookup_url(url, irc):
					try:
						r = requests.head(url, timeout=3, verify=False)
						if any(r.headers['content-type'].split(';')[0] in s for s in ['text/html', 'text/xml', 'application/xhtml+xml']):
							r = requests.get(url, timeout=3, verify=False)
							doc = html5lib.parse(r.content, treebuilder="etree", namespaceHTMLElements=False)
							title = doc.find('.//title').text.strip()
							title = ' '.join(title.split())
							irc.notice(target, ("%s <%s>" % (title, url)).encode('utf-8'))
						else:
							log_error('Ich kann nicht mit in zu "%s"-Dokumenten.' % r.headers['content-type'])
					except (AttributeError, requests.exceptions.RequestException) as e:
						log_error("%s: %s" % (type(e).__name__, e))
					except Exception as e:
						log_error("%s: %s" % (type(e).__name__, e))
						irc.notice(target, 'Fehler bei <%s>: %s: %s' % (url, type(e).__name__, e))

				t = threading.Thread(target=lookup_url, args=(m.group(0), irc))
				t.daemon = True
				t.start()

	try:
		cmd, args = message.split(' ', 1)
	except ValueError:
		cmd, args = message, None
	cmd = cmd.lower()

	if is_channel(target):
		flag = CMD_CHANNEL
	else:
		flag = CMD_QUERY

	for trigger in msg_triggers:
		if trigger[2] & flag == flag:
			if cmd in trigger[0]:
				splatargs = trigger[4] if len(trigger) > 4 else []
				kwargs = trigger[5] if len(trigger) > 5 else {}
				if trigger[3](irc, nick, userhost, target, cmd, args, *splatargs, **kwargs):
					return True

	return False

def handle_kick(irc, nick, userhost, target, victim):
	irc.send('JOIN', target)
	return True

def handle_quit(irc, nick, userhost, target, victim):
	irc.reconnect()
	return True

def handle_err_nicknameinuse(irc, nick, userhost, target, victim):
	irc.send('NICK', config.altnick)
	defer(30, irc.send, 'NICK', config.nick)
	return True

def handle_unknown(irc, prefix, command, args):
	# print '@@@ UNKNOWN: %s %s %s' % (prefix, command, args)
	return False

def defer(delay, fun, *args, **kwargs):
	t = threading.Timer(delay, fun, args=args, kwargs=kwargs)
	t.daemon = True
	t.start()
	return t

CMD_CHANNEL = 1
CMD_QUERY = 2

msg_triggers = [
	# triggers, CMD_CHANNEL | CMD_QUERY, func, *args, **kwargs
	[['!info'], None, CMD_CHANNEL, info],
	[['!help'], 'Diese Liste', CMD_CHANNEL | CMD_QUERY, help],
	# Twitter
	[['!tweet', '!twitter'], ['<Text>', 'Twittert <Text> als '+config.twitter_account], CMD_CHANNEL, twitter, ['tweet']],
	[['!reply', '!re'], ['<Tweet-URL oder ID> <Text>', 'Twittert <Text> als Antwort auf den angegebenen Tweet'], CMD_CHANNEL, twitter, ['reply']],
	[['!fav', '!favorite', '!favourite'], ['<Tweet-URL oder ID>', 'Favt den angegebenen Tweet'], CMD_CHANNEL, twitter, ['fav']],
	[['!rt', '!retweet'], ['<Tweet-URL oder ID>', 'Retweetet den angegebenen Tweet'], CMD_CHANNEL, twitter, ['rt']],
	[['!veto'], 'Stoppt die aktuelle Twitter-Aktion', CMD_CHANNEL, veto],
	# Quotes
	[['!addquote'], ['<Text>', 'Text als Quote hinzufügen'], CMD_CHANNEL, quote_add],
	[['!quote'], 'Zufällige Quote anzeigen', CMD_CHANNEL, quote_show],
	[['!quote'], ['<Nummer>', 'Bestimmte Quote anzeigen'], CMD_CHANNEL, quote_show],
	#[['!delquote'], ['<Nummer>', 'Quote löschen'], CMD_CHANNEL, quote_del],
	# Tools
	[['!time'], 'Systemzeit ausgeben', CMD_CHANNEL | CMD_QUERY, time],
	[['!ignore'], ['<Usermask> <Channel> <Owner-Passwort>', 'Usermask von Botbenutzung ausschließen'], CMD_QUERY, ignore],
	[['!ignored'], ['<Usermask> <Channel> <Owner-Passwort>', 'Check if <usermask> is ignored in <target>'], CMD_QUERY, ignored],
	[['!quit'], ['<Owner-Passwort>', 'Raus!'], CMD_QUERY, quit],
]

if not hasattr(config, 'altnick'):
	config.altnick = config.nick + '_'

veto_timer = None

auth = tweepy.OAuthHandler(config.consumer_key, config.consumer_secret)
auth.set_access_token(config.access_token, config.access_token_secret)

api = tweepy.API(auth)

def twitter_mentions_thread(api, irc):
	while True:
		try:
			sleep(30)
			for tweet in api.mentions():
				if tweet.created_at > datetime.utcnow() - timedelta(seconds=30):
					irc.notice(config.chan, ("Tweet %s von @%s: %s" % (tweet.id_str, tweet.user.screen_name, unescape(tweet.text).replace('\n', ' '))).encode('utf-8'))
		except Exception, e:
			log_error("!!! Exception in twitter_mentions_thread: %s" % e)

# Twitter init
log("Verifying Twitter credentials...")
user = api.verify_credentials()
if user:
	log('Authenticated with Twitter as @%s' % user.screen_name)
else:
	log('Could not verify credientials. Check your Twitter credentials in config.py!')
	sys.exit(1)

# main
irc = IRCConnection(server=config.server, port=config.port, ssl=config.ssl, password=config.password, nick=config.nick, realname=config.realname, user=config.user, channels=[config.chan])
irc.on('privmsg', handle_privmsg)
irc.on('kick', handle_kick)
irc.on('quit', handle_quit)
irc.on('ERR_NICKNAMEINUSE', handle_err_nicknameinuse)
#irc.on('*', handle_unknown)

t = threading.Thread(target=twitter_mentions_thread, args=(api, irc))
t.daemon = True
t.start()

irc.connect()
