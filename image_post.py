import os
import tweepy
import requests
import tempfile
import boto3
import json
import re
import sys
import math
import time


import shapefile
import shapely.geometry.polygon

from shapely.geometry import shape
from osgeo import gdal

from datetime import datetime
from epl.imagery.reader import Landsat, Metadata, Band, DataType

r = re.compile(r'LC08_L1GT_[\d]+_[\d]+_[\d]+_[\d]+_[\w]+')

# Create SQS client
sqs = boto3.client('sqs')

# List SQS queues
# response = sqs.list_queues()
#
# print(response['QueueUrls'][0])


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

STATE_COUNTY_MAP = {}

for idx, record in enumerate(records):
    county_num = record[county_idx]
    # state_num = record[state_idx]
    #
    # if state_num not in STATE_COUNTY_MAP:
    #     STATE_COUNTY_MAP[state_num] = {}

    STATE_COUNTY_MAP[county_num] = shape(wrs2.shape(idx).__geo_interface__)

CONS_KEY = os.environ['CONSUMER_KEY_API']
CONS_SECRET = os.environ['CONSUMER_SECRET_API']
ACCESS_TOKEN = os.environ['ACCESS_TOKEN']
ACCESS_SECRET = os.environ['ACCESS_TOKEN_SECRET']
SHORTNER_KEY = os.environ['GOOGLE_URL_SHORTENER_KEY']
geocode_key = os.environ['GOOGLE_GEOCODE_KEY']

MAX_TWITTER_PIXELS_JPEG = 6000000.0
METERS_PER_PIXEL = 30.0

MAX_ZOOM = 15

QUEUE_URL = "https://us-west-2.queue.amazonaws.com/495706002520/landsat-aws-available"

SCALE_PARAMS = [[0.0, 26214.0], [0.0, 26214.0], [0.0, 26214.0]]


def post_image(metadata: Metadata, date_string, api, county_geometry: shapely.geometry.polygon=None):
    county_bounds = None if not county_geometry else county_geometry.bounds
    county_wkb =  None if not county_geometry else county_geometry.wkb
    wrs_geometry = shape(metadata.get_wrs_polygon())
    landsat = Landsat(metadata)

    # get a numpy.ndarray from bands for specified imagery
    band_numbers = [Band.NIR, Band.SWIR1, Band.SWIR2, Band.ALPHA]

    dataset = landsat.get_dataset(band_definitions=band_numbers,
                                  output_type=DataType.BYTE,
                                  scale_params=SCALE_PARAMS,
                                  extent=county_bounds,
                                  cutline_wkb=county_wkb,
                                  xRes=METERS_PER_PIXEL,
                                  yRes=METERS_PER_PIXEL)

    x_src_size = float(dataset.RasterXSize)
    y_src_size = float(dataset.RasterYSize)

    # black area will be compressed in jpeg, this allows us to up the max_pixels for county images
    if county_geometry:
        area_ratio = county_geometry.envelope.area / county_geometry.area
    else:
        area_ratio = wrs_geometry.envelope.area / wrs_geometry.area

    max_pixels = MAX_TWITTER_PIXELS_JPEG * area_ratio
    resolution = METERS_PER_PIXEL
    if x_src_size * y_src_size > max_pixels:
        side_scale = math.sqrt(x_src_size * y_src_size) / math.sqrt(max_pixels)
        resolution = METERS_PER_PIXEL * side_scale
        del dataset
        dataset = landsat.get_dataset(band_definitions=band_numbers,
                                      output_type=DataType.BYTE,
                                      scale_params=SCALE_PARAMS,
                                      extent=county_bounds,
                                      cutline_wkb=county_wkb,
                                      xRes=resolution,
                                      yRes=resolution)

    print("create")
    temp = tempfile.NamedTemporaryFile(suffix=".jpg")
    dataset_translated = gdal.Translate(temp.name, dataset, format='JPEG', noData=0)
    del dataset
    print("gdal finished")
    temp.flush()
    del dataset_translated

    file_size = os.path.getsize(temp.name) / 1024
    if file_size > 3072:
        ratio = file_size / 3072
        resolution = resolution * ratio
        dataset = landsat.get_dataset(band_definitions=band_numbers,
                                      output_type=DataType.BYTE,
                                      scale_params=SCALE_PARAMS,
                                      extent=county_bounds,
                                      cutline_wkb=county_wkb,
                                      xRes=resolution,
                                      yRes=resolution)
        print("create again")
        temp = tempfile.NamedTemporaryFile(suffix=".jpg")
        dataset_translated = gdal.Translate(temp.name, dataset, format='JPEG', noData=0)
        del dataset
        print("gdal finished again")
        temp.flush()
        del dataset_translated


    # TODO this fails at dateline
    center = county_geometry.centroid if county_geometry else shape(metadata.get_wrs_polygon()).centroid

    zoom_level = 9
    if county_geometry:
        ratio = int(round(math.sqrt(wrs_geometry.envelope.area) / math.sqrt(county_geometry.envelope.area)))
        zoom_level += int(math.floor(math.sqrt(ratio)))
        if zoom_level >= MAX_ZOOM:
            zoom_level = MAX_ZOOM

    #                  https://www.google.com/maps/@?api=1&map_action=map&center=-33.712206,150.311941&zoom=12&basemap=terrain
    google_maps_url = "https://www.google.com/maps/@?api=1&map_action=map&center={0},{1}&zoom={2}&basemap=terrain". \
        format(center.y, center.x, zoom_level)

    # shorten url because of stupid twitter bug https://github.com/twitter/twitter-text/issues/201
    shortener = "https://www.googleapis.com/urlshortener/v1/url?key={0}".format(SHORTNER_KEY)
    response_shortner = requests.post(shortener, json={"longUrl": google_maps_url})
    if response_shortner.status_code == 200:
        short_url = json.loads(response_shortner.text)["id"]
    else:
        short_url = ""

    geocode_url = "https://maps.googleapis.com/maps/api/geocode/json?latlng={0},{1}&key={2}".format(center.y,
                                                                                                    center.x,
                                                                                                    geocode_key)
    geocode_name = ""
    geocode_response = requests.get(geocode_url)
    if geocode_response.status_code == 200:
        response_obj = json.loads(geocode_response.text)['results']
        if len(response_obj) > 0:
            if county_geometry:
                idx = -4
            else:
                idx = -3

            if len(response_obj) < 4:
                idx = -1 * len(response_obj)
            geocode_name = response_obj[idx]['formatted_address']

    place_name = "\n" + geocode_name + "\n"

    msg = date_string + place_name + short_url
    print(os.path.getsize(temp.name) / 1024)
    upload = api.media_upload(temp.name)
    media_ids = [upload.media_id_string]
    res = api.update_status(media_ids=media_ids,
                            status=msg,
                            long=center.x,
                            lat=center.y)

    temp.close()
    return res


def main(argv):
    # wait until /imagery/c1 is a directory
    b_mounted = False
    while not b_mounted:
        if os.path.isdir("/imagery/c1"):
            sys.stdout.write("s3 is mounted\n")
            b_mounted = True
        time.sleep(2)

    tweet_count = 0
    while tweet_count < 1000:
        messages = sqs.receive_message(QueueUrl=QUEUE_URL,
                                       AttributeNames=['ApproximateFirstReceiveTimestamp'],
                                       MaxNumberOfMessages=10)
        bucket_posts = {}
        batch_delete = []
        if 'Messages' not in messages:
            break

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
                bucket_posts[path_name] = sns_messages['Records'][0]['eventTime']

        auth = tweepy.OAuthHandler(CONS_KEY, CONS_SECRET)
        auth.set_access_token(ACCESS_TOKEN, ACCESS_SECRET)

        api = tweepy.API(auth)

        for path_name in bucket_posts:
            sys.stdout.write("{0} path available\n".format(path_name))
            metadata = Metadata(path_name)

            if metadata.cloud_cover > 30:
                continue

            d = datetime.now()
            delta_sensed = d - metadata.sensing_time
            seconds_sensed = delta_sensed.total_seconds()
            h = int(seconds_sensed // 3600)
            m = int((seconds_sensed % 3600) // 60)
            date_string_1 = "hours since acquired: {0}:{1}".format(h, str(m).zfill(2))

            delta_processed = d - metadata.date_processed
            seconds_processed = delta_processed.total_seconds()
            h = int(seconds_processed // 3600)
            m = int((seconds_processed % 3600) // 60)
            date_string_2 = "hours since processed: {0}:{1}".format(h, str(m).zfill(2))

            delta_post_time = d - datetime.strptime(bucket_posts[path_name], "%Y-%m-%dT%H:%M:%S.%fZ")
            seconds_aws_post_time = delta_post_time.total_seconds()
            h = int(seconds_aws_post_time // 3600)
            m = int((seconds_aws_post_time % 3600) // 60)
            date_string_3 = "hours since posted to s3: {0}:{1}".format(h, str(m).zfill(2))

            if delta_sensed.days > 1:
                continue

            date_string = date_string_1 + '\n' + date_string_2 + '\n' + date_string_3

            # TODO, o my god, this needs a spatial index, but I'm just slamming things together.
            contained_counties = []
            image_extent = shape(metadata.get_wrs_polygon())
            for county in STATE_COUNTY_MAP:
                if image_extent.contains(STATE_COUNTY_MAP[county]):
                    contained_counties.append(county)

            # TODO testing scale in and scale out with data in sqs
            if len(contained_counties) == 0:
                continue

            # Post overview image
            post_image(metadata, date_string, api)
            tweet_count += 1
            for county_name in contained_counties:
                post_image(metadata, date_string, api, STATE_COUNTY_MAP[county_name])
                tweet_count += 1

        # TODO only delete those that have been successfully posted
        sqs.delete_message_batch(QueueUrl=QUEUE_URL, Entries=batch_delete)


if __name__ == "__main__":
    main(sys.argv)
