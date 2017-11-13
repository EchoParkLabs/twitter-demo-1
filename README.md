```bash
aws autoscaling put-scaling-policy --policy-name twitter-demo-1-sqs-scalein-policy --auto-scaling-group-name twitter-demo-1-auto-scale --scaling-adjustment -1 --adjustment-type ChangeInCapacity
```
```json
{
    "Alarms": [], 
    "PolicyARN": "arn:aws:autoscaling:us-west-2:495706002520:scalingPolicy:972e3ae5-e868-4e03-8ab9-504307972c70:autoScalingGroupName/twitter-demo-1-auto-scale:policyName/twitter-demo-1-sqs-scalein-policy"
}
```

```bash
aws autoscaling put-scaling-policy --policy-name twitter-demo-1-sqs-scaleout-policy --auto-scaling-group-name twitter-demo-1-auto-scale --scaling-adjustment 1 --adjustment-type ChangeInCapacity
```
```json
{
    "Alarms": [], 
    "PolicyARN": "arn:aws:autoscaling:us-west-2:495706002520:scalingPolicy:f80ebb6a-a3b6-407b-bc8b-1f661b92ef38:autoScalingGroupName/twitter-demo-1-auto-scale:policyName/twitter-demo-1-sqs-scaleout-policy"
}
```

```bash
aws cloudwatch put-metric-alarm --alarm-name AddCapacityToProcessQueue --metric-name ApproximateNumberOfMessagesVisible --namespace "AWS/SQS" --statistic Average --period 300 --threshold 3 --comparison-operator GreaterThanOrEqualToThreshold --dimensions Name=landsat-aws-available,Value=arn:aws:sqs:us-west-2:495706002520:landsat-aws-available --evaluation-periods 2 --alarm-actions arn:aws:autoscaling:us-west-2:495706002520:scalingPolicy:f80ebb6a-a3b6-407b-bc8b-1f661b92ef38:autoScalingGroupName/twitter-demo-1-auto-scale:policyName/twitter-demo-1-sqs-scaleout-policy
```

```bash
aws cloudwatch put-metric-alarm --alarm-name RemoveCapacityFromProcessQueue --metric-name ApproximateNumberOfMessagesVisible --namespace "AWS/SQS" --statistic Average --period 300 --threshold 1 --comparison-operator LessThanOrEqualToThreshold --dimensions Name=landsat-aws-available,Value=arn:aws:sqs:us-west-2:495706002520:landsat-aws-available --evaluation-periods 2 --alarm-actions arn:aws:autoscaling:us-west-2:495706002520:scalingPolicy:972e3ae5-e868-4e03-8ab9-504307972c70:autoScalingGroupName/twitter-demo-1-auto-scale:policyName/twitter-demo-1-sqs-scalein-policy
 ```
 
 ```bash
 aws cloudwatch describe-alarms --alarm-names AddCapacityToProcessQueue RemoveCapacityFromProcessQueue
 ```
 
 ```bash
 aws autoscaling describe-policies --auto-scaling-group-name twitter-demo-1-auto-scale
```