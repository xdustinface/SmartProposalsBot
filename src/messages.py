#!/usr/bin/env python3

def splitMessage(text, split, maximum):

    # When the message is longer then the max allowed size
    # split it at double linebreaks to make sure its well readable
    # when the message comes in parts.
    if len(text) > maximum:

        parts = []

        searchIndex = 0

        while True:

            if len(text[searchIndex:]) <= maximum:
                parts.append(text[searchIndex:])
                break

            splitIndex = text.rfind(split,searchIndex,maximum + searchIndex)

            if searchIndex == 0 and splitIndex == -1:
                # If there is no split string, split it just at the
                # length limit.
                parts = [text[i:i + limit] for i in range(0, len(text), maximum)]
                break
            elif searchIndex != 0 and splitIndex == -1:
                # If there was a split string in the message but the
                # next part of the message hasnt one split the rest of the message
                # at the length limit if its still exceeds it.
                parts.extend([text[i:i + maximum] for i in range(searchIndex, len(text), maximum)])
            elif splitIndex != -1:
                # Found a sweet spot to to split
                parts.append(text[searchIndex:splitIndex])
                searchIndex = splitIndex
            else:
                logger.warning("Split whatever..")
                # ...

        return parts

    else:
        return [text]

def removeMarkdown(text):
    clean = text.replace('_','')
    clean = clean.replace('*','')
    clean = clean.replace('`','')
    return clean

def markdown(text,messenger):

    msg = text.replace('<c>','`')

    if messenger == 'telegram':
        msg = msg.replace('<b>','*')
        msg = msg.replace('<u>','')
        msg = msg.replace('<cb>','/')
        msg = msg.replace('<ca>','')
        msg = msg.replace('<c>','`')
        msg = msg.replace('<i>','')
    elif messenger == 'discord':
        msg = msg.replace('<u>','__')
        msg = msg.replace('<i>','*')
        msg = msg.replace('<b>','**')
        msg = msg.replace('<cb>','`')
        msg = msg.replace('<ca>','`')

    return msg

def link(messenger, link, text = ''):

    msg = link

    if messenger == 'telegram':
        msg = "[{}]({})".format(text,link)
    elif messenger == 'discord':
        msg = "<{}>".format(link)

    return msg

def help(messenger):

    helpMsg =  ("This bot will allow you to:\n"
                " <b>-<b> Subscribe for notifications about new/ending ")
    helpMsg +=  "proposals on the voting portal: " + link(messenger,"https://vote.smartcash.cc") + "\n"
    helpMsg += (" <b>-<b> Add proposals to your watchlist and receive notifications when their "
                "voting state changed\n"
                " <b>-<b> Check the open proposals\n"
                " <b>-<b> Read the summary of specific proposals\n"
                " <b>-<b> More...check out the command below!\n\n"
                "<b>Commands (DM + Public)<b>\n\n"
                "<cb>help<ca> - Print this help.\n"
                "<cb>open<ca> - Print a list of all proposals that are open to vote.\n"
                "<cb>latest<ca> - Print the last recent proposal.\n"
                "<cb>passing<ca> - Print the open proposals with currently more YES votes.\n"
                "<cb>failing<ca> - Print the open proposals with currently more NO votes.\n"
                "<cb>detail<ca> <b>:id<b> - Print the summary of a specific proposal. Replace <b>:id<b> with the proposal id! Example: <cb>detail #202<ca>\n\n"
                "<b>Command (DM only)<b>\n\n"
                "<cb>subscribe<ca> - Subscribe notifications about new/ended proposals.\n"
                "<cb>unsubscribe<ca> - Unsubscribe the notifications about new/ended proposals.\n"
                "<cb>add<ca> <b>:id<b> - Add a proposal to your watchlist. Replace <b>:id<b> with the proposal id! Example: <cb>add #202<ca>\n"
                "<cb>remove<ca> <b>:id<b> - Remove a proposal from your watchlist. Replace <b>:id<b> with the proposal id Example: <cb>remove #202<ca>\n"
                "<cb>watchlist<ca> - Print all proposals on your watchlist\n\n")

    helpMsg = markdown(helpMsg, messenger)

    return helpMsg


############################################################
#                      Common messages                     #
############################################################
def proposalShort(messenger, proposal):

    message = ""

    power = proposal.voteYes + proposal.voteNo + proposal.voteAbstain

    message += "<u><b> #{} - {}<b><u>\n\n".format(proposal.proposalId, removeMarkdown(proposal.title))
    message += "<b>Owner<b> {}\n".format(removeMarkdown(proposal.owner))
    message += "<b>Requested [USD]<b> {:,}\n".format(round(proposal.amountUSD,1))
    message += "<b>Requested [SMART]<b> {:,} SMART\n\n".format(round(proposal.amountSmart,1))
    message += "<b>Remaining time<b> {}\n".format(proposal.remainingString())
    message += "<b>YES<b> {}%\n".format(proposal.percentYesString())
    message += "<b>NO<b> {}%\n".format(proposal.percentNoString())
    message += "<b>ABSTAIN<b> {}%\n".format(proposal.percentAbstainString())
    message += "<b>Voting power<b> {:,} SMART\n".format(int(power))
    message += link(messenger, "https://vote.smartcash.cc/Proposal/Details/{}".format(proposal.url),'Open the proposal!')
    message += "\n\n"

    return markdown(message,messenger)

def proposalDetail(messenger, proposal):

    message = ""

    power = proposal.voteYes + proposal.voteNo + proposal.voteAbstain

    message += "<u><b>#{} - {}<b><u>\n\n".format(proposal.proposalId, removeMarkdown(proposal.title))
    message += "<b>Owner<b>: {}\n\n".format(removeMarkdown(proposal.owner))
    message += "<b>Requested [USD]<b> {:,}\n".format(round(proposal.amountUSD,1))
    message += "<b>Requested [SMART]<b> {:,}\n\n".format(round(proposal.amountSmart,1))
    message += "<b>Created at<b> {}\n".format(proposal.createdString())
    message += "<b>Voting ends at<b> {}\n".format(proposal.deadlineString())
    message += "<b>Remaining time<b> {}\n\n".format(proposal.remainingString())
    message += "<i>{}<i>\n\n".format(removeMarkdown(proposal.summary))
    message += "<b>Current state percental<b>\n"
    message += "<b>YES<b> {}%\n".format(proposal.percentYesString())
    message += "<b>NO<b> {}%\n".format(proposal.percentNoString())
    message += "<b>ABSTAIN<b> {}%\n\n".format(proposal.percentAbstainString())
    message += "<b>Current voting power<b>\n"
    message += "<b>YES<b> {:,} SMART\n".format(round(proposal.voteYes,1))
    message += "<b>NO<b> {:,} SMART\n".format(round(proposal.voteNo,1))
    message += "<b>ABSTAIN<b> {:,} SMART\n\n".format(round(proposal.voteAbstain,1))
    message += "<b>Voting power<b> {:,} SMART\n\n".format(int(power))
    message += link(messenger, "https://vote.smartcash.cc/Proposal/Details/{}".format(proposal.url),'Open the proposal!')
    message += "\n\n"

    return markdown(message,messenger)

def welcome(messenger):
    message =  ":boom: <u><b>Welcome<b><u> :boom:\n\n"
    message += "You can use me to receive notifications about new/ended proposals or "
    message += "add the proposals you like and want to follow to your watchlist here. "
    message += "This will allow me to send you updates when the voting distribution for any"
    message += " of the proposals on your watchlist obtains a change.\n\n"
    message += "You are on the subscription list! This means you will receive"
    message += " notifications about new/ending proposals from now on. If you dont"
    message += " like it send me <cb>unsubscribe<ca> to disable it.\n\n"
    message += "To get more info about all my available commands send me <c>help<c>\n\n"
    message += "If you want to support my creator, its @dustinface#6318 :v:\n\n"
    message += ":coffee: & :beer: => <b>STsDhYJZZrVFCaA5FX2AYWP27noYo3RUjD<b>\n\n\n"
    message += "<u>You may also want to check this out<u>\n\n" + link(messenger,"https://steemit.com/smartcash/@dustinface/smarthive-voting-automation-script")
    message += "\n\nIt will allow you to vote with all addresses of your wallet in one shot.\n\n"

    return markdown(message, messenger)

############################################################
#                      User messages                       #
############################################################

def publishedProposalNotification(messenger, proposal):

    message = "<u><b>:boom: We have a new proposal :boom:<b><u>\n\n"

    message += "<u><b>#{} - {}<b><u>\n\n".format(proposal.proposalId, removeMarkdown(proposal.title))
    message += "<b>Owner<b>: {}\n".format(removeMarkdown(proposal.owner))
    message += "<b>Requested [USD]<b> {:,}\n".format(round(proposal.amountUSD,1))
    message += "<b>Requested [SMART]<b> {:,}\n\n".format(round(proposal.amountSmart,1))
    message += "<i>{}<i>\n\n".format(removeMarkdown(proposal.summary))
    message += link(messenger, "https://vote.smartcash.cc/Proposal/Details/{}".format(proposal.url),'Open the proposal!')
    message += "\n\n"

    message += "<u><b>Beee SMART and VOTE!<b><u>\n\n"

    return markdown(message, messenger)

def reminderProposalNotification(messenger, proposal):

    message = "<u><b>:exclamation: 24 hours left :exclamation:<b><u>\n\n"

    message += "<b>#{} - {}<b>\n\n".format(proposal.proposalId, removeMarkdown(proposal.title))
    message += "Be part of the community and cast your votes!\n\n"
    message += link(messenger, "https://vote.smartcash.cc/Proposal/Details/{}".format(proposal.url),'Open the proposal!')
    message += "\n\n"

    return markdown(message, messenger)

def endedProposalNotification(messenger, proposal):

    message = "<u><b>Proposal ended!<b><u>\n\n"

    message += "<u><b>#{} - {}<b><u>\n\n".format(proposal.proposalId, removeMarkdown(proposal.title))

    if proposal.allocated():
        result = ":tada: Allocated :tada:"
    else:
        result = proposal.status

    message += "<b>Result<b> {}\n\n".format(result)

    message += link(messenger, "https://vote.smartcash.cc/Proposal/Details/{}".format(proposal.url),'Open the proposal!')
    message += "\n\n"

    return markdown(message, messenger)


############################################################
#                     Warning messages                     #
############################################################


############################################################
#                     Error messages                       #
############################################################

def noWatchlistEntry(messenger):
    return markdown(("<b>ERROR<b>: You have currently no proposals on your watchlist. "
                         "You can add some with the <cb>add<ca> command."),messenger)

def rateLimitError(messenger, seconds):
    return markdown("<b>Sorry, you hit the rate limit. Take a deep breath...\n\n{} to go!<b>".format(seconds),messenger)

def proposalIsOnWatchlist(messenger, title):
    clean = removeMarkdown(title)
    return markdown("<b>ERROR<b>: The proposal <b>{}<b> is already on your watchlist!\n".format(clean),messenger)

def proposalIsNotOnWatchlist(messenger, title):
    clean = removeMarkdown(title)
    return markdown("<b>ERROR<b>: The proposal <b>{}<b> is not on your watchlist!\n".format(clean),messenger)

def proposalIdRequired(messenger, command):
    return markdown(("<b>ERROR<b>: The proposal's ID is required as arument. You can see the ID's  with the foregoing #in the proposal list.\n\n"
                     "Example: <cb>{} 200<ca>".format(command)),messenger)

def invalidProposalId(messenger, id):
    clean = removeMarkdown(id)
    return markdown("<b>ERROR<b>: The given proposal ID <b>{}<b> is invalid. You can see the ID's with the foregoing # in the proposal list.\n".format(clean),messenger)

def proposalNotFound(messenger, id):
    clean = removeMarkdown(id)
    return markdown("<b>ERROR<b>: The proposal with the ID - <b>{}<b> - could not be found. If you know its there contact the team!\n".format(clean),messenger)

def notAvailableInGroups(messenger):
    return markdown("<b>Sorry, this command is not available in groups.<b>\n\nClick here @SmartProposals",messenger)

def unexpectedError(messenger):
    return markdown("<b>Unexpected error. Contact the team!<b>",messenger)
