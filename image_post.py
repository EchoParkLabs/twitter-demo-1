import os
from TwitterAPI import TwitterAPI
from epl.imagery.reader import Landsat, Metadata

cons_key = os.environ['CONSUMER_KEY_API']
cons_secret = os.environ['CONSUMER_SECRET_API']
access_token = os.environ['ACCESS_TOKEN']
access_secret = os.environ['ACCESS_TOKEN_SECRET']

api = TwitterAPI(cons_key, cons_secret, access_token, access_secret)

r = api.request('statuses/update', {'status':'This is a tweet!'})
print(r.status_code)
# png = "./trace1.png"

print("hello twitter")
