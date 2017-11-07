import os
import tweepy
import requests
import shapely.geometry

from datetime import date
from epl.imagery.reader import Landsat, Metadata, MetadataService, SpacecraftID, Band

cons_key = os.environ['CONSUMER_KEY_API']
cons_secret = os.environ['CONSUMER_SECRET_API']
access_token = os.environ['ACCESS_TOKEN']
access_secret = os.environ['ACCESS_TOKEN_SECRET']

auth = tweepy.OAuthHandler(cons_key, cons_secret)
auth.set_access_token(access_token, access_secret)

api = tweepy.API(auth)

r = requests.get("https://raw.githubusercontent.com/johan/world.geo.json/master/countries/USA/NM/Taos.geo.json")
taos_geom = r.json()

taos_shape = shapely.geometry.shape(taos_geom['features'][0]['geometry'])

metadata_service = MetadataService()

d_start = date(2017, 3, 12) # 2017-03-12
d_end = date(2017, 3, 19) # 2017-03-20, epl api is inclusive

sql_filters = ['collection_number="PRE"']
rows = metadata_service.search(
    SpacecraftID.LANDSAT_8,
    start_date=d_start,
    end_date=d_end,
    bounding_box=taos_shape.bounds,
    limit=10,
    sql_filters=sql_filters)

base_mount_path = '/imagery'

metadataset = []
for row in rows:
    metadataset.append(Metadata(row, base_mount_path))

landsat = Landsat(metadataset)

# get a numpy.ndarray from bands for specified imagery
band_numbers = [Band.RED, Band.GREEN, Band.BLUE]
scaleParams = [[0.0, 40000], [0.0, 40000], [0.0, 40000]]
nda = landsat.fetch_imagery_array(band_numbers, scaleParams, extent=taos_shape.bounds)
#
# png = "./trace1.png"
# # api.update_status('tweepy + oauth! 4')
# api.update_with_media(png, status="words")

print("hello twitter")

