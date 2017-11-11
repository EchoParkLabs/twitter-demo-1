import os
import tweepy
import requests
import shapely.geometry
import tempfile
import math
import boto3
import json
import re
import random

from shapely.geometry import shape
from osgeo import gdal

from datetime import datetime
from epl.imagery.reader import Landsat, Metadata, Band, DataType

r = re.compile(r'LC08_L1GT_[\d]+_[\d]+_[\d]+_[\d]+_[\w]+')

# Create SQS client
sqs = boto3.client('sqs')

# List SQS queues
response = sqs.list_queues()

print(response['QueueUrls'][0])
messages = sqs.receive_message(QueueUrl=response['QueueUrls'][0],
                               AttributeNames=['ApproximateFirstReceiveTimestamp'],
                               MaxNumberOfMessages=10)

path_names = []
batch_delete = []
for message in messages['Messages']:
    sns_content = json.loads(message['Body'])
    sns_messages = json.loads(sns_content['Message'])
    # TODO assumes there's only one record per sns entry in sqs.
    image_key = sns_messages['Records'][0]['s3']['object']['key']
    sqs_entry = {'Id': message['MessageId'], 'ReceiptHandle': message['ReceiptHandle']}
    batch_delete.append(sqs_entry)
    #  if the file is not the
    if not image_key.endswith("index.html"):
        continue

    path_name = '/imagery/' + os.path.dirname(image_key)
    basename = os.path.basename(path_name)
    if r.search(basename):
        continue
    else:
        path_names.append(path_name)

cons_key = os.environ['CONSUMER_KEY_API']
cons_secret = os.environ['CONSUMER_SECRET_API']
access_token = os.environ['ACCESS_TOKEN']
access_secret = os.environ['ACCESS_TOKEN_SECRET']
shortner_key = os.environ['GOOGLE_URL_SHORTENER_KEY']

auth = tweepy.OAuthHandler(cons_key, cons_secret)
auth.set_access_token(access_token, access_secret)

api = tweepy.API(auth)

for path_name in path_names:
    print(path_name)
    metadata = Metadata(path_name)

    landsat = Landsat(metadata)

    # get a numpy.ndarray from bands for specified imagery
    band_numbers = [Band.NIR, Band.SWIR1, Band.SWIR2, Band.ALPHA]
    scaleParams = [[0.0, 40000], [0.0, 40000], [0.0, 40000]]
    resolution = 60
    dataset = landsat.get_dataset(band_definitions=band_numbers,
                                  output_type=DataType.BYTE,
                                  scale_params=scaleParams,
                                  xRes=resolution,
                                  yRes=resolution)

    x_src_size = dataset.RasterXSize
    y_src_size = dataset.RasterYSize

    # This example assumes that the above get_dataset is using xRes=60, yRes=60
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
    del dataset_translated

    d = datetime.now()
    date_string = "run time: " + d.isoformat()
    # TODO this fails at dateline
    center = shape(metadata.get_wrs_polygon()).centroid
    zoom_level = 8
    #                  https://www.google.com/maps/@?api=1&map_action=map&center=-33.712206,150.311941&zoom=12&basemap=terrain
    google_maps_url = "https://www.google.com/maps/@?api=1&map_action=map&center={0},{1}&zoom={2}&basemap=terrain".format(center.y, center.x, zoom_level)

    # TODO shorten url because of stupid twitter bug https://github.com/twitter/twitter-text/issues/201
    shortener = "https://www.googleapis.com/urlshortener/v1/url?key={0}".format(shortner_key)
    r = requests.post(shortener, json={"longUrl": google_maps_url})
    if r.status_code == 200:
        short_url = json.loads(r.text)["id"]
    else:
        short_url = ""

    place_name = "\n"
    try:
        result_geocode = api.reverse_geocode(long=center.x, lat=center.y)
        place_name = "\n" + result_geocode[0].full_name + "\n"
    except:
        print("reverse_geocode error")

    msg = date_string + place_name + short_url
    upload = api.media_upload(temp.name)
    media_ids = [upload.media_id_string]
    res = api.update_status(media_ids=media_ids,
                            status=msg,
                            long=center.x,
                            lat=center.y)

    temp.close()

# TODO only delete those that have been successfully posted
sqs.delete_message_batch(QueueUrl=response['QueueUrls'][0], Entries=batch_delete)
