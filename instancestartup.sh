#!/usr/bin/env bash

# check that network is up
until ping -c1 www.google.com &>/dev/null; do :; done

# remove container just in case
sudo docker rm -f temp-twitter

# sign in to ecr and pull latest demo image
sudo $(/usr/local/bin/aws ecr get-login --no-include-email --region us-west-2)
sudo docker pull 495706002520.dkr.ecr.us-west-2.amazonaws.com/twitter-demo-1:latest

# run docker image
sudo docker run -d --privileged --name=temp-twitter 495706002520.dkr.ecr.us-west-2.amazonaws.com/twitter-demo-1:latest
