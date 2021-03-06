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


from typing import List
import shapefile
import shapely.geometry.polygon

from shapely.wkb import loads as wkb_loads
from shapely.geometry import shape
from osgeo import gdal

from datetime import datetime
from epl.native.imagery.reader import Landsat, Metadata, DataType, MetadataService, LandsatQueryFilters
from epl.native.imagery.metadata_helpers import Band, SpacecraftID
from epl.grpc.imagery import epl_imagery_pb2
# from epl.imagery.reader import Landsat, Metadata, Band, DataType

r = re.compile(r'LC08_L1GT_[\d]+_[\d]+_[\d]+_[\d]+_[\w]+')

# Create SQS client
sqs = boto3.client('sqs')

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
    county_name = record[county_idx]
    key = (county_name, record[state_idx])
    if county_name in STATE_COUNTY_MAP:
        print("{0}".format(county_name))
    else:
        STATE_COUNTY_MAP[key] = shape(wrs2.shape(idx).__geo_interface__)

TWITTER_CONSUMER_KEY_API = os.environ['TWITTER_CONSUMER_KEY_API']
TWITTER_CONSUMER_SECRET_API = os.environ['TWITTER_CONSUMER_SECRET_API']
TWITTER_ACCESS_TOKEN = os.environ['TWITTER_ACCESS_TOKEN']
TWITTER_SECRET = os.environ['TWITTER_SECRET']
GOOGLE_URL_SHORTNER_KEY = os.environ['GOOGLE_URL_SHORTENER_KEY']
GOOGLE_GEOCODE_KEY = os.environ['GOOGLE_GEOCODE_KEY']

MAX_TWITTER_PIXELS_JPEG = 6000000.0
METERS_PER_PIXEL = 30.0

MAX_ZOOM = 15

QUEUE_URL = "https://us-west-2.queue.amazonaws.com/495706002520/landsat-aws-available"

SCALE_PARAMS = [[0.0, 26214.0], [0.0, 26214.0], [0.0, 26214.0]]


def post_image(metadata_set: List[Metadata], 
               date_string, 
               api, 
               county_geometry: shapely.geometry.polygon=None):
    county_bounds = None if not county_geometry else county_geometry.bounds
    county_wkb = None if not county_geometry else county_geometry.wkb
    wrs_shape = wkb_loads(metadata_set[0].get_wrs_polygon())
    
    landsat = Landsat(metadata_set)

    # get a numpy.ndarray from bands for specified imagery
    band_numbers = [Band.NIR, Band.SWIR1, Band.SWIR2, Band.ALPHA]

    dataset = landsat.get_dataset(band_definitions=band_numbers,
                                  output_type=DataType.BYTE,
                                  scale_params=SCALE_PARAMS,
                                  envelope_boundary=county_bounds,
                                  polygon_boundary_wkb=county_wkb,
                                  spatial_resolution_m=METERS_PER_PIXEL)

    x_src_size = float(dataset.RasterXSize)
    y_src_size = float(dataset.RasterYSize)

    # black area will be compressed in jpeg, this allows us to up the max_pixels for county images
    if county_geometry:
        area_ratio = county_geometry.envelope.area / county_geometry.area
    else:
        area_ratio = wrs_shape.envelope.area / wrs_shape.area

    max_pixels = MAX_TWITTER_PIXELS_JPEG * area_ratio
    resolution = METERS_PER_PIXEL
    if x_src_size * y_src_size > max_pixels:
        side_scale = math.sqrt(x_src_size * y_src_size) / math.sqrt(max_pixels)
        resolution = METERS_PER_PIXEL * side_scale
        del dataset
        dataset = landsat.get_dataset(band_definitions=band_numbers,
                                      output_type=DataType.BYTE,
                                      scale_params=SCALE_PARAMS,
                                      envelope_boundary=county_bounds,
                                      polygon_boundary_wkb=county_wkb,
                                      spatial_resolution_m=resolution)

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
        resolution = math.ceil(resolution * ratio)
        dataset = landsat.get_dataset(band_definitions=band_numbers,
                                      output_type=DataType.BYTE,
                                      scale_params=SCALE_PARAMS,
                                      envelope_boundary=county_bounds,
                                      polygon_boundary_wkb=county_wkb,
                                      spatial_resolution_m=resolution)
        print("create again")
        temp = tempfile.NamedTemporaryFile(suffix=".jpg")
        dataset_translated = gdal.Translate(temp.name, dataset, format='JPEG', noData=0)
        del dataset
        print("gdal finished again")
        temp.flush()
        del dataset_translated


    # TODO this fails at dateline
    center_shape = county_geometry.centroid if county_geometry else wkb_loads(metadata_set[0].get_wrs_polygon()).centroid

    zoom_level = 9
    if county_geometry:
        ratio = int(round(math.sqrt(wrs_shape.envelope.area) / math.sqrt(county_geometry.envelope.area)))
        zoom_level += int(math.floor(math.sqrt(ratio)))
        if zoom_level >= MAX_ZOOM:
            zoom_level = MAX_ZOOM

    #                  https://www.google.com/maps/@?api=1&map_action=map&center=-33.712206,150.311941&zoom=12&basemap=terrain
    google_maps_url = "https://www.google.com/maps/@?api=1&map_action=map&center={0},{1}&zoom={2}&basemap=terrain". \
        format(center_shape.y, center_shape.x, zoom_level)

    # shorten url because of stupid twitter bug https://g ithub.com/twitter/twitter-text/issues/201
    shortener = "https://www.googleapis.com/urlshortener/v1/url?key={0}".format(GOOGLE_URL_SHORTNER_KEY)
    response_shortner = requests.post(shortener, json={"longUrl": google_maps_url})
    if response_shortner.status_code == 200:
        short_url = json.loads(response_shortner.text)["id"]
    else:
        short_url = ""

    geocode_url = "https://maps.googleapis.com/maps/api/geocode/json?latlng={0},{1}&key={2}".format(center_shape.y,
                                                                                                    center_shape.x,
                                                                                                    GOOGLE_GEOCODE_KEY)
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

    try:
        upload = api.media_upload(temp.name)
        media_ids = [upload.media_id_string]
        res = api.update_status(media_ids=media_ids,
                                status=msg,
                                long=center_shape.x,
                                lat=center_shape.y)
    except:
        print("failed to post image")
        res = -1
    finally:
        temp.close()

    return res


def date_info(metadata, s3_path_name):
    # analysis of the date, captured, processed and published to AWS
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

    delta_post_time = d - datetime.strptime(s3_path_name, "%Y-%m-%dT%H:%M:%S.%fZ")
    seconds_aws_post_time = delta_post_time.total_seconds()
    h = int(seconds_aws_post_time // 3600)
    m = int((seconds_aws_post_time % 3600) // 60)
    date_string_3 = "hours since posted to s3: {0}:{1}".format(h, str(m).zfill(2))

    date_string = date_string_1 + '\n' + date_string_2 + '\n' + date_string_3

    return date_string, delta_sensed


def main(argv):
    # wait until /imagery/c1 is a directory
    b_mounted = False
    while not b_mounted:
        if os.path.isdir("/imagery/c1"):
            sys.stdout.write("s3 is mounted\n")
            b_mounted = True
        time.sleep(2)

    tweet_count = 0
    metadata_service = MetadataService()
    # don't want to over do it with twitter
    while tweet_count < 1000:
        messages = sqs.receive_message(QueueUrl=QUEUE_URL,
                                       AttributeNames=['ApproximateFirstReceiveTimestamp'],
                                       MaxNumberOfMessages=10)
        bucket_posts = {}
        batch_delete = []
        if 'Messages' not in messages:
            break

        # grab satellite imagery message from sqs (originally an SNS message)
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

            # create a local path name
            path_name = '/imagery/' + os.path.dirname(image_key)
            basename = os.path.basename(path_name)
            if r.search(basename):
                continue
            else:
                bucket_posts[path_name] = sns_messages['Records'][0]['eventTime']

        auth = tweepy.OAuthHandler(TWITTER_CONSUMER_KEY_API, TWITTER_CONSUMER_SECRET_API)
        auth.set_access_token(TWITTER_ACCESS_TOKEN, TWITTER_SECRET)

        api = tweepy.API(auth)

        # for each path name perform some analysis
        for path_name in bucket_posts:
            sys.stdout.write("{0} path available\n".format(path_name))
            metadata = Metadata(path_name)

            # only process realtime data, not the tier data that has been reprocessed
            if metadata.collection_category != "RT":
                continue

            # cloud cover better than 30%
            if metadata.cloud_cover > 30:
                continue

            # skip everything that is north of Maine, it not as compelling
            image_extent_shape = wkb_loads(metadata.get_wrs_polygon())

            if image_extent_shape.centroid.y > 45.2538:
                continue

            date_string, delta_sensed = date_info(metadata, bucket_posts[path_name])

            if delta_sensed.days > 1:
                continue

            # TODO this needs a spatial index, but I'm just slamming things together for a demo
            # contained_counties = []
            intersecting_counties = []
            for county_state_key in STATE_COUNTY_MAP:
                if image_extent_shape.intersects(STATE_COUNTY_MAP[county_state_key]):
                    intersecting_counties.append(county_state_key)

                # if image_extent_shape.contains(STATE_COUNTY_MAP[county]):
                #     contained_counties.append(county)

            # TODO for now, only counties in US get tweeted
            if len(intersecting_counties) == 0:
                continue

            # Post overview image
            post_image([metadata], date_string, api)
            tweet_count += 1
            bad_counties = ["Wharton", "Schuylkill", "Honolulu", "Valley", "Clark", "Monroe", "Harding", "Wake", "Franklin", "Maui"]
            for county_state_key in intersecting_counties:
                if county_state_key[0] in bad_counties or county_state_key[0].startswith("Mont"):
                    continue
                sys.stdout.write("county name {0}\n".format(county_state_key[0]))

                # county geometry
                county_shape = STATE_COUNTY_MAP[county_state_key]
                county_shape_minus_wrs = county_shape.difference(wkb_loads(metadata.get_wrs_polygon()))

                if not county_shape_minus_wrs.is_empty:
                    # get other metadata
                    landsat_qf = LandsatQueryFilters()
                    # cloud cover less than 30%
                    landsat_qf.cloud_cover.set_range(end=30)

                    # only interested in Precision Terrain
                    landsat_qf.data_type.set_value('L1TP')
                    # subtract the wrs_shape from the input geometry and then search for any data
                    # that will cover the rest of the county requested
                    landsat_qf.aoi.set_geometry(county_shape_minus_wrs.wkb)
                    # sort by date, with most recent first
                    landsat_qf.acquired.sort_by(epl_imagery_pb2.DESCENDING)

                    rows = metadata_service.search_mosaic_group(data_filters=landsat_qf, satellite_id=SpacecraftID.LANDSAT_8)
                    metadata_set = list(rows)
                    metadata_set.insert(0, metadata)
                else:
                    metadata_set = [metadata]

                if post_image(metadata_set, date_string, api, county_shape) != -1:
                    tweet_count += 1

        # TODO only delete those that have been successfully posted
        sqs.delete_message_batch(QueueUrl=QUEUE_URL, Entries=batch_delete)


if __name__ == "__main__":
    main(sys.argv)
