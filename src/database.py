#!/usr/bin/env python3

import logging
from src import util
import threading
import sqlite3 as sql

logger = logging.getLogger("database")

#####
#
# Wrapper for the user database where all the users
# and their added proposals are stored.
#
#####

class BotDatabase(object):

    def __init__(self, dburi):

        self.connection = util.ThreadedSQLite(dburi)

        if self.isEmpty():
            self.reset()

    def isEmpty(self):

        tables = []

        with self.connection as db:

            db.cursor.execute("SELECT name FROM sqlite_master")

            tables = db.cursor.fetchall()

        return len(tables) == 0

    def addUser(self, userId, userName):

        user = None

        try:

            with self.connection as db:

                logger.debug("addUser: New user {} {}".format(userId,userName))

                db.cursor.execute("INSERT INTO users( id, name, subscription ) values( ?, ?, 1 )", ( userId, userName ))

                user = db.cursor.lastrowid
        except:
            pass

        return user

    def getUser(self, userId):

        user = None

        with self.connection as db:

            db.cursor.execute("SELECT * FROM users WHERE id=?",[userId])

            user = db.cursor.fetchone()

        return user

    def getUsers(self):

        users = None

        with self.connection as db:

            db.cursor.execute("SELECT * FROM users")

            users = db.cursor.fetchall()

        return users

    def getSubscriptions(self):

        users = None

        with self.connection as db:

            db.cursor.execute("SELECT * FROM users WHERE subscription=1")

            users = db.cursor.fetchall()

        return users

    def updateSubscription(self, userId, state):

        with self.connection as db:

            db.cursor.execute("UPDATE users SET subscription = ? WHERE id=?",(state,userId))

    def deleteUser(self, userId):

        with self.connection as db:

            db.cursor.execute("DELETE FROM users WHERE id=?",[userId])

    def getWatchlist(self, userId = None, proposalId = None):

        watchlist = None

        with self.connection as db:
            if userId and proposalId:
                db.cursor.execute("SELECT * FROM watchlist WHERE user_id=? AND proposal_id=?",[userId])
            elif userId and not proposalId:
                db.cursor.execute("SELECT * FROM watchlist WHERE user_id=?",[userId])
            elif not userId and proposalId:
                db.cursor.execute("SELECT * FROM watchlist WHERE proposal_id=?",[proposalId])
            else:
                db.cursor.execute("SELECT * FROM watchlist")

            watchlist = db.cursor.fetchall()

        return watchlist

    def addToWatchlist(self, userId, proposalId):

        added = None

        try:

            with self.connection as db:

                logger.debug("addToWatchlist: {} - {}".format(userId,proposalId))

                db.cursor.execute("INSERT INTO watchlist( user_id, proposal_id ) values( ?, ? )", ( userId, proposalId ))

                added = db.cursor.rowcount

        except Exception as e:
            logger.error("addToWatchlist", exc_info=e)
            pass

        return added

    def removeFromWatchlist(self, userId, proposalId = None):

        removed = False

        try:

            with self.connection as db:
                if proposalId:
                    db.cursor.execute("DELETE FROM watchlist WHERE user_id=? AND proposal_id=?",(userId, proposalId))
                else:
                    db.cursor.execute("DELETE FROM watchlist WHERE user_id=?",[userId])

                removed = db.cursor.rowcount

        except Exception as e:
            logger.error("removeFromWatchlist", exc_info=e)
            pass

        return removed

    def reset(self):

        sql = 'BEGIN TRANSACTION;\
        CREATE TABLE "users" (\
        	`id`	INTEGER NOT NULL PRIMARY KEY,\
        	`name`	INTEGER,\
        	`subscription`	INTEGER,\
            `last_activity`	INTEGER\
        );\
        CREATE TABLE "watchlist" (\
        	`id` INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,\
            `user_id` INTEGER,\
        	`proposal_id` INTEGER\
        );\
        COMMIT;'

        with self.connection as db:
            db.cursor.executescript(sql)


#####
#
# Wrapper for the proposal database where all the proposals from the
# voting portal are stored.
#
#####

class ProposalDatabase(object):

    def __init__(self, dburi):

        self.connection = util.ThreadedSQLite(dburi)

        if self.isEmpty():
            self.reset()

    def isEmpty(self):

        tables = []

        with self.connection as db:

            db.cursor.execute("SELECT name FROM sqlite_master")

            tables = db.cursor.fetchall()

        return len(tables) == 0

    def raw(self, query):

        with self.connection as db:
            db.cursor.execute(query)
            return db.cursor.fetchall()

        return None

    def addProposal(self, proposal):

        try:

            with self.connection as db:
                query = "INSERT INTO proposals(\
                        proposalId,\
                        proposalKey, \
                        title,\
                        url,\
                        summary,\
                        owner,\
                        amountSmart,\
                        amountUSD,\
                        installment,\
                        createdDate,\
                        votingDeadline,\
                        status,\
                        voteYes,\
                        voteNo,\
                        voteAbstain,\
                        percentYes,\
                        percentNo,\
                        percentAbstain,\
                        currentStatus,\
                        categoryTitle,\
                        approval,\
                        reminder,\
                        twitter,\
                        reddit,\
                        gab,\
                        discord) \
                        values( ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,0,0,0,0 )"

                db.cursor.execute(query, (
                                  proposal.proposalId,
                                  proposal.proposalKey,
                                  proposal.title,
                                  proposal.url,
                                  proposal.summary,
                                  proposal.owner,
                                  proposal.amountSmart,
                                  proposal.amountUSD,
                                  proposal.installment,
                                  proposal.createdDate,
                                  proposal.votingDeadline,
                                  proposal.status,
                                  proposal.voteYes,
                                  proposal.voteNo,
                                  proposal.voteAbstain,
                                  proposal.percentYes,
                                  proposal.percentNo,
                                  proposal.percentAbstain,
                                  proposal.currentStatus,
                                  proposal.categoryTitle,
                                  proposal.approval,
                                  proposal.reminder
                                  ))

                return db.cursor.lastrowid

        except Exception as e:
            logger.error("addProposal ", exc_info=e)

        return None

    def updateProposal(self, proposal):

        try:

            with self.connection as db:
                query = "UPDATE proposals SET \
                        proposalKey=?, \
                        title=?,\
                        url=?,\
                        summary=?,\
                        owner=?,\
                        amountSmart=?,\
                        amountUSD=?,\
                        installment=?,\
                        createdDate=?,\
                        votingDeadline=?,\
                        status=?,\
                        voteYes=?,\
                        voteNo=?,\
                        voteAbstain=?,\
                        percentYes=?,\
                        percentNo=?,\
                        percentAbstain=?,\
                        currentStatus=?,\
                        categoryTitle=?, \
                        approval=?,\
                        reminder=?,\
                        twitter=?,\
                        reddit=?,\
                        gab=?,\
                        discord=? \
                        WHERE proposalId=?"

                db.cursor.execute(query, (
                                  proposal.proposalKey,
                                  proposal.title,
                                  proposal.url,
                                  proposal.summary,
                                  proposal.owner,
                                  proposal.amountSmart,
                                  proposal.amountUSD,
                                  proposal.installment,
                                  proposal.createdDate,
                                  proposal.votingDeadline,
                                  proposal.status,
                                  proposal.voteYes,
                                  proposal.voteNo,
                                  proposal.voteAbstain,
                                  proposal.percentYes,
                                  proposal.percentNo,
                                  proposal.percentAbstain,
                                  proposal.currentStatus,
                                  proposal.categoryTitle,
                                  proposal.approval,
                                  proposal.reminder,
                                  proposal.twitter,
                                  proposal.reddit,
                                  proposal.gab,
                                  proposal.discord,
                                  proposal.proposalId
                                  ))

                return db.cursor.rowcount

        except Exception as e:
            logger.error("updateProposal ", exc_info=e)

        return None

    def getProposals(self):

        proposals = None

        with self.connection as db:
            db.cursor.execute("SELECT * FROM proposals order by proposalId")
            proposals = db.cursor.fetchall()

        return proposals

    def getProposal(self, proposalId):

        proposal = None

        with self.connection as db:

            db.cursor.execute("SELECT * FROM proposals where proposalId=? order by proposalId",[proposalId])
            proposal = db.cursor.fetchone()

        return proposal

    def reset(self):

        sql = '\
        BEGIN TRANSACTION;\
        CREATE TABLE "proposals" (\
        	`proposalId` INTEGER NOT NULL PRIMARY KEY,\
            `proposalKey` TEXT,\
        	`title`	TEXT,\
        	`url` TEXT,\
        	`summary`	TEXT,\
        	`owner` TEXT,\
        	`amountSmart` REAL,\
        	`amountUSD`	REAL,\
        	`installment`	INTEGER,\
            `createdDate` TEXT,\
            `votingDeadline` TEXT,\
            `status` TEXT,\
            `voteYes` REAL,\
            `voteNo` REAL,\
            `voteAbstain` REAL,\
            `percentYes` REAL,\
            `percentNo` REAL,\
            `percentAbstain` REAL,\
            `currentStatus` TEXT,\
            `categoryTitle` TEXT,\
            `approval` INTEGER,\
            `reminder` INTEGER,\
            `twitter` INTEGER,\
            `reddit` INTEGER,\
            `gab` INTEGER,\
            `discord` INTEGER\
        );\
        COMMIT;'

        with self.connection as db:
            db.cursor.executescript(sql)
