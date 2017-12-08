
## Demonstration of a Landsat Data Tweeter
As data becomes available on S3, this program will spin up. Check for any newly processed "real-time" Landsat data that intersects the United states. It then clips and warps the data using the Echo Park Labs imagery API and tweets that image to this twitter account:
https://twitter.com/echoparkdemo

## Steps for Scaling up EC2 Instances according to a changes in SGS

http://docs.aws.amazon.com/autoscaling/latest/userguide/as-using-sqs-queue.html
http://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/SQS_AlarmMetrics.html

```bash
aws autoscaling put-scaling-policy --policy-name twitter-demo-1-sqs-scalein-policy --auto-scaling-group-name twitter-demo-1-auto-scale --scaling-adjustment -1 --adjustment-type ChangeInCapacity
```
```json
{
    "Alarms": [], 
    "PolicyARN": "arn:aws:autoscaling:us-west-2:495706002520:scalingPolicy:4eb685d5-0338-4cd0-b012-66d72488a37e:autoScalingGroupName/twitter-demo-1-auto-scale:policyName/twitter-demo-1-sqs-scalein-policy"
}
```

```bash
aws autoscaling put-scaling-policy --policy-name twitter-demo-1-sqs-scaleout-policy --auto-scaling-group-name twitter-demo-1-auto-scale --scaling-adjustment 1 --adjustment-type ChangeInCapacity
```
```json
{
    "Alarms": [], 
    "PolicyARN": "arn:aws:autoscaling:us-west-2:495706002520:scalingPolicy:dcca074c-9bcc-4350-a069-09927d5c28fd:autoScalingGroupName/twitter-demo-1-auto-scale:policyName/twitter-demo-1-sqs-scaleout-policy"
}
```

```bash
aws cloudwatch put-metric-alarm --alarm-name AddCapacityToProcessQueue --metric-name ApproximateNumberOfMessagesVisible --namespace "AWS/SQS" --statistic Average --period 300 --threshold 3 --comparison-operator GreaterThanOrEqualToThreshold --dimensions Name=QueueName,Value=landsat-aws-available --evaluation-periods 2 --alarm-actions arn:aws:autoscaling:us-west-2:495706002520:scalingPolicy:dcca074c-9bcc-4350-a069-09927d5c28fd:autoScalingGroupName/twitter-demo-1-auto-scale:policyName/twitter-demo-1-sqs-scaleout-policy
```

```bash
aws cloudwatch put-metric-alarm --alarm-name RemoveCapacityFromProcessQueue --metric-name ApproximateNumberOfMessagesVisible --namespace "AWS/SQS" --statistic Average --period 300 --threshold 1 --comparison-operator LessThanOrEqualToThreshold --dimensions Name=QueueName,Value=landsat-aws-available --evaluation-periods 2 --alarm-actions arn:aws:autoscaling:us-west-2:495706002520:scalingPolicy:4eb685d5-0338-4cd0-b012-66d72488a37e:autoScalingGroupName/twitter-demo-1-auto-scale:policyName/twitter-demo-1-sqs-scalein-policy
 ```
 
 ```bash
 aws cloudwatch describe-alarms --alarm-names AddCapacityToProcessQueue RemoveCapacityFromProcessQueue
 ```
 
 ```bash
 aws autoscaling describe-policies --auto-scaling-group-name twitter-demo-1-auto-scale
```
