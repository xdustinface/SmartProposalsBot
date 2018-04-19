import logging
import twitter
import praw

log = logging.getLogger("socialmedia")

class Tweet(object):
    def __init__(self, data):

        for arg in data:
            setattr(self, arg, data[arg])

class Tweeter(object):

    def __init__(self, consumerKey, consumerSecret, accessToken, accessTokenSecret):
        log.info("Tweeter: Init")

        self.api = twitter.Api(consumer_key=consumerKey,
                               consumer_secret=consumerSecret,
                               access_token_key=accessToken,
                               access_token_secret=accessTokenSecret)

    def tweet(self, message, **kwargs):

        send = self.api.PostUpdates

        if len(message) > 280:
            send = self.api.PostUpdates

        status = self.api.PostUpdate(message)
        log.info("Tweeter: tweet - {}".format(status))

class Reddit(object):

    def __init__(self, clientId, clientSecret, password, userAgent, userName):
        log.info("Reddit: Init")
        
        self.api = praw.Reddit(client_id=clientId, client_secret=clientSecret,
                     password=password, user_agent=userAgent,
                     username=userName)

        def post(subreddit, message):
            self.api.subreddit(subreddit).submit(message, url='https://reddit.com')
