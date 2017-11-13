```bash
aws autoscaling put-scaling-policy --policy-name twitter-demo-1-sqs-scalein-policy --auto-scaling-group-name twitter-demo-1-auto-scale --scaling-adjustment -1 --adjustment-type ChangeInCapacity
```
```json
{
    "Alarms": [], 
    "PolicyARN": "arn:aws:autoscaling:us-west-2:495706002520:scalingPolicy:113bcf2c-133e-4362-82a5-ec93c6e1b072:autoScalingGroupName/twitter-demo-1-auto-scale:policyName/twitter-demo-1-sqs-scalein-policy"
}
```

```bash
aws autoscaling put-scaling-policy --policy-name twitter-demo-1-sqs-scaleout-policy --auto-scaling-group-name twitter-demo-1-auto-scale --scaling-adjustment 1 --adjustment-type ChangeInCapacity
```
```json
{
    "Alarms": [], 
    "PolicyARN": "arn:aws:autoscaling:us-west-2:495706002520:scalingPolicy:b4a2f35c-7295-4bc3-9b3b-6e831e3563e1:autoScalingGroupName/twitter-demo-1-auto-scale:policyName/twitter-demo-1-sqs-scaleout-policy"
}
```

```bash
aws cloudwatch put-metric-alarm --alarm-name AddCapacityToProcessQueue --metric-name ApproximateNumberOfMessagesVisible --namespace "AWS/SQS" --statistic Average --period 300 --threshold 3 --comparison-operator GreaterThanOrEqualToThreshold --dimensions Name=landsat-aws-available,Value=arn:aws:sqs:us-west-2:495706002520:landsat-aws-available --evaluation-periods 2 --alarm-actions arn:aws:autoscaling:us-west-2:495706002520:scalingPolicy:113bcf2c-133e-4362-82a5-ec93c6e1b072:autoScalingGroupName/twitter-demo-1-auto-scale:policyName/twitter-demo-1-sqs-scalein-policy
```

```bash
aws cloudwatch put-metric-alarm --alarm-name RemoveCapacityFromProcessQueue --metric-name ApproximateNumberOfMessagesVisible --namespace "AWS/SQS" --statistic Average --period 300 --threshold 1 --comparison-operator LessThanOrEqualToThreshold --dimensions Name=landsat-aws-available,Value=arn:aws:sqs:us-west-2:495706002520:landsat-aws-available --evaluation-periods 2 --alarm-actions arn:aws:autoscaling:us-west-2:495706002520:scalingPolicy:b4a2f35c-7295-4bc3-9b3b-6e831e3563e1:autoScalingGroupName/twitter-demo-1-auto-scale:policyName/twitter-demo-1-sqs-scaleout-policy
 ```
 
 ```bash
 aws cloudwatch describe-alarms --alarm-names AddCapacityToProcessQueue RemoveCapacityFromProcessQueue
 ```
 
 ```bash
 aws autoscaling describe-policies --auto-scaling-group-name twitter-demo-1-auto-scale
```