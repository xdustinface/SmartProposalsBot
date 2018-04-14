#!/usr/bin/env python3

import configparser
import logging
import sys, argparse, os
import json

from src import database
from src import telegram
from src import discord
from src import util
from src.socialmedia import Tweeter
from src.votingportal import SmartCashProposals

__version__ = "1.0"

def checkConfig(config,category, name):
    try:
        config.get(category,name)
    except configparser.NoSectionError as e:
        sys.exit("Config error {}".format(e))
    except configparser.NoOptionError as e:
        sys.exit("Config value error {}".format(e))

def main(argv):

    directory = os.path.dirname(os.path.realpath(__file__))
    config = configparser.SafeConfigParser()

    try:
        config.read(directory + '/smart.conf')
    except:
        sys.exit("Config file missing or corrupt.")

    checkConfig(config, 'bot','token')
    checkConfig(config, 'bot','app')
    checkConfig(config, 'general','loglevel')
    checkConfig(config, 'general','environment')

    if config.get('bot', 'app') != 'telegram' and\
       config.get('bot', 'app') != 'discord':
        sys.exit("You need to set 'telegram' or 'discord' as 'app' in the configfile.")

    # Set the log level
    level = int(config.get('general','loglevel'))

    if level < 0 or level > 4:
        sys.exit("Invalid log level.\n 1 - debug\n 2 - info\n 3 - warning\n 4 - error")

    environment = int(config.get('general','environment'))

    if environment != 1 and\
       environment != 2:
       sys.exit("Invalid environment.\n 1 - development\n 2 - production\n")

    # Enable logging

    if environment == 1: # development
        logging.basicConfig(format='%(asctime)s - scproposals_{} - %(name)s - %(levelname)s - %(message)s'.format(config.get('bot', 'app')),
                        level=level*10)
    else:# production
        logging.basicConfig(format='scproposals_{} %(name)s - %(levelname)s - %(message)s'.format(config.get('bot', 'app')),
                        level=level*10)

    notifyChannel = []
    admins = []
    password = None

    try:
        notifyChannel = config.get('optional', 'notification_channels').split(',')
    except:
        pass

    try:
        admins = config.get('optional','admins').split(',')
    except:
        pass

    try:
        password = config.get('optional','password')
    except:
        pass

    consumerKey = None
    consumerSecret = None
    accessToken = None
    accessTokenSecret = None

    tweeter = None

    try:
        consumerKey = config.get('twitter','consumer_key')
        consumerSecret = config.get('twitter','consumer_secret')
        accessToken = config.get('twitter','access_token_key')
        accessTokenSecret = config.get('twitter','access_token_secret')

        tweeter = Tweeter(consumerKey, consumerSecret, accessToken, accessTokenSecret)
    except:
        pass

    # Load the user database
    botdb = database.BotDatabase(directory + '/bot.db')

    # Load the proposals database
    proposaldb = database.ProposalDatabase(directory + '/proposals.db')

    # Create the proposal list manager
    proposals = SmartCashProposals(proposaldb)

    bot = None

    if config.get('bot', 'app') == 'telegram':
        bot = telegram.SmartProposalsBotTelegram(config.get('bot','token'), admins, password, botdb, proposals, notifyChannel)
    elif config.get('bot', 'app') == 'discord':
        bot = discord.SmartProposalsBotDiscord(config.get('bot','token'), admins, password, botdb, proposals, notifyChannel, tweeter)
    else:
        sys.exit("You need to set 'telegram' or 'discord' as 'app' in the configfile.")

    # Start and run forever!
    bot.start()

if __name__ == '__main__':
    main(sys.argv[1:])
