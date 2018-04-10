#!/usr/bin/env python3

import logging
import telegram
import json
import time
import threading
import uuid

from telegram.error import (TelegramError, Unauthorized, BadRequest,
                            TimedOut, ChatMigrated, NetworkError, RetryAfter)
from telegram.ext import CommandHandler,MessageHandler,Filters
from telegram.ext import Updater

from src import util
from src import messages
from src import commands

logger = logging.getLogger("bot")

####
# Message which gets used in the MessageQueue
####
class Message(object):

    def __init__(self, text):
        self.text = text
        self.attempts = 1

    def __str__(self):
        return self.text

####
# Message queue for the telegram api rate limit management: MessagingMachine
####
class MessageQueue(object):

    def __init__(self, chatId):

        self.chatId = chatId
        self.queue = []
        self.messagesPerSecond = 1
        self.leftover = self.messagesPerSecond
        self.lastCheck = time.time()

    ######
    # Makes the queue printable
    ######
    def __str__(self):
        return "MessageQueue chat {}, len {}, left {}".format(self.chatId, len(self.queue),self.leftover)

    ######
    # Refresh the current rate limit state
    ######
    def refresh(self):

        current = time.time()
        passed = current - self.lastCheck
        self.lastCheck = current

        self.leftover += passed * self.messagesPerSecond

        if self.leftover > self.messagesPerSecond:
            self.leftover = self.messagesPerSecond

        #logger.debug("[{}] leftover {}".format(self.chatId, self.leftover))

    ######
    # Check if the queue has messages and has not hit the rate limit yet
    ######
    def ready(self):

        self.refresh()

        return len(self.queue) and int(self.leftover) > 0

    ######
    # Add a message to the queue
    ######
    def add(self, message):
        self.queue.append(message)

    ######
    # Get the next message, remove those with 3 send attempts.
    ######
    def next(self):

        if self.queue[0].attempts >= 3:
            logger.info("Delete due to max attemts. After {}".format(len(self.queue)))
            self.pop()

        return self.queue[0] if len(self.queue) else None

    ######
    # Remove a message and decrease the ratelimit counter
    ######
    def pop(self):

        self.leftover -= 1

        if not len(self.queue):
            return

        del self.queue[0]

    ######
    # Lock the queue for a given number of seconds.
    ######
    def lock(self, seconds):
        self.leftover -= seconds * self.messagesPerSecond

    ######
    # Called when an error occured. Give the highest rated message a shot.
    ######
    def error(self):

        self.leftover -= 1

        if not len(self.queue):
            return

        self.queue[0].attempts += 1


####
# Telegram API Rate limit management. Handles all the user queues and tries
# to send messages periodically.
####
class MessagingMachine(object):

    def __init__(self, bot, database):
        self.sem = threading.Lock()
        self.bot = bot
        self.database = database
        self.queues = {}
        self.sendInterval = 0.25 # Seconds
        self.timer = None
        self.maxLength = 2000
        self.messagesPerSecond = 30
        self.leftover = self.messagesPerSecond
        self.lastCheck = time.time()

        self.startTimer()


    ######
    # Start the messaging timer
    ######
    def startTimer(self):

        self.timer = threading.Timer(self.sendInterval, self.run)
        self.timer.start()

    ######
    # Stop the messaging timer
    ######
    def stopTimer(self):
        if self.timer:
            self.timer.cancel()

    ######
    # Refresh the current rate limit state
    ######
    def refresh(self):

        current = time.time()
        passed = current - self.lastCheck
        self.lastCheck = current

        self.leftover += passed * self.messagesPerSecond

        if self.leftover > self.messagesPerSecond:
            self.leftover = self.messagesPerSecond

    ######
    # Check if the queue has messages and has not hit the rate limit yet
    ######
    def ready(self):

        self.refresh()

        return int(self.leftover) > 0

    ######
    # Add a message for a specific userId. If there is a queue it gets just
    # added to it otherwise one will be created.
    ######
    def addMessage(self, chatId, text, split = '\n'):

        self.sem.acquire()

        logger.info("addMessage - Chat: {}, Text: {}".format(chatId,text))

        if chatId not in self.queues:
            self.queues[chatId] = MessageQueue(chatId)

        for part in messages.splitMessage(text, split, self.maxLength ):
            self.queues[chatId].add(Message(part))

        logger.info(self.queues[chatId])

        self.sem.release()

    ######
    # Timer Callback. Main part of this class. Goes through all the queues, checks
    # if any rate limit got hit and sends messages if its allowed to.
    ######
    def run(self):

        self.sem.acquire()

        for chatId, queue in self.queues.items():

            if not self.ready():
                logger.debug("MessagingMachine not ready {}".format(self.leftover))
                break

            if not queue.ready():
                logger.debug("Queue not ready {}".format(queue))
                continue

            err = True

            message = queue.next()

            if message == None:
                continue

            try:
                self.bot.sendMessage(chat_id=chatId, text = str(message),parse_mode=telegram.ParseMode.MARKDOWN )

            except Unauthorized as e:
                logger.warning("Exception: Unauthorized {}".format(e))

                self.database.removeFromWatchlist(chatId)
                self.database.deleteUser(chatId)

                err = False

            except TimedOut as e:
                logger.warning("Exception: TimedOut {}".format(e))
            except NetworkError as e:
                logger.warning("Exception: NetworkError {}".format(e))
            except ChatMigrated as e:
                logger.warning("Exception: ChatMigrated from {} to {}".format(chatId, e.new_chat_id))
            except BadRequest as e:
                logger.warning("Exception: BadRequest {}".format(e))
            except RetryAfter as e:
                logger.warning("Exception: RetryAfter {}".format(e))

                queue.lock(e.retry_after)
                warnMessage = messages.rateLimitError(self.messenger, util.secondsToText(int(e.retry_after)))
                self.bot.sendMessage(chat_id=chatId, text = warnMessage ,parse_mode=telegram.ParseMode.MARKDOWN )

            except TelegramError as e:
                logger.warning("Exception: TelegramError {}".format(e))
            else:
                logger.debug("sendMessage - OK!")
                err = False

            if err:
                queue.error()
            else:
                queue.pop()

            self.leftover -= 1

        self.sem.release()

        self.startTimer()


class SmartProposalBotTelegram(object):

    def __init__(self, botToken, admin, password, db, proposals):

        # Currently only used for markdown
        self.messenger = "telegram"

        # Create a bot instance for async messaging
        self.bot = telegram.Bot(token=botToken)
        # Create the updater instance for configuration
        self.updater = Updater(token=botToken)
        # Set the database of the users/watchlists
        self.database = db
        # Store and setup the proposal handler
        self.proposals = proposals
        self.proposals.newProposalCB = self.newProposalCB
        self.proposals.proposalEndedCB = self.proposalEndedCB
        # Store the admins id
        self.admin = admin
        # Store the admin password
        self.password = password
        # Create the message queue
        self.messageQueue = MessagingMachine(self.bot, db)

        # Get the dispather to add the needed handlers
        dp = self.updater.dispatcher

        #### Setup command handler ####
        dp.add_handler(CommandHandler('subscribe', self.subscribe))
        dp.add_handler(CommandHandler('unsubscribe', self.unsubscribe))
        dp.add_handler(CommandHandler('open', self.open))
        dp.add_handler(CommandHandler('latest', self.latest))
        dp.add_handler(CommandHandler('passing', self.passing))
        dp.add_handler(CommandHandler('faling', self.failing))

        #### Setup common handler ####
        dp.add_handler(CommandHandler('help', self.help))

        #### Setup admin handler, Not public ####
        dp.add_handler(CommandHandler('broadcast', self.broadcast, pass_args=True))
        dp.add_handler(CommandHandler('stats', self.stats, pass_args=True))

        dp.add_handler(MessageHandler(Filters.command, self.unknown))
        dp.add_error_handler(self.error)


    ######
    # Starts the bot and block until the programm will be stopped.
    ######
    def start(self):
        logger.info("Start!")
        self.updater.start_polling()

        # Start its task and leave it
        self.rewardList.start()

        self.sendMessage(self.admin, "*Bot Started*")

        self.updater.idle()

    def isGroup(self, update):

        if update.message.chat_id != update.message.from_user.id:
            logger.warning("not allowed group action")
            response = messages.notAvailableInGroups(self.messenger)
            self.sendMessage(update.message.chat_id, response )
            return True

        return False

    ######
    # Add a message to the queue
    ######
    def sendMessage(self, chatId, text, split = '\n'):
        self.messageQueue.addMessage(chatId, text, split)


    def adminCheck(self, chatId, password):
        logger.warning("adminCheck - {} == {}, {} == {}".format(self.admin, chatId, self.password, password))
        return int(self.admin) == int(chatId) and self.password == password



    def stats(self, bot, update, args):

        if len(args) == 1 and\
           self.adminCheck(update.message.chat_id, args[0]):

            logger.warning("stats - access granted")

            response = common.stats(self)

            self.sendMessage(self.admin, response)
        else:
            response = common.unknown(self)
            self.sendMessage(update.message.chat_id, response)

    def loglevel(self, bot, update, args):

        if len(args) >= 2 and\
           self.adminCheck(update.message.chat_id, args[0]):

            logger.warning("loglevel - access granted")

            response = "*Loglevel*"

            self.sendMessage(self.admin, response)
        else:
            response = common.unknown(self)
            self.sendMessage(update.message.chat_id, response)

    def settings(self, bot, update, args):

        if len(args) == 1 and\
           self.adminCheck(update.message.chat_id, args[0]):

            logger.warning("settings - access granted")

            response = "*Settings*"

            self.sendMessage(self.admin, response)
        else:
            response = common.unknown(self)
            self.sendMessage(update.message.chat_id, response)

    def unknown(self, bot, update):

        response = common.unknown(self)
        self.sendMessage(update.message.chat_id, response)

    def error(self, bot, update, error):

        common.error(self, update, error)


    ############################################################
    #                        Callbacks                         #
    ############################################################


    ######
    # Push the message to the admin
    #
    # Called by: SmartCashProposals
    #
    ######
    def adminCB(self, message):
        self.sendMessage(self.admin, message)
