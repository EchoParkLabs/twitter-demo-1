FROM 495706002520.dkr.ecr.us-west-2.amazonaws.com/aws-imagery-reader:latest as builder

# COUNTY Shapefile Reader
ENV CLOUD_SDK_REPO=cloud-sdk-stretch
RUN echo "deb http://packages.cloud.google.com/apt $CLOUD_SDK_REPO main" | tee -a /etc/apt/sources.list.d/google-cloud-sdk.list
RUN curl https://packages.cloud.google.com/apt/doc/apt-key.gpg | apt-key add -
RUN cat /etc/apt/sources.list.d/google-cloud-sdk.list
RUN apt-get update && apt-get install -y google-cloud-sdk
RUN apt-get install unzip
# COUNTY Shapefile Reader


# COUNTY Shapefile Reader
RUN gcloud auth activate-service-account gcp-imagery-reader@echoparklabs.iam.gserviceaccount.com --key-file /usr/local/lib/python3/dist-packages/epl/imagery/echoparklabs-e163261155ee.json
# originally from https://landsat.usgs.gov/pathrow-shapefiles
WORKDIR /opt/src/image_post/cb_2016_us_county_500k
RUN gsutil cp gs://county-borders/cb_2016_us_county_500k.zip .
RUN unzip '*.zip'
# COUNTY Shapefile Reader


FROM 495706002520.dkr.ecr.us-west-2.amazonaws.com/aws-imagery-reader:latest

RUN pip3 install tweepy && \
    pip3 install Pillow && \
    pip3 install boto3

# COUNTY Shapefile Reader
WORKDIR /.epl/metadata/county-borders
COPY --from=builder /opt/src/image_post/cb_2016_us_county_500k /.epl/metadata/county-borders/cb_2016_us_county_500k
# COUNTY Shapefile Reader

WORKDIR /opt/src/image_post
COPY ./ ./

RUN mv /opt/src/image_post/image_post.conf /etc/supervisor/conf.d/

ARG SQS_ACCESS_KEY_ID
ARG SQS_SECRET_ACCESS_KEY
ARG TWITTER_ACCESS_TOKEN
ARG TWITTER_CONSUMER_KEY_API
ARG TWITTER_CONSUMER_SECRET_API
ARG TWITTER_SECRET
ARG GOOGLE_GEOCODE_KEY
ARG GOOGLE_URL_SHORTENER_KEY

RUN echo "[default]" >> credentials
RUN echo "aws_access_key_id = $SQS_ACCESS_KEY_ID" >> credentials
RUN echo "aws_secret_access_key = $SQS_SECRET_ACCESS_KEY" >> credentials
RUN cat credentials

WORKDIR /root/.aws
RUN mv /opt/src/image_post/credentials ~/.aws && \
    mv /opt/src/image_post/config ~/.aws

WORKDIR /opt/src/image_post
CMD ["/usr/bin/supervisord"]
