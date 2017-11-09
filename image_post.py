import os
import tweepy
import requests
import shapely.geometry
import tempfile
import math
import boto3

from osgeo import gdal

from datetime import date
from datetime import datetime
from epl.imagery.reader import Landsat, Metadata, MetadataService, SpacecraftID, Band, DataType


# Create SQS client
sqs = boto3.client('sqs')

# List SQS queues
response = sqs.list_queues()

print(response['QueueUrls'])

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

landsat = Landsat(metadataset[0])

# get a numpy.ndarray from bands for specified imagery
band_numbers = [Band.NIR, Band.SWIR1, Band.SWIR2, Band.ALPHA]
scaleParams = [[0.0, 40000], [0.0, 40000], [0.0, 40000]]
extent = taos_shape.bounds
dataset = landsat.get_dataset(band_definitions=band_numbers,
                              output_type=DataType.BYTE,
                              scale_params=scaleParams)

x_src_size = dataset.RasterXSize
y_src_size = dataset.RasterYSize

resolution = 60
max_pixels = 12960000.0
if x_src_size * y_src_size > max_pixels:
    size_scale = max_pixels / (x_src_size * y_src_size)
    resolution = resolution + resolution * size_scale
    del dataset
    dataset = landsat.get_dataset(band_definitions=band_numbers,
                                  output_type=DataType.BYTE,
                                  scale_params=scaleParams,
                                  xRes=resolution,
                                  yRes=resolution)

print("create")
temp = tempfile.NamedTemporaryFile(suffix=".jpg")
dataset_translated = gdal.Translate(temp.name, dataset, format='JPEG', noData=0)
# TODO if dataset_translasted is super larged, add xRes and yRes to shrink image. no idea what largest size is yet
del dataset
print("gdal finished")
temp.flush()
d = datetime.now()
date_string = "run time: " + d.isoformat()
# TODO this fails at dateline
lat = extent[1] + math.fabs(extent[1] - extent[3]) / 2.0
lon = extent[0] + math.fabs(extent[0] - extent[2]) / 2.0
api.update_with_media(temp.name, status=date_string, lat=lat, lon=lon)
temp.close()
del dataset_translated


print("posted to twitter")


