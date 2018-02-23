
## Demonstration of a Landsat Data Tweeter
As data becomes available on S3, this program will spin up a new worker instance. Then it will check for any newly processed "real-time" Landsat data that intersects the United states. If the imagery is in the united states it clips the data by county boundary and warps the data using the Echo Park Labs imagery API. The resulting imagery is tweeted to this twitter account:
https://twitter.com/echoparkdemo

## Steps for Scaling up EC2 Instances according to a changes in SQS
Scaling up instances from SQS using cloud watch took a little time to sort out. These notes here are just a reminder of the documentation I read to get it all working.

http://docs.aws.amazon.com/autoscaling/latest/userguide/as-using-sqs-queue.html
http://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/SQS_AlarmMetrics.html
