import os
import tweepy
import requests
import tempfile
import math
import boto3
import json
import re
import random
import shapefile

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


wrs2 = shapefile.Reader("/.epl/metadata/county-borders/cb_2016_us_county_500k/cb_2016_us_county_500k.shp")
records = wrs2.records()
"""('DeletionFlag', 'C', 1, 0)
['STATEFP', 'C', 2, 0]
['COUNTYFP', 'C', 3, 0]
['COUNTYNS', 'C', 8, 0]
['AFFGEOID', 'C', 14, 0]
['GEOID', 'C', 5, 0]
['NAME', 'C', 100, 0]
['LSAD', 'C', 2, 0]
['ALAND', 'N', 14, 0]
['AWATER', 'N', 14, 0]"""
county_idx = None
state_idx = None
for idx, field in enumerate(wrs2.fields):
    if field[0] == "STATEFP":
        state_idx = idx - 1
    elif field[0] == "NAME":
        county_idx = idx - 1

state_county_map = {}

for idx, record in enumerate(records):
    county_num = record[county_idx]
    # state_num = record[state_idx]
    #
    # if state_num not in state_county_map:
    #     state_county_map[state_num] = {}

    state_county_map[county_num] = shape(wrs2.shape(idx).__geo_interface__)

cons_key = os.environ['CONSUMER_KEY_API']
cons_secret = os.environ['CONSUMER_SECRET_API']
access_token = os.environ['ACCESS_TOKEN']
access_secret = os.environ['ACCESS_TOKEN_SECRET']
shortner_key = os.environ['GOOGLE_URL_SHORTENER_KEY']
geocode_key = os.environ['GOOGLE_GEOCODE_KEY']

tweet_count = 0
while tweet_count < 10:
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

    auth = tweepy.OAuthHandler(cons_key, cons_secret)
    auth.set_access_token(access_token, access_secret)

    api = tweepy.API(auth)

    for path_name in path_names:
        print(path_name)
        metadata = Metadata(path_name)

        if metadata.cloud_cover > 30:
            continue

        d = datetime.now()
        delta = d - metadata.sensing_time
        if delta.days > 1:
            continue

        # TODO, o my god, this needs a spatial index, but I'm just slamming things together.
        county_name = None
        county_geometry = None
        image_extent = shape(metadata.get_wrs_polygon())
        for county in state_county_map:
            if image_extent.contains(state_county_map[county]):
                county_name = county
                county_geometry = state_county_map[county]

        if county_name is None:
            continue

        landsat = Landsat(metadata)

        # get a numpy.ndarray from bands for specified imagery
        band_numbers = [Band.NIR, Band.SWIR1, Band.SWIR2, Band.ALPHA]
        scaleParams = [[0.0, 40000], [0.0, 40000], [0.0, 40000]]
        resolution = 60
        dataset = landsat.get_dataset(band_definitions=band_numbers,
                                      output_type=DataType.BYTE,
                                      scale_params=scaleParams,
                                      extent=county_geometry.bounds,
                                      cutline_wkb=county_geometry.wkb,
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
                                          extent=county_geometry.bounds,
                                          cutline_wkb=county_geometry.wkb,
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

        seconds = delta.total_seconds()
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        date_string = "hours & minutes since acquired: {0}:{1}".format(h, str(m).zfill(2))
        # TODO this fails at dateline
        center = county_geometry.centroid
        # center = shape(metadata.get_wrs_polygon()).centroid
        zoom_level = 9
        #                  https://www.google.com/maps/@?api=1&map_action=map&center=-33.712206,150.311941&zoom=12&basemap=terrain
        google_maps_url = "https://www.google.com/maps/@?api=1&map_action=map&center={0},{1}&zoom={2}&basemap=terrain".format(center.y, center.x, zoom_level)

        # TODO shorten url because of stupid twitter bug https://github.com/twitter/twitter-text/issues/201
        shortener = "https://www.googleapis.com/urlshortener/v1/url?key={0}".format(shortner_key)
        response_shortner = requests.post(shortener, json={"longUrl": google_maps_url})
        if response_shortner.status_code == 200:
            short_url = json.loads(response_shortner.text)["id"]
        else:
            short_url = ""

        # TODO twitter wouldn't allow any more searches
        # result_geocode = api.reverse_geocode(long=center.x, lat=center.y)
        # geocode_name = result_geocode[0].full_name
        geocode_url = "https://maps.googleapis.com/maps/api/geocode/json?latlng={0},{1}&key={2}".format(center.y,
                                                                                                        center.x,
                                                                                                        geocode_key)
        geocode_response = requests.get(geocode_url)
        if geocode_response.status_code == 200:
            response_obj = json.loads(geocode_response.text)['results']
            idx = -4
            if len(response_obj) < 4:
                idx = -1 * len(response_obj)
            geocode_name = response_obj[idx]['formatted_address']
        else:
            geocode_name = county_name

        place_name = "\n" + geocode_name + "\n"

        msg = date_string + place_name + short_url
        upload = api.media_upload(temp.name)
        media_ids = [upload.media_id_string]
        res = api.update_status(media_ids=media_ids,
                                status=msg,
                                long=center.x,
                                lat=center.y)
        tweet_count += 1
        temp.close()

    # TODO only delete those that have been successfully posted
    sqs.delete_message_batch(QueueUrl=response['QueueUrls'][0], Entries=batch_delete)
