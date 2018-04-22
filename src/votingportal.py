
import os, stat, sys
import re
import subprocess
import json
import time
import requests

import logging
import threading
import re
import uuid

import datetime, calendar
from src import util

stateOpen = 'open'
stateAllocated = 'allocated'
stateCompleted = 'completed'
stateNotFunded = "not funded"
stateDeactivated = 'deactivated'

validProposalStates = [stateOpen, stateAllocated, stateCompleted, stateNotFunded, stateDeactivated]

log = logging.getLogger("voting")

def proposalDateToString(dateString):

    try:
        dateParts = dateString.split('T')
        dateString = " ".join(dateParts)
        dateString += " UTC"
    except:
        log.error("Date format changed?")

    return dateString

class ProposalException(Exception):

    def __init__(self, code, message):
        super(ProposalException, self).__init__()
        self.code = code
        self.message = message

    def __repr__(self):
        return self.__str__()

    def __str__(self):
        return "{} - {}".format(self.code, self.message)

class JsonFormatException(ProposalException):
    def __init__(self, message):
        super(JsonFormatException, self).__init__(1,message)

class LoadException(ProposalException):
    def __init__(self, message):
        super(LoadException, self).__init__(2,message)

class Proposal(object):
    def __init__(self, data):

        for arg in data:
            setattr(self, arg, data[arg])

    def __str__(self):
        return "proposalId {}, status {}, currentStatus {}".format(self.proposalId,self.status, self.currentStatus)

    def __eq__(self, other):
        return self.hash == other.hash and\
                self.index == other.index

    def __lt__(self, other):
        return self.proposalId < other.proposalId

    @classmethod
    def fromRaw(cls, raw):

        rawDict = dict(raw)

        required = ['proposalId','proposalKey','title','url',
                    'summary','owner','amountSmart','amountUSD',
                    'installment','votingDeadline','createdDate','status',
                    'voteYes','voteNo','voteAbstain','percentYes',
                    'percentNo','percentAbstain','currentStatus','categoryTitle']

        optional = ['reminder', 'approval', 'twitter', 'reddit', 'gab', 'discord', 'telegram']

        for key in required:
            if not key in rawDict:
                raise JsonFormatException( "{} not found".format(key) )

        for key in optional:
            if not key in rawDict:
                rawDict[key] = 0

        return cls(rawDict)

    def remainingString(self):

        s = self.votingDeadline
        seconds = self.remainingSeconds()

        if seconds:
            s = util.secondsToText(seconds)

        return s

    def percentYesString(self):

        if self.percentYes == 'NaN':
            return '0.0'
        else:
            return str(round(self.percentYes,2))

    def percentNoString(self):

        if self.percentNo == 'NaN':
            return '0.0'
        else:
            return str(round(self.percentNo,2))

    def percentAbstainString(self):

        if self.percentAbstain == 'NaN':
            return '0.0'
        else:
            return str(round(self.percentAbstain,2))

    def createdString(self):
        return proposalDateToString(self.createdDate)

    def deadlineString(self):
        return proposalDateToString(self.votingDeadline)

    def remainingSeconds(self):

        seconds = 0

        try:
            d = datetime.datetime.strptime(self.votingDeadline, '%Y-%m-%dT%H:%M:%S')
            seconds = calendar.timegm(d.timetuple()) - time.time()
        except:
            log.error("Date format changed?")

        return seconds


    def valid(self):

        for state in validProposalStates:
            if state in self.status.lower():
                return True

        return False

    def allocated(self):
        return stateAllocated in self.status.lower()

    def open(self):
        return stateOpen in self.status.lower()

    def passing(self):
        return stateOpen in self.status.lower() and 'yes' in self.currentStatus.lower()

    def failing(self):
        return stateOpen in self.status.lower() and 'no' in self.currentStatus.lower()

    def published(self, twitter = False, reddit = False, gab = False, discord = False, telegram = False):

        if twitter and not self.twitter:
            return False

        if reddit and not self.reddit:
            return False

        if gab and not self.gab:
            return False

        if discord and not self.discord:
            return False

        if telegram and not self.telegram:
            return False

        return True

class SmartCashProposals(object):

    def __init__(self, db):

        self.running = False

        self.db = db
        self.timer = None

        self.url = "https://vote.smartcash.cc/api/"
        self.apiVersion = "v1"
        self.openEndpoint = "/voteproposals"
        self.detailEndpoint = "/voteproposals/detail/"

        self.proposalPublishedCB = None
        self.proposalUpdatedCB = None
        self.proposalReminderCB = None
        self.proposalEndedCB = None
        self.errorCB = None

        self.proposals = {}

    def startTimer(self, timeout = 120):
        self.timer = threading.Timer(timeout, self.updateProposals)
        self.timer.start()

    def start(self):
        log.info("start")

        # Load proposals from the DB
        for raw in self.db.getProposals():

            try:
                proposal = Proposal.fromRaw(raw)
            except Exception as e:
                log.error("Could not create proposal from raw data", exc_info = e)
                continue
            else:

                if not proposal.valid():
                    self.error("Invalid proposal state - {}".format(proposal.status))
                else:
                    self.proposals[proposal.proposalId] = proposal

        self.running = True
        self.startTimer(1)

    def error(self, message, exception = None):

        log.error(message,exc_info=exception)

        if self.errorCB:
            self.errorCB(message)

    def stop(self):
        log.info("stop")

    def updateProposals(self):

        self.update()
        self.startTimer()

    def loadProposalDetail(self, proposalId):
        log.info("loadProposalDetail")

        try:
            response = requests.get(self.url + self.apiVersion + self.detailEndpoint + str(proposalId),
                         timeout=20)
        except Exception as e:
            raise LoadException("Request exception {}".format(str(e)))
        else:

            if response.status_code != 200:
                log.error("Request failed: {}".format(response.status_code))
                raise LoadException("Invalid status code {}".format(response.status_code))

            try:
                detail = json.loads(response.text)
            except Exception as e:
                raise JsonFormatException("Load proposal detail {}".format(str(e)))
            else:

                if not 'status' in detail:
                    raise LoadException("Invalid response: status missing!")

                if not 'OK' in detail['status']:
                    raise LoadException("Invalid response: status not OK => {}".format(detail['status']))

                if not 'result' in detail:
                    raise LoadException("Invalid response: result missing!")

                raw = None

                # Workaround because there is a typo in the json result
                # Check both in case it gets fixed.
                if 'proposal' in detail['result']:
                    raw = detail['result']['proposal']
                elif 'propposal' in detail['result']:
                    raw = detail['result']['propposal']
                else:
                    raise LoadException("Invalid response: proposal missing!")

                try:
                    proposal = Proposal.fromRaw(raw)
                except Exception as e:
                    raise LoadException("Parse proposal detail {}".format(str(e)))
                else:

                    if proposal.proposalId != proposalId:
                        raise LoadException("proposalId missmatch {} - {}".format(proposal.proposalId, proposalId))

                    return proposal

    def update(self):

        log.info("update")

        response = None

        try:
            response = requests.get(self.url + self.apiVersion + self.openEndpoint,
                         timeout=20)
        except Exception as e:
            log.error("Request exception: {}".format(e))
            return

        if response.status_code != 200:
            log.error("Request failed: {}".format(response.status_code))
            return

        try:
            openList = json.loads(response.text)
        except Exception as e:
            log.error("Could not parse response", exc_info=e)
            return
        else:

            if not 'status' in openList:
                log.error("Invalid response: status missing!")
                return

            if not 'OK' in openList['status']:
                log.error("Invalid response: status not OK => {}".format(openList['status']))
                return

            if not 'result' in openList:
                log.error("Invalid response: result missing!")
                return

            openProposalsJson = openList['result']

            if not len(openProposalsJson):
                log.info("Currently no proposal open for voting!")
                return

            log.info("{} open proposals found".format(len(openProposalsJson)))

            openProposals = {}

            for raw in openProposalsJson:

                try:
                    proposal = Proposal.fromRaw(raw)
                except Exception as e:
                    log.error("Could not create proposal from raw data", exc_info = e)
                    continue
                else:
                    openProposals[proposal.proposalId] = proposal

            for id in self.proposals:

                proposal = self.proposals[id]

                if not id in openProposals:

                    if not proposal.open():
                        log.debug("Ended but was not open?!")
                        continue

                    try:
                        detailed = self.loadProposalDetail(id)
                    except Exception as e:
                        self.error("Could not load proposal {}".format(proposal.proposalId),e)
                    else:

                        updated = {
                                    'voteYes' : None,
                                    'voteNo' : None,
                                    'voteAbstain' : None,
                                    'status' : None,
                                    'currentStatus' : None
                                  }

                        for key in updated:

                            before = proposal.__getattribute__(key)
                            after = detailed.__getattribute__(key)
                            if before != after:

                                log.info("#{} - update {}: B: {} A: {}".format(id, key, before, after))
                                updated[key] = {'before':before, 'now': after}
                                proposal.__setattr__(key,after)

                        if self.proposalEndedCB:
                            self.proposalEndedCB(proposal)

                        self.db.updateProposal(proposal)

                        self.proposals[id] = proposal

                else:

                    dbProposal = self.db.getProposal(proposal.proposalId)

                    if not dbProposal:
                        log.error("Proposal not in DB. Should not happen!")
                        continue

                    # Compare metrics!
                    log.info("Compare {}".format(proposal.title))

                    updateNotify = {
                                'voteYes' : None,
                                'voteNo' : None,
                                'voteAbstain' : None,
                                'status' : None,
                                'currentStatus' : None
                              }

                    updateOnly = ['percentYes','percentNo', 'percentAbstain', 'amountSmart', 'amountUSD']

                    compare = Proposal.fromRaw(dbProposal)
                    open = openProposals[id]

                    for key in updateNotify:

                        before = compare.__getattribute__(key)
                        after = open.__getattribute__(key)

                        if before != after:

                            log.info("#{} - update notify {}: B: {} A: {}".format(id, key, before, after))
                            updateNotify[key] = {'before':before, 'now': after}
                            compare.__setattr__(key,after)

                    for key in updateOnly:

                        before = compare.__getattribute__(key)
                        after = open.__getattribute__(key)

                        if before != after:
                            log.info("#{} - update only {}: B: {} A: {}".format(id, key, before, after))
                            compare.__setattr__(key,after)

                    if sum(map(lambda x: x != None,list(updateNotify.values()))):
                        log.info("Proposal updated!")

                        if self.proposalUpdatedCB:
                            self.proposalUpdatedCB(updateNotify, compare)

                        self.db.updateProposal(compare)

                    remainingSeconds = compare.remainingSeconds()

                    if not compare.reminder and remainingSeconds and\
                        remainingSeconds < (48 * 60 * 60): # Remind 24hours before the end

                        compare.reminder = 1
                        self.db.updateProposal(compare)

                        if self.proposalReminderCB:
                            self.proposalReminderCB(compare)

                    self.proposals[id] = compare


            for id, proposal in openProposals.items():
                if not self.db.getProposal(id):
                    log.info("Add {}".format(proposal.title))

                    self.proposals[id] = proposal

                    if not self.db.addProposal(proposal):
                        log.warning("Could not add {}".format(proposal.title))

                    if self.proposalPublishedCB:
                        self.proposalPublishedCB(proposal)

    def getOpenProposals(self, remaining = None):

        if remaining:
            result = sorted(filter(lambda x: x.open() and x.remainingSeconds() < remaining, self.proposals.values()))
        else:
            result = sorted(filter(lambda x: x.open(), self.proposals.values()))

        return result

    def getProposal(self, proposalId):

        if proposalId in self.proposals:
            return self.proposals[proposalId]

        return None

    def getProposals(self, proposalIds):

        proposals = []

        for id in proposalIds:
            if id in self.proposals:
                proposals.append(self.proposals[id])

        return sorted(proposals)

    def getLatestProposals(self):

        if len(self.proposals):
            return sorted(list(self.proposals.values()))[-1]

        return None

    def getPassingProposals(self):
        return sorted(filter(lambda x: x.passing(),self.proposals.values()))

    def getFailingProposals(self):
        return sorted(filter(lambda x: x.failing(),self.proposals.values()))

    def getNotPublishedProposals(self, twitter=False, reddit=False, gab=False, discord=False, telegram=False):
        return sorted(filter(lambda x: not x.published(twitter = twitter,\
                                                       reddit=reddit,\
                                                       gab=gab,\
                                                       discord=discord,\
                                                       telegram=telegram),self.proposals.values()))
