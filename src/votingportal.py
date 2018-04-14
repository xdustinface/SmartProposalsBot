
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
stateDeactivated = 'deactivated'

validProposalStates = [stateOpen, stateAllocated, stateCompleted, stateDeactivated]

errorInvalidState = "Invalid proposal state - {}"

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

        optional = ['reminder', 'approval']

        for key in required:
            if not key in rawDict:
                raise JsonFormatException( "{} not found".format(key) )

        for key in optional:
            if not key in rawDict:
                rawDict[key] = 0

        return cls(rawDict)

    def remainingString(self):

        s = self.votingDeadline

        try:
            d = datetime.datetime.strptime(self.votingDeadline, '%Y-%m-%dT%H:%M:%S')
            seconds = calendar.timegm(d.timetuple()) - time.time()
            s = util.secondsToText(seconds)
        except:
            log.error("Date format changed?")

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

    def valid(self):

        for state in validProposalStates:
            if state in self.status.lower():
                return True

        return False

    def allocated(self):
        return stateAllocated in self.status.lower()

    def open(self):
        return self.status.lower() == stateOpen

    def passing(self):
        log.info(self)
        return self.status.lower() == stateOpen and self.currentStatus.lower() == 'yes'

    def failing(self):
        return self.status.lower() == stateOpen and self.currentStatus.lower() == 'no'

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
        self.proposalEndedCB = None

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
                    self.errorCB(errorInvalidState.format(proposal.status))
                else:
                    self.proposals[proposal.proposalId] = proposal

        self.running = True
        self.startTimer(1)

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

        response = requests.get(self.url + self.apiVersion + self.openEndpoint,
                         timeout=20)

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

            for id, proposal in self.proposals.items():

                if proposal.status.lower() == stateOpen and not id in openProposals:
                    log.info("Proposal ended!")

                    try:
                        detailed = self.loadProposalDetail(id)
                    except Exception as e:
                        log.error("Could not load proposal {}".format(proposal.proposalId),exc_info=e)
                        self.errorCB(str(e))
                    else:

                        self.proposals[id] = detailed

                        if self.proposalEndedCB:
                            self.proposalEndedCB(detailed)
                else:

                    dbProposal = self.db.getProposal(proposal.proposalId)

                    if not dbProposal:
                        log.info("Add {}".format(proposal.title))
                        if not self.db.addProposal(proposal):
                            log.warning("Could not add {}".format(proposal.title))

                        if self.proposalPublishedCB:
                            self.proposalPublishedCB(proposal)

                    elif proposal.open():
                        # Compare metrics!
                        log.info("Compare {}".format(proposal.title))

                        updated = {
                                    'voteYes' : None,
                                    'voteNo' : None,
                                    'voteAbstain' : None,
                                    'status' : None,
                                    'currentStatus' : None
                                  }

                        compare = Proposal.fromRaw(dbProposal)

                        for key in updated:
                            if compare.__getattribute__(key) != proposal.__getattribute__(key):
                                updated[key] = {'before':compare.__getattribute__(key), 'now': proposal.__getattribute__(key)}

                        if sum(map(lambda x: x != None,list(updated.values()))):
                            log.info("Proposal updated!")

                            if self.proposalUpdatedCB:
                                self.db.updateProposal(proposal)
                                self.proposalUpdatedCB(updated, proposal)

    def getOpenProposals(self):
        return sorted(filter(lambda x: x.open(), self.proposals.values()))

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
