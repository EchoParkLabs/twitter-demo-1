import os
import tweepy
import requests
import shapely.geometry
import tempfile

from osgeo import gdal

from datetime import date
from datetime import datetime
from epl.imagery.reader import Landsat, Metadata, MetadataService, SpacecraftID, Band, DataType

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
dataset = landsat.get_dataset(band_definitions=band_numbers,
                              output_type=DataType.BYTE,
                              scale_params=scaleParams,
                              extent=taos_shape.bounds)

print("create")
temp = tempfile.NamedTemporaryFile(suffix=".jpg")
dataset_translated = gdal.Translate(temp.name, dataset, format='JPEG', noData=0)
# TODO if dataset_translasted is super larged, add xRes and yRes to shrink image. no idea what largest size is yet
del dataset
print("gdal finished")
temp.flush()
d = datetime.now()
date_string = "run time: " + d.isoformat()
api.update_with_media(temp.name, status=date_string)
temp.close()
del dataset_translated


print("posted to twitter")


