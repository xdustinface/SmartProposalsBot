import logging
import requests, json
import twitter
import praw
from enum import Enum

log = logging.getLogger("socialmedia")

class PublishResult(Enum):
    Success = 0
    AlreadyPosted = 1
    RateLimit = 2
    Error = 100

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

        result = {'status': PublishResult.Success, 'error': "" }

        send = self.api.PostUpdate

        if len(message) > 280:
            send = self.api.PostUpdates

        try:
            status = send(message)
            log.info("Tweeter: tweet - {}".format(status))
        except twitter.error.TwitterError as e:

            for error in e.message:

                if 'code' in error and error['code'] == 187:
                    log.error("Tweeter: tweet already posted")
                    result['status'] = PublishResult.AlreadyPosted
                    result['error'] = error['message'] if 'message' in error else str(error)
                else:
                    result['status'] = PublishResult.Error
                    result['error'] += " {}".format(str(error))

        except Exception as e:
            log.error("Tweeter: tweet failed", exc_info=e)
            result['status'] = PublishResult.Error
            result['error'] = str(e)
        else:
            log.info("Tweeter: tweet suceeded {}".format(message))
            pass

        return result

class Reddit(object):

    def __init__(self, clientId, clientSecret, password, userAgent, userName):
        log.info("Reddit: Init")

        self.api = praw.Reddit(client_id=clientId, client_secret=clientSecret,
                     password=password, user_agent=userAgent,
                     username=userName)

        log.info("Reddit: user - {}".format(self.api.user.me()))

    def submit(self, subreddit, **kwargs):

        result = {'status': PublishResult.Success, 'error': "" }

        try:
            self.api.subreddit(subreddit).submit(**kwargs)
        except praw.exceptions.APIException as e:
            log.error("Reddit: APIException - {}".format(e.error_type))
            result['status'] = PublishResult.RateLimit
            result['error'] = e.message
        except Exception as e:
            log.error("Reddit: submit", exc_info=e)
            result['status'] = PublishResult.Error
            result['error'] = str(e)
        else:
            log.info("Reddit: submit suceeded {}".format(str(kwargs)))
            pass

        return result

class Gab(object):

    def __init__(self, userName, password):
        log.info("Gab: Init")
        self.headers = {'user-agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:58.0) Gecko/20100101 Firefox/58.0'}
        result = requests.get('https://gab.ai/auth/login', headers=self.headers)
        self.session = result.cookies
        token = result.text.split('"_token" value="')[1].split('"')[0]
        self.session = requests.post('https://gab.ai/auth/login', headers=self.headers, cookies=self.session, data={'_token':token, 'password':password, 'username':userName}).cookies

    def post(self, body, category='', quote='', replies=True, media={}, gif='', nsfw=False, reply_to='', share_fb='', share_twitter='', topic=''):

        result = {'status': PublishResult.Success, 'error': "" }

        try:
            response = requests.post('https://gab.ai/posts', headers=self.headers, cookies=self.session, data={'_method':'post', 'body':body, 'category':category, 'gif':gif, 'is_premium':0, 'is_quote':quote, 'is_replies_disabled':not replies, 'media_attachments':media, 'nsfw':int(nsfw), 'reply_to':reply_to, 'share_facebook':share_fb, 'share_twitter':share_twitter, 'topic':topic})
        except Exception as e:
            log.error("Gab: post", exc_info=e)
            result['status'] = PublishResult.Error
            result['error'] = str(e)
        else:

            if response.status_code == 200:
                log.info("Gab: post suceeded {}".format(str(body)))
            else:
                err = "{} - {}".format(response.status_code, response.reason)
                log.error("Gab: post error {}")
                result['status'] = PublishResult.Error
                result['error'] = err

        return result

    def submit(self, subreddit, **kwargs):

        result = {'status': PublishResult.Success, 'error': "" }

        try:
            self.api.subreddit(subreddit).submit(**kwargs)
        except praw.exceptions.APIException as e:
            log.error("Reddit: APIException - {}".format(e.error_type))
            result['status'] = PublishResult.RateLimit
            result['error'] = e.message
        except Exception as e:
            log.error("Reddit: submit", exc_info=e)
            result['status'] = PublishResult.Error
            result['error'] = str(e)
        else:
            log.info("Reddit: submit suceeded {}".format(str(kwargs)))
            pass

        return result
