"""Failover AWS Spot Instances."""
import boto3

REGION_NAME = "sa-east-1"
TAG_FAILOVER = "_fasi_failover"
TAG_ELASTIC_IP = "_fasi_elastic_ip"
TAG_EBS = "_fasi_ebs"


def main(event, context):
    client = BotoClientFacade("autoscaling", REGION_NAME)
    response = client.multi_request("describe_auto_scaling_groups")
    groups = {group["AutoScalingGroupName"]: group for group in response["AutoScalingGroups"]}

    mirrors = []
    for group_name, group in groups.items():
        for tag in group["Tags"]:
            if tag["Key"] == TAG_FAILOVER:
                failover = tag["Value"]
                break
        else:
            continue
        mirror = AutoScalingMirror(group_name, failover)
        mirror.primary_desired_capacity = group["DesiredCapacity"]
        mirror.primary_instances = group["Instances"]
        try:
            mirror.failover_desired_capacity = groups[failover]["DesiredCapacity"]
            mirror.failover_instances = groups[failover]["Instances"]
        except KeyError:
            print "KeyError: group '{}' exists?".format(failover)
            continue
        for tag in group["Tags"]:
            if tag["Key"] == TAG_ELASTIC_IP:
                mirror.elastic_ip = tag["Value"]
            elif tag["Key"] == TAG_EBS:
                mirror.ebs = tag["Value"]
        mirrors.append(mirror)

    elastic_ips = {}
    ebs_volumes = {}
    for mirror in mirrors:
        deficit = mirror.primary_desired_capacity - len(mirror.primary_instances)
        deficit = deficit if deficit >= 0 else 0

        if deficit != mirror.failover_desired_capacity:
            print "Scaling failover to {} instances".format(deficit)
            client.raw_request("set_desired_capacity", {
                "AutoScalingGroupName": mirror.failover_name, "DesiredCapacity": deficit,
                "HonorCooldown": False})

        if mirror.elastic_ip:
            if len(mirror.primary_instances) == 1:
                elastic_ips[mirror.elastic_ip] = mirror.primary_instances[0]
            elif len(mirror.failover_instances) == 1:
                elastic_ips[mirror.elastic_ip] = mirror.failover_instances[0]

        if mirror.ebs:
            if len(mirror.primary_instances) == 1:
                ebs_volumes[mirror.ebs] = mirror.primary_instances[0]
            elif len(mirror.failover_instances) == 1:
                ebs_volumes[mirror.ebs] = mirror.failover_instances[0]

    if elastic_ips:
        ec2_client = BotoClientFacade("ec2", REGION_NAME)
        resp = ec2_client.raw_request("describe_addresses", {"AllocationIds": elastic_ips.keys()})

        for elastic_ip in resp["Addresses"]:
            current_allocated = elastic_ip.get("InstanceId", None)
            ip_owner = elastic_ips[elastic_ip["AllocationId"]]["InstanceId"]
            if ip_owner != current_allocated:
                print "Associating elastic ip {} to instance {}".format(elastic_ip["AllocationId"],
                                                                        ip_owner)
                ec2_client.raw_request("associate_address", {
                    "InstanceId": ip_owner, "AllocationId": elastic_ip["AllocationId"],
                    "AllowReassociation": True})

    if ebs_volumes:
        ec2_client = BotoClientFacade("ec2", REGION_NAME)
        resp = ec2_client.raw_request("describe_volumes", {"VolumeIds": ebs_volumes.keys()})

        for volume in resp["Volumes"]:
            current_allocated = None
            for attachment in volume["Attachments"]:
                if attachment["State"] in ["attached", "attaching"]:
                    current_allocated = attachment.get("InstanceId", None)
                    break

            volume_owner = ebs_volumes[volume["VolumeId"]]["InstanceId"]
            if volume_owner != current_allocated:
                if current_allocated:
                    print "Detaching ebs volume {} from instance {}".format(volume["VolumeId"],
                                                                      current_allocated)
                    ec2_client.raw_request("detach_volume", {
                        "InstanceId": current_allocated, "VolumeId": volume["VolumeId"],
                        "Device": "/dev/sdf"})
            if not current_allocated:
                print "Attaching ebs volume {} to instance {}".format(volume["VolumeId"],
                                                                      volume_owner)
                ec2_client.raw_request("attach_volume", {
                    "InstanceId": volume_owner, "VolumeId": volume["VolumeId"],
                    "Device": "/dev/sdf"})

    return "finished"


class AutoScalingMirror:
    primary_name = None
    failover_name = None

    primary_desired_capacity = None
    failover_desired_capacity = None

    primary_instances = None
    failover_instances = None

    failover_needed_capacity = None
    elastic_ip = None
    elastic_ip_owner = None

    ebs = None
    ebs_owner = None

    def __init__(self, primary_name, failover_name):
        self.primary_name = primary_name
        self.failover_name = failover_name


class BotoClientFacade(object):
    """High level boto3 requests"""
    def __init__(self, service_name, region_name):
        self._boto_client = boto3.client(service_name, region_name=region_name)

    def multi_request(self, request_name, parameters=None):
        """Emulate pagination as a single request"""
        parameters = {} if parameters is None else parameters
        if "NextToken" in parameters:
            raise Exception("'NextToken' parameter is not allowed in multi_request")

        full_response = {}
        while True:
            response = self.raw_request(request_name, parameters)
            for key, value in response.items():
                if isinstance(value, list):
                    if key not in full_response:
                        full_response[key] = []
                    full_response[key] += value
                else:
                    if key not in full_response:
                        full_response[key] = []
                    full_response[key].append(value)
            try:
                next_token = response["NextToken"]
                parameters["NextToken"] = next_token
                if not next_token:
                    break
            except KeyError:
                break
        return full_response

    def raw_request(self, request_name, parameters=None):
        parameters = {} if parameters is None else parameters
        request = getattr(self._boto_client, request_name)
        return request(**parameters)
