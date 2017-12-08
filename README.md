# Failover AWS Spot Instances

This lambda script allows your AWS account to use spot instances that automatically failover to on-demand instances on pricing spikes. It works by setting up two *auto scaling groups* and a *lambda function* that pools the groups and changes the *desired capacity* accordingly.

Note: This will incur in additional AWS Lambda charges, but they are small compared to the savings of using spot instances.

**Failover Delay:** 5 to 10 minutes

**License:** MIT

## Usage Scenarios
### Very-low-cost LAMP server
You could use this script to set-up a low-cost spot instance, such as *t1.micro*, as your LAMP server. If your instance is terminated during pricing spikes, it is automatically replaced by an on-demand instance. When prices drop, the on-demand instance terminated.

### Persistent Spot Instances Cluster
Imagine that you have to do lots of computation and need lots of instances. AWS provide you with two approaches: The first one is to use normal instances. Effective, but costly; The second option are spot instances. While they are cheap, if you are going through some pricing spike then you have no idea when the computation will be finished. Why not use a hybrid approach?
You can set-up two auto scaling groups, one for the spot instances and other for on-demand. Only when your spot group is unable to launch instances, the on-demand group is used. This allows you to have the agility of on-demand instances, but also the pricing benefits of spot instances.

## Lifecycle
```
----0------X-------------0---------I----------0-------
  Pool  Failure      Failover  Launched   Resources
```

1. Pool: Lambda function check instances
2. Failure: A spot instance has failed
3. Failover: Lambda function launches an on-demand replacement
4. Launched: Replacement is running
5. Resources: Lambda function assigns the elastic ip and EBS volume

## Configuring
**NOTE: You only need to do this once per AWS account. A single function can handle multiple auto scaling groups.**

Create a new Python 2.7 function in AWS Lambda and paste the code found in "lambda.py" file. Make sure the following configurations are set.

Configuration|What to do?
-----|------
Function Runtime|Python 2.7
Function Handler|fasi.main
Function Role|(create a new role and add the policies from "lambda-iam-role.json")
Event|(set an scheduled event with 5 minutes interval)
Timeout|10 seconds

By now everything should be up and running. Try to test the function to see if any error is raised. On a successful pass the function should return a "finished" string. Now you can create as many failover spot instances as you want.

## Usage (single instance failover)
Create 2 launch configurations. One is used as the main servers (probably a spot request), and, in this example, is called **primary-lc**. The second one is used as a failover (you could use an ondemand instance), and is called **failover-lc**. Remember: The name of the launch configurations are not important, we are just using these names for didatic reasons.

Using the **failover-lc** create an Auto Scaling Group (we'll call it **failover-asg**) and make sure you have the following configurations. Do not create any auto scalling events!

Configuration|Value
-----|------
Name|(set anything you want)
Launch Configuration|**failover-lc**
Min Capacity|0
Max Capacity|1
Desired Capacity|0
Autoscaling|Manual

Next, use the **primary-lc** to create another Auto Scaling Group (we'll call it **primary-asg**). Set the following configurations.

Configuration|Value
-----|------
Name|(set anything you want)
Launch Configuration|**primary-lc**
Min Capacity|1
Max Capacity|1
Desired Capacity|1
Autoscaling|(anything you want)

In order to tell the lambda script to watch these resources you should set the following tags in the **primary-asg** group.

Key|Value
-----|------
_fasi_failover|(name of the **failover-asg** group)
_fasi_elastic_ip|(reservation-id of the elastic ip to use)
_fasi_ebs|(volume-id of permanent ebs)

Everything should be up and running! If your instance in the **primary-asg** fails (and it's not replaced) the lambda script automatically launches a new one in the **failover-asg**, changes the elastic ip association and reattach the ebs volume. As soon as the **primary-asg** succeeds in launching an instance, the **failover-asg** is scaled-down.

## Usage (multiple instances failover)
Use the same steps as *single instance failover*, but set the *Max Capacity* accordingly. Please note that **elastic ip reassociation does not work with multiple instances**. This means that you must not set the *_fasi_elastic_ip* tag.


## License ##
This project was developed by [NUMER Simulação Numérica](https://numer.com.br) and is available under the MIT license.
