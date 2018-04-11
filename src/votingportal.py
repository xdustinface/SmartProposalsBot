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

log = logging.getLogger("voting")

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


class Proposal(object):
    def __init__(self, data):

        for arg in data:
            setattr(self, arg, data[arg])

    @classmethod
    def fromRaw(cls, raw):

        rawDict = dict(raw)

        required = ['proposalId','proposalKey','title','url',
                    'summary','owner','amountSmart','amountUSD',
                    'installment','votingDeadline','createdDate','status',
                    'voteYes','voteNo','voteAbstain','percentYes',
                    'percentNo','percentAbstain','currentStatus','categoryTitle']

        for key in required:
            if not key in rawDict:
                raise JsonFormatException( "{} not found - {}".format(key) )

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

        s = self.createdDate

        try:
            s = s.split('T')
            s = " ".join(s)
            s += " UTC"
        except:
            log.error("Date format changed?")

        return s

    def deadlineString(self):

        s = self.votingDeadline

        try:
            s = s.split('T')
            s = " ".join(s)
            s += " UTC"
        except:
            log.error("Date format changed?")

        return s

class SmartCashProposals(object):

    def __init__(self, db):

        self.running = False

        self.db = db
        self.timer = None

        self.url = "https://vote.smartcash.cc/api/"
        self.apiVersion = "v1"
        self.openEndpoint = "/voteproposals"

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

                if not proposal.proposalId in self.proposals:
                    self.proposals[proposal.proposalId] = proposal

        self.running = True
        self.startTimer(1)

    def stop(self):
        log.info("stop")

    def updateProposals(self):

        self.update()
        self.startTimer()

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

            openProposals = openList['result']

            if not len(openProposals):
                log.info("Currently no proposal open for voting!")
                return

            log.info("{} open proposals found".format(len(openProposals)))

            for raw in openProposals:

                try:
                    proposal = Proposal.fromRaw(raw)
                except Exception as e:
                    log.error("Could not create proposal from raw data", exc_info = e)
                    continue
                else:
                    self.proposals[proposal.proposalId] = proposal

            self.sync()

    def sync(self):
        log.info("sync")

        for proposal in self.proposals.values():

            dbProposal = self.db.getProposal(proposal.proposalId)

            if not dbProposal:
                log.info("Add {}".format(proposal.title))
                if not self.db.addProposal(proposal):
                    log.warning("Could not add {}".format(proposal.title))

                if self.proposalPublishedCB:
                    self.proposalPublishedCB(proposal)

            else:
                # Compare metrics!
                log.info("Compare {}".format(proposal.title))

                updated = { 'voteYes' : None,
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

        open = []

        for proposal in self.proposals.values():
            if  'OPEN' in proposal.status.upper():
                open.append(proposal)

        return open

    def getProposal(self, proposalId):

        if proposalId in self.proposals:
            return self.proposals[proposalId]

        return None

    def getProposals(self, proposalIds):

        proposals = []

        for id in proposalIds:
            if id in self.proposals:
                proposals.append(self.proposals[id])

        return proposals

    def getLatestProposals(self):

        if len(self.proposals):
            return list(self.proposals.values())[-1]

        return None

    def getPassingProposals(self):
        passing = []

        for proposal in self.proposals.values():
            if  'OPEN' in proposal.status.upper() and\
                'YES' in proposal.currentStatus.upper():
                passing.append(proposal)

        return passing

    def getFailingProposals(self):
        failing = []

        for proposal in self.proposals.values():
            if  'OPEN' in proposal.status.upper() and\
                'NO' in proposal.currentStatus.upper():
                failing.append(proposal)

        return failing
