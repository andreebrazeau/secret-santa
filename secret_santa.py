# -*- coding: utf-8 -*-
import yaml
# sudo pip install pyyaml
import re
import random
import smtplib
import datetime
import pytz
import time
import socket
import sys
import getopt
import os
import requests

from email.header import Header
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

help_message = '''
To use, fill out config.yml with your own participants. You can also specify 
DONT-PAIR so that people don't get assigned their significant other.

You'll also need to specify your mail server settings. An example is provided
for routing mail through gmail.

For more information, see README.
'''

REQRD = (
    'SMTP_SERVER', 
    'SMTP_PORT', 
    'USERNAME', 
    'PASSWORD', 
    'TIMEZONE', 
    'PARTICIPANTS', 
    'DONT-PAIR', 
    'FROM', 
    'SUBJECT', 
    'MESSAGE',
)

HEADER = """Date: {date}
Content-Type: text/plain; charset="utf-8"
Message-Id: {message_id}
From: {frm}
To: {to}
Subject: {subject}
        
"""

CONFIG_PATH = os.path.join(os.path.dirname(__file__), 'config.yml')

global CONFIG
global SERVER
SERVER = None


class Person:
    def __init__(self, name, email, invalid_matches):
        self.name = name
        self.email = email
        self.invalid_matches = invalid_matches
    
    def __str__(self):
        return u"{} <{}>".format(self.name, self.email)


class Pair:
    def __init__(self, giver, reciever):
        self.giver = giver
        self.reciever = reciever
    
    def couple(self):
        return u"{} ---> {}".format(self.giver.name, self.reciever.name)


def parse_yaml(yaml_path=CONFIG_PATH):
    return yaml.load(open(yaml_path))    


def choose_reciever(giver, recievers):
    choice = random.choice(recievers)
    if choice.name in giver.invalid_matches or giver.name == choice.name:
        if len(recievers) is 1:
            raise Exception('Only one reciever left, try again')
        return choose_reciever(giver, recievers)
    else:
        return choice


def create_pairs(g, r):
    givers = g[:]
    recievers = r[:]
    pairs = []
    for giver in givers:
        try:
            reciever = choose_reciever(giver, recievers)
            recievers.remove(reciever)
            pairs.append(Pair(giver, reciever))
        except:
            return create_pairs(g, r)
    return pairs


def containsnonasciicharacters(str):
    return not all(ord(c) < 128 for c in str)


def addheader(message, headername, headervalue):
    if containsnonasciicharacters(headervalue):
        h = Header(headervalue, 'utf-8')
        message[headername] = h
    else:
        message[headername] = headervalue
    return message


def send_email(pair):

    zone = pytz.timezone(CONFIG['TIMEZONE'])
    now = zone.localize(datetime.datetime.now())
    date = now.strftime('%a, %d %b %Y %T %Z') # Sun, 21 Dec 2008 06:25:23 +0000
    message_id = u'<{}@{}>'.format(str(time.time())+str(random.random()), socket.gethostname())
    frm = CONFIG['FROM']
    to = pair.giver.email
    subject = CONFIG['SUBJECT'].format(santa=pair.giver.name, santee=pair.reciever.name)
    body = CONFIG['MESSAGE'].format(
        santa=pair.giver.name,
        santee=pair.reciever.name,
    )

    if CONFIG['EMAILER'] == "mailgun":
        resp = requests.post(
            u"{}/messages".format(CONFIG['MAILGUN_API_BASE']),
            auth=("api", CONFIG['MAILGUN_API_KEY']),
            data={"from": "Pere Noel <santa@{}>".format(CONFIG['MAILGUN_SUBDOMAIN']),
                  "to": u"{name} <{email}>".format(name=pair.giver.name, email=pair.giver.email),
                  "subject": subject,
                  "text": body})
        print u"Emailed {} <{}>".format(pair.giver.name, to)
        return resp

    elif CONFIG['EMAILER'] == "smtp":

        msg = MIMEMultipart('alternative')
        msg = addheader(msg, 'Subject', subject)
        msg['From'] = frm

        if(containsnonasciicharacters(body)):
            plaintext = MIMEText(body.encode('utf-8'),'plain','utf-8')
        else:
            plaintext = MIMEText(body,'plain')

        msg.attach(plaintext)

        global SERVER

        if not SERVER:
            SERVER = smtplib.SMTP(CONFIG['SMTP_SERVER'], CONFIG['SMTP_PORT'])
            SERVER.starttls()
            SERVER.login(CONFIG['USERNAME'], CONFIG['PASSWORD'])
        result = SERVER.sendmail(frm, [to], msg.as_string())
        print u"Emailed {} <{}>".format(pair.giver.name, to)

class Usage(Exception):
    def __init__(self, msg):
        self.msg = msg


def main(argv=None):
    if argv is None:
        argv = sys.argv
    try:
        try:
            opts, args = getopt.getopt(argv[1:], "shc", ["send", "help"])
        except getopt.error, msg:
            raise Usage(msg)
    
        # option processing
        send = False
        for option, value in opts:
            if option in ("-s", "--send"):
                send = True
            if option in ("-h", "--help"):
                raise Usage(help_message)

        global CONFIG
        CONFIG = parse_yaml()

        for key in REQRD:
            if key not in CONFIG.keys():
                raise Exception(
                    'Required parameter {} not in yaml config file!'.format(key,))

        participants = CONFIG['PARTICIPANTS']
        dont_pair = CONFIG['DONT-PAIR']

        if len(participants) < 2:
            raise Exception('Not enough participants specified.')
        
        givers = []
        for person in participants:
            name, email = re.match(r'([^<]*)<([^>]*)>', person).groups()
            name = name.strip()
            invalid_matches = []
            for pair in dont_pair:
                names = [n.strip() for n in pair.split(',')]
                if name in names:
                    # is part of this pair
                    for member in names:
                        if name != member:
                            invalid_matches.append(member)
            person = Person(name, email, invalid_matches)
            givers.append(person)
        
        recievers = givers[:]
        pairs = create_pairs(givers, recievers)
        if not send:
            print u"""
Test pairings:
                
{}
                
To send out emails with new pairings,
call with the --send argument:

    $ python secret_santa.py --send
            
            """.format("\n".join([p.couple() for p in pairs]))

        for pair in pairs:
            if send:
                send_email(pair)

        if send and CONFIG['EMAILER'] == "smtp":
            SERVER.quit()
        
    except Usage, err:
        print >> sys.stderr, sys.argv[0].split("/")[-1] + ": " + str(err.msg)
        print >> sys.stderr, "\t for help use --help"
        return 2


if __name__ == "__main__":
    sys.exit(main())