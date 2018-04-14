#!/usr/bin/env python3

import logging
from src import messages
from src import util
import requests
import json
import time

import telegram
import discord

logger = logging.getLogger("commands")

######
# Return the welcome message and add the user if its not already added
#
#
# Gets only called by any command handler
######
def checkUser(bot, message):
    logger.info("checkUser")

    result = {'response':None, 'added':False}

    userInfo = util.crossMessengerSplit(message)
    userId = userInfo['user'] if 'user' in userInfo else None
    userName = userInfo['name'] if 'name' in userInfo else "Unknown"

    if not bot.database.getUser(userId) and bot.database.addUser(userId, userName):
        logger.info("checkUser - new user {}".format(userName))

        result['added'] = True

        if bot.messenger == 'discord':
            result['response'] = messages.welcome(bot.messenger)

    return result

######
# Return the given proposals as formated string
#
#
# Gets only called by any command handler
######
def proposalList(bot, proposals, title = "", fallback = ""):
    logger.info("proposalList - " + title)

    response = ""

    if title != "":
        response = messages.markdown("<u><b>{}<b><u>\n\n".format(title),bot.messenger)

    if len(proposals):

        for proposal in proposals:
            response += messages.proposalShort(bot.messenger, proposal)
    else:
        response += fallback

    return response

######
# Command handler for printing the open proposals
#
# Command: open
#
# Gets only called by bot instance
######
def open(bot):
    logger.info("open")

    open = bot.proposals.getOpenProposals()

    return proposalList(bot, open, "Open proposals", "Currently no proposal ready to vote!")


######
# Command handler for printing the latest proposal
#
# Command: latest
#
# Gets only called by bot instance
######
def latest(bot):

    logger.info("latest")

    response = messages.markdown("<u><b>Latest proposal<b><u>\n\n",bot.messenger)

    proposal = bot.proposals.getLatestProposals()

    if proposal:
        response += messages.proposalDetail(bot.messenger, proposal)
    else:
        response += "No latest proposal available!"

    return response

######
# Command handler for printing a specific proposal
#
# Command: detail
#
# Gets only called by bot instance
######
def detail(bot,args):

    logger.info("detail")

    response = messages.markdown("<u><b>Proposal detail<b><u>\n\n",bot.messenger)

    if len(args):
        proposalIds = []

        for arg in args:
            try:
                proposalIds.append(int(arg))
            except:
                response += "Invalid argument: {}\n\n".format(messages.removeMarkdown(arg))

    for proposalId in proposalIds:
        proposal = bot.proposals.getProposal(proposalId)

        if proposal:
            response += messages.proposalDetail(bot.messenger, proposal)
        else:
            response += "There is no info about the ID {}!\n\n".format(proposalId)

    return response

######
# Command handler for printing the open proposals
#
# Command: open
#
# Gets only called by bot instance
######
def passing(bot):
    logger.info("passing")

    proposals = bot.proposals.getPassingProposals()

    return proposalList(bot, proposals, "Passing proposals", "Currently no proposal ready to vote!")

######
# Command handler for printing the open proposals
#
# Command: open
#
# Gets only called by bot instance
######
def failing(bot):
    logger.info("failing")

    proposals = bot.proposals.getFailingProposals()

    return proposalList(bot, proposals, "Failing proposals", "Currently no proposal ready to vote!")

######
# Return the given proposals as formated string
#
#
# Gets only called by any command handler
######
def subscription(bot, message, state):
    logger.info("subscription")

    response = "<u><b>Subscription<b><u>\n\n"

    userInfo = util.crossMessengerSplit(message)
    userId = userInfo['user'] if 'user' in userInfo else None
    userName = userInfo['name'] if 'name' in userInfo else "Unknown"
    public = userInfo['public']

    dbUser = bot.database.getUser(userId)
    if not dbUser:
        logger.error("User not in db?!")
        response += messages.unexpectedError(bot.messenger)
    else:
        logger.info("subscription - update {}".format(state))

        bot.database.updateSubscription(userId, state)

        response += "Succesfully <b>{}subscribed<b> new/ended proposals.".format("" if state else "un")

    return messages.markdown(response, bot.messenger)

######
# Return the given proposals as formated string
#
#
# Gets only called by any command handler
######
def add(bot, message, args):
    logger.info("add")

    response = "<u><b>Add to watchlist<b><u>\n\n"

    userInfo = util.crossMessengerSplit(message)
    userId = userInfo['user'] if 'user' in userInfo else None
    userName = userInfo['name'] if 'name' in userInfo else "Unknown"
    public = userInfo['public']

    dbUser = bot.database.getUser(userId)
    if not dbUser:
        logger.error("User not in db?!")
        response += messages.unexpectedError(bot.messenger)
    else:

        if len(args) != 1:
            response += messages.proposalIdRequired(bot.messenger, 'add')
        elif not util.isInt(args[0].replace('#','')):
            response += messages.invalidProposalId(bot.messenger, args[0])
        else:

            proposal = bot.proposals.getProposal(int(args[0].replace('#','')))

            if not proposal:
                response += messages.proposalNotFound(bot.messenger, args[0])
            else:

                currentList = bot.database.getWatchlist(userId=userId)

                if currentList and len(currentList) and\
                   proposal.proposalId in list(map(lambda x: x['proposal_id'],currentList)):

                   response += messages.proposalIsOnWatchlist(bot.messenger, proposal.title)

                else:

                    if bot.database.addToWatchlist(userId, proposal.proposalId):
                        response += "Succesfully added the proposal <b>{}<b> to your watchlist.".format(proposal.title)
                    else:
                        logger.error("Could not add watchlist entry?!")
                        response += messages.unexpectedError(bot.messenger)

    return messages.markdown(response, bot.messenger)

######
# Return the given proposals as formated string
#
#
# Gets only called by any command handler
######
def remove(bot, message, args):
    logger.info("remove")

    response = "<u><b>Remove from watchlist<b><u>\n\n"

    userInfo = util.crossMessengerSplit(message)
    userId = userInfo['user'] if 'user' in userInfo else None
    userName = userInfo['name'] if 'name' in userInfo else "Unknown"
    public = userInfo['public']

    dbUser = bot.database.getUser(userId)
    if not dbUser:
        logger.error("User not in db?!")
        response += messages.unexpectedError(bot.messenger)
    else:

        if len(args) != 1:
            response += messages.proposalIdRequired(bot.messenger, 'remove')
        elif not util.isInt(args[0].replace('#','')):
            response += messages.invalidProposalId(bot.messenger, args[0])
        else:

            proposal = bot.proposals.getProposal(int(args[0].replace('#','')))

            if not proposal:
                response += messages.proposalNotFound(bot.messenger, args[0])
            else:

                currentList = bot.database.getWatchlist(userId=userId)

                if currentList and len(currentList) and\
                   not proposal.proposalId in list(map(lambda x: x['proposal_id'],currentList)) or\
                   not currentList or not len(currentList):

                   response += messages.proposalIsNotOnWatchlist(bot.messenger, proposal.title)

                else:

                    if bot.database.removeFromWatchlist(userId, proposal.proposalId):
                        response += "Succesfully removed the proposal <b>{}<b> from your watchlist.".format(proposal.title)
                    else:
                        logger.error("Could not remove watchlist entry?!")
                        response += messages.unexpectedError(bot.messenger)

    return messages.markdown(response, bot.messenger)

######
# Return the given proposals as formated string
#
#
# Gets only called by any command handler
######
def watchlist(bot, message):
    logger.info("watchlist")

    response = "<u><b>Your watchlist<b><u>\n\n"

    userInfo = util.crossMessengerSplit(message)
    userId = userInfo['user'] if 'user' in userInfo else None
    userName = userInfo['name'] if 'name' in userInfo else "Unknown"
    public = userInfo['public']

    dbUser = bot.database.getUser(userId)
    if not dbUser:
        logger.error("User not in db?!")
        response += "<b>Unexpected error. Contact the team!<b>"
    else:

        watchlist = bot.database.getWatchlist(userId=userId)

        if not watchlist or not len(watchlist):
            logger.info("No watchlist entry!")
            response += messages.noWatchlistEntry(bot.messenger)
        else:

            proposalIds = list(map(lambda x: x['proposal_id'], watchlist))
            watchlist = bot.proposals.getProposals(proposalIds)

            response += proposalList(bot, watchlist)

    return messages.markdown(response, bot.messenger)


######
# Command handler for printing stats about the bot
#
# Command: /stats
#
# Gets only called by bot instance
######
def stats(bot):

    logger.info("stats")

    response = messages.markdown("<u><b>Statistics<b><u>\n\n",bot.messenger)

    users = bot.database.getUsers()
    subscriptions = bot.database.getSubscriptions()
    watchlistEntries = bot.database.getWatchlist()

    response += "User: {}\n".format(len(users))
    response += "Subscriptions: {}\n".format(len(subscriptions))
    response += "Watchlist entires: {}\n".format(len(watchlistEntries))

    return response

def handlePublishedProposal(bot, proposal):

    # Create notification response messages!
    responses = {'message':messages.publishedProposalNotification(bot.messenger, proposal), 'userIds': []}

    for user in bot.database.getSubscriptions():
        responses['userIds'].append(user['id'])

    return responses

def handleUpdatedProposal(bot, updated, proposal):

    # Create notification response messages!

    responses = {}
    changes = []

    if 'voteYes' in updated and updated['voteYes']:
        change = updated['voteYes']
        changes.append("<b>YES<b> votes (SMART) changed from <b>{:,}<b> to <b>{:,}<b>\n".format(round(change['before'],1), round(change['now'],1)))

    if 'voteNo' in updated and updated['voteNo']:
        change = updated['voteNo']
        changes.append("<b>NO<b> votes (SMART) changed from <b>{:,}<b> to <b>{:,}<b>\n".format(round(change['before'],1), round(change['now'],1)))

    if 'voteAbstain' in updated and updated['voteAbstain']:
        change = updated['voteAbstain']
        changes.append("<b>ABSTAIN<b> votes (SMART) changed from <b>{:,}<b> to <b>{:,}<b>\n".format(round(change['before'],1), round(change['now'],1)))

    if 'status' in updated and updated['status']:
        change = updated['status']
        changes.append("<b>State<b> changed from <b>{}<b> to <b>{}<b>\n".format(change['before'], change['now']))

    if 'currentStatus' in updated and updated['currentStatus']:
        change = updated['currentStatus']
        changes.append("<b>Current result<b> changed from <b>{}<b> to <b>{}<b>\n".format(change['before'], change['now']))

    for entry in bot.database.getWatchlist(proposalId=proposal.proposalId):

        message = "<u><b>Watchlist update!<b><u>\n\n"
        message += "The proposal <b>{}<b> obtained the following change{}\n\n".format(proposal.title, "s" if len(changes) > 1 else "")

        for change in changes:
            message += change

        responses[entry['user_id']] = messages.markdown(message, bot.messenger)

    return responses

def handleEndedProposal(bot, proposal):

    # Create notification response messages!
    responses = {'message':messages.endedProposalNotification(bot.messenger, proposal), 'userIds': []}

    for user in bot.database.getSubscriptions():
        responses['userIds'].append(user['id'])

    return responses

######
# Command handler for printing the unknonw text
#
# Command: fallback for unknown commands
#
# Gets only called by bot instance
######
def unknown(bot):

    logger.info("help")

    return messages.markdown("I'm not sure what you mean? Try <cb>help<ca>",bot.messenger)

######
# Command handler for logging errors from the bot api
#
# Command: No command, will get called on errors.
#
# Gets only called by bot instance
######
def error(bot, update, error):
    logger.error('Update "%s" caused error "%s"' % (update, error))
    logger.error(error)
