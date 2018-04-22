#!/usr/bin/env python3

import logging
import threading
import time
import json
import discord
import asyncio
import uuid

from fuzzywuzzy import process as fuzzy

from src import util
from src import messages
from src import commands as commandhandler

from src.socialmedia import PublishResult

logger = logging.getLogger("bot")

class SmartProposalsBotDiscord(object):

    def __init__(self, botToken, admins, password, db, proposals, notifyChannelIds, tweeter, reddit, gab):

        # Currently only used for markdown
        self.messenger = "discord"

        self.client = discord.Client()
        self.client.on_ready = self.on_ready
        self.client.on_message = self.on_message
        # Create a bot instance for async messaging
        self.token = botToken
        # Set the database of the users/watchlists
        self.database = db
        # Store and setup the proposal handler
        self.proposals = proposals
        self.proposals.proposalPublishedCB = self.proposalPublishedCB
        self.proposals.proposalUpdatedCB = self.proposalUpdatedCB
        self.proposals.proposalReminderCB = self.proposalReminderCB
        self.proposals.proposalEndedCB = self.proposalEndedCB
        self.proposals.errorCB = self.adminCB
        # Store the admin password
        self.password = password
        # Store the admin user
        self.admins = admins
        # Channels to notify new/ending proposals
        self.notifyChannelIds = notifyChannelIds
        # Twitter manager
        self.tweeter = tweeter
        # Reddit manager
        self.reddit = reddit
        # Gab manager
        self.gab = gab

    def runClient(self):

        loop = asyncio.get_event_loop()

        while True:

            try:
                loop.run_until_complete(self.client.start(self.token))
            except KeyboardInterrupt:
                logger.warning("Terminate!")
                self.stop()
                return
            except Exception as e:
                logger.error("Bot crashed?! ", e)
                self.adminCB("**Bot crashed** {}".format(str(e)))

            asyncio.run_coroutine_threadsafe(self.client.close(), loop=loop)

            time.sleep(10)

            self.client = discord.Client()

            self.client.on_ready = self.on_ready
            self.client.on_message = self.on_message

    ######
    # Starts the bot and block until the programm gets stopped.
    ######
    def start(self):
        logger.info("Start!")
        self.runClient()

    def stop(self):
        asyncio.run_coroutine_threadsafe(self.client.close(), loop=self.client.loop)
        self.proposals.stop()

    ######
    # Send a message :text to a specific user :user
    ######
    async def sendMessage(self, user, text, split = '\n'):

        logger.info("sendMessage - Chat: {}, Text: {}".format(user,text))

        parts = messages.splitMessage(text, split, 2000)

        try:
            for part in parts:
                await self.client.send_message(user, part)
        except discord.errors.Forbidden:
            logging.error('sendMessage user blocked the bot')

            # Remove the user and the assigned watchlist entires.
            self.database.removeFromWatchlist(user.id)
            self.database.deleteUser(user.id)

        except discord.errors.HTTPException as e:
            logging.error('HTTPException', exc_info=e)
        except Exception as e:
            logging.error('sendMessage', exc_info=e)
        else:
            logger.info("sendMessage - OK!")

    async def on_ready(self):

        logger.info('Logged in as')
        logger.info(self.client.user.name)
        logger.info(self.client.user.id)
        logger.info('------')

        # Initialize/Start the proposal list if its not yet
        if not self.proposals.running:
            self.proposals.start()

            # Advise the admin about the start.
            self.adminCB("**Bot started**")
        else:
            # Advise the admin about the start.
            self.adminCB("**Bot reconnected**")

    ######
    # Discord api coroutine which gets called when a new message has been
    # received in one of the channels or in a private chat with the bot.
    ######
    async def on_message(self,message):

        if message.author == self.client.user:
            # Just jump out if its the bots message.
            return

        # split the new messages by spaces
        parts = message.content.split()

        command = None
        args = None

        # If the first mention in the message is the bot itself
        # and there is a possible command in the message
        if len(message.mentions) == 1 and message.mentions[0] == self.client.user\
            and len(parts) > 1:
            command = parts[1]
            args = parts[2:]
        # If there are multiple mentions send each one (excluded the bot itself)
        # the help message.
        # Like: hey @dustinface and @whoever check out the @SmartProposals
        # The above would send @dustinface and @whoever the help message of the bot.
        elif len(message.mentions) > 1 and self.client.user in message.mentions:

            for mention in message.mentions:
                if not mention == self.client.user:

                    # Check if the user is already in the databse
                    result = commandhandler.checkUser(self, mention)

                    if result['response']:
                        await self.sendMessage(mention, result['response'])

                    if result['added']:
                        continue

                    await self.sendMessage(mention, messages.help(self.messenger))

            return
        # If there are no mentions and we are in a private chat
        elif len(message.mentions) == 0 and not isinstance(message.author, discord.Member):
            command = parts[0]
            args = parts[1:]
        # If we got mentioned but no command is available in the message just send the help
        elif len(message.mentions) and message.mentions[0] == self.client.user and\
              len(parts) == 1:
              command = 'help'
        # No message of which the bot needs to know about.
        else:
            logger.debug("on_message - jump out {}".format(self.client.user))
            return

        # If we got here call the command handler to see if there is any action required now.
        await self.commandHandler(message, command.lower(), args)

    ######
    # Handles incomming splitted messages. Check if there are commands which require
    # any action. If so it calls the related methods and sends the response to
    # the author of the command message.
    ######
    async def commandHandler(self, message, command, args):

        logger.info("commandHandler - {}, command: {}, args: {}".format(message.author, command, args))

        # Check if the user is already in the databse
        result = commandhandler.checkUser(self, message)

        if result['response']:
            await self.sendMessage(message.author, result['response'])

        if result['added'] and not isinstance(message.author, discord.Member):
            return

        # per default assume the message gets back from where it came
        receiver = message.author

        ####
        # List of available commands
        # Public = 0
        # DM-Only = 1
        # Admin only = 2
        ####
        commands = {
                    # DM Only
                    'subscribe':1,'unsubscribe':1,'add':1,'remove':1,'watchlist':1,
                    # Public
                    'help':0,'open':0,'latest':0,'passing':0,'failing':0, 'detail':0,'ending':0,
                    # Admin commands
                    'stats':2, 'broadcast':2, 'publish':2, 'new':2,
        }

        choices = fuzzy.extract(command,commands.keys(),limit=2)

        if choices[0][1] == choices[1][1] or choices[0][1] < 60:
            logger.debug('Invalid fuzzy result {}'.format(choices))
            command = 'unknown'
        else:
            command = choices[0][0]

        # If the command is DM only
        if command in commands and commands[command] == 1:

            if isinstance(message.author, discord.Member):
             await self.client.send_message(message.channel,\
             message.author.mention + ', the command `{}` is only available in private chat with me!'.format(command))

             if not added:
                 await self.client.send_message(message.author, messages.markdown('<b>Try it here with: {}<b>\n'.format(command), self.messenger))
                 await self.client.send_message(message.author, messages.help(self.messenger))

             return

        else:
            receiver = message.channel

        # If the command is admin only
        if command in commands and commands[command] == 2:

            # Admin command got fired in a public chat
            if isinstance(message.author, discord.Member):
                # Just send the unknown command message and jump out
                await self.sendMessage(receiver, (message.author.mention + ", " + commandhandler.unknown(self)))
                logger.info("Admin only, public")
                return

            def tryAdmin(message, args):
                logger.info("PW {}".format(self.password))
                if message.author.id in self.admins:
                    logger.info("yo")
                    if self.password != None:
                        logger.info("yo1")
                        if len(args) >= 1 and args[0] == self.password:
                            return True
                    else:
                        logger.info("yo2")
                        return True

                return False

            # Admin command got fired from an unauthorized user
            if tryAdmin(message, args):
                receiver = message.author
            else:
                logger.info("Admin only, other")
                # Just send the unknown command message and jump out
                await self.sendMessage(receiver, (message.author.mention + ", " + commandhandler.unknown(self)))
                return

        ### DM Only ###
        if command == 'subscribe':
            response = commandhandler.subscription(self,message,True)
            await self.sendMessage(receiver, response)
        elif command == 'unsubscribe':
            response = commandhandler.subscription(self,message,False)
            await self.sendMessage(receiver, response)
        elif command == 'add':
            response = commandhandler.add(self, message, args)
            await self.sendMessage(receiver, response)
        elif command == 'remove':
            response = commandhandler.remove(self, message, args)
            await self.sendMessage(receiver, response)
        elif command == 'watchlist':
            response = commandhandler.watchlist(self, message)
            await self.sendMessage(receiver, response)
        ### Public ###
        elif command == 'open':
            response = commandhandler.open(self)
            await self.sendMessage(receiver, response)
        elif command == 'latest':
            response = commandhandler.latest(self)
            await self.sendMessage(receiver, response)
        elif command == 'ending':
            response = commandhandler.ending(self)
            await self.sendMessage(receiver, response)
        elif command == 'detail':
            response = commandhandler.detail(self,args)
            await self.sendMessage(receiver, response)
        elif command == 'passing':
            response = commandhandler.passing(self)
            await self.sendMessage(receiver, response)
        elif command == 'failing':
            response = commandhandler.failing(self)
            await self.sendMessage(receiver, response)
        ### Admin command handler ###
        elif command == 'stats':
            response = commandhandler.stats(self)
            await self.sendMessage(receiver, response)
        elif command == 'new':
            response = commandhandler.new(self)
            await self.sendMessage(receiver, response)
        elif command == 'publish':
            result = commandhandler.publish(self, message, args)

            if result['fire']:
                response = self.publishProposal(result['author'], result['proposal'])
            else:
                response = result['message']
            await self.sendMessage(receiver, response)

        elif command == 'start':
            response = commandhandler.stats(self)
            await self.sendMessage(receiver, messages.welcome(self.messenger))
        elif command == 'broadcast':

            response = None

            if self.password:
                response = " ".join(args[1:])
            else:
                response = " ".join(args)

            for dbUser in self.database.getUsers():

                member = self.findMember(dbUser['id'])

                if member:
                    await self.sendMessage(member, response)

        # Help message
        elif command == 'help':
            await self.sendMessage(receiver, messages.help(self.messenger))

        # Could not match any command. Send the unknwon command message.
        else:
            await self.sendMessage(receiver, (message.author.mention + ", " + commandhandler.unknown(self)))

    ######
    # Unfortunately there is no better way to send messages to a user if you have
    # only their userId. Therefor this method searched the discord user object
    # in the global member list and returns is.
    ######
    def findMember(self, userId):

        for member in self.client.get_all_members():
            if int(member.id) == int(userId):
                return member

        logger.info ("Could not find the userId in the list?! {}".format(userId))

        return None

    def notifyChannels(self,message):

        for channelId in self.notifyChannelIds:

            channel = self.client.get_channel(channelId)

            if channel:
                asyncio.run_coroutine_threadsafe(self.sendMessage(channel, message), loop=self.client.loop)

    def publishProposal(self, author, proposal):

        ## Socialmedia
        response = "<u><b>Publish proposal<b><u>\n\n"

        response += "<b>{}<b> triggered the publishing for proposal <b>#{}<b>\n\n".format(author, proposal.proposalId)

        proposalUrl = "https://vote.smartcash.cc/Proposal/Details/{}".format(proposal.url)

        response += "<b>Discord<b> "

        if not proposal.discord:

            response += "Success"

            proposal.discord = 1

            responses = commandhandler.handlePublishedProposal(self, proposal)

            message = responses['message']

            for userId in responses['userIds']:

                member = self.findMember(userId)

                if member:
                    asyncio.run_coroutine_threadsafe(self.sendMessage(member, message), loop=self.client.loop)

            self.notifyChannels(message)
        else:
            response += "Alread published!"

        response += "<b>\nTwitter<b> "

        if self.tweeter and not proposal.twitter:

            tweet =  "💥 New Proposal 💥\n\n"
            tweet += proposal.title + "\n\n"
            tweet += "\n\n"
            tweet += proposalUrl

            result = self.tweeter.tweet(tweet)

            if result['status'] != PublishResult.Success:
                response += str(result['error'])
            else:
                response += "Success"
                proposal.twitter = 1

        elif self.tweeter:
            response += "Alread published!"
        else:
            response += "No twitter account given!"

        response += "\n<b>Reddit<b> "

        if self.reddit and not proposal.reddit:

            title = "💥 New Proposal 💥 - {}".format(proposal.title)

            result = self.reddit.submit("test", title=title,  url=proposalUrl, resubmit=False)

            if result['status'] != PublishResult.Success:
                response += str(result['error'])
            else:
                response += "Success"
                proposal.reddit = 1

        elif self.reddit:
            response += "Alread published!"
        else:
            response += "No reddit account given!"

        response += "\n<b>Gab.ai<b> "

        if self.gab and not proposal.gab:

            tweet =  "💥 New Proposal 💥\n\n"
            tweet += proposal.title + "\n\n"
            tweet += "\n\n"
            tweet += proposalUrl

            result = self.gab.post(tweet)

            if result['status'] != PublishResult.Success:
                response += str(result['error'])
            else:
                response += "Success"
                proposal.gab = 1

        elif self.gab:
            response += "Alread published!"
        else:
            response += "No gab account given!"

        self.proposals.db.updateProposal(proposal)

        self.notifyAdmins(messages.markdown(response, self.messenger))

    ############################################################
    #                        Callbacks                         #
    ############################################################

    ######
    # Callback for evaluating if someone in the database had an upcomming event
    # and send messages to all chats with activated notifications
    #
    # Called by: SmartCashProposals
    #
    ######
    def proposalPublishedCB(self, proposal):

        adminResponse = messages.publishedProposalNotificationAdmin(self.messenger, proposal)

        self.notifyAdmins(adminResponse)

    def proposalReminderCB(self, proposal):

            responses = commandhandler.handleReminderProposal(self, proposal)

            message = responses['message']

            for userId in responses['userIds']:

                member = self.findMember(userId)

                if member:
                    asyncio.run_coroutine_threadsafe(self.sendMessage(member, message), loop=self.client.loop)

            self.notifyChannels(message)

            if self.tweeter:

                tweet =  "❗️ 24 hours left ❗️\n\n"
                tweet += proposal.title + "\n\n"
                tweet += "1 more day till the end! GO cast your votes! "

                tweet += "https://vote.smartcash.cc/Proposal/Details/{}".format(proposal.url)

            tweetResult = self.tweeter.tweet(tweet)

            if tweetResult['status'] != PublishResult.Success:
                self.adminCB("**Tweeter error** {}".format(tweetResult['error']))

    ######
    # Callback for evaluating if someone in the database has won the reward
    # and send messages to all chats with activated notifications
    #
    # Called by: SmartCashProposals
    #
    ######
    def proposalUpdatedCB(self, updated, proposal):

        responses = commandhandler.handleUpdatedProposal(self, updated, proposal)

        for userId, message in responses.items():

            member = self.findMember(userId)

            if member:
                asyncio.run_coroutine_threadsafe(self.sendMessage(member, message), loop=self.client.loop)

    ######
    # Callback for evaluating if someone in the database has won the reward
    # and send messages to all chats with activated notifications
    #
    # Called by: SmartCashProposals
    #
    ######
    def proposalEndedCB(self, proposal):

        responses = commandhandler.handleEndedProposal(self, proposal)

        message = responses['message']

        for userId in responses['userIds']:

            member = self.findMember(userId)

            if member:
                asyncio.run_coroutine_threadsafe(self.sendMessage(member, message), loop=self.client.loop)

        self.notifyChannels(message)

        if self.tweeter:

            if proposal.allocated():
                tweet =  "🎉 Approved 🎉\n\n"
            else:
                tweet = "Rejected 👎\n\n"

            tweet += proposal.title + "\n\n"

            tweet += "https://vote.smartcash.cc/Proposal/Details/{}".format(proposal.url)

            tweetResult = self.tweeter.tweet(tweet)

            if tweetResult['status'] != PublishResult.Success:
                self.adminCB("Tweeter error {}".format(tweetResult['error']))


    def notifyAdmins(self, message):

        if not len(self.admins):
            return

        for admin in self.admins:

            member = self.findMember(admin)

            if member:
                asyncio.run_coroutine_threadsafe(self.sendMessage(member, message), loop=self.client.loop)
            else:
                logger.warning("notifyAdmins - Could not find admin {}".format(admin))

    ######
    # Push the message to the admin
    #
    # Called by: SmartNodeList
    #
    ######
    def adminCB(self, message):

        if not len(self.admins):
            return

        admin = self.findMember(self.admins[0])

        if admin:
            asyncio.run_coroutine_threadsafe(self.sendMessage(admin, message), loop=self.client.loop)
        else:
            logger.warning("adminCB - Could not find admin.")
