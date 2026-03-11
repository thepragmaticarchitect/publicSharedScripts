ec2_idle_finder.py
------------------
Checks EC2 instances for low CPU utilization over the past 14 days using
CloudWatch metrics. Flags instances that are likely idle or oversized.

Good for FinOps reviews and rightsizing conversations.

Requirements: boto3
Usage:
    python ec2_idle_finder.py
    python ec2_idle_finder.py --days 7 --cpu-threshold 5 --output idle.csv
"""

import boto3
import csv
import argparse
from datetime import datetime, timedelta, timezone


def get_avg_cpu(cw_client, instance_id: str, days: int) -> float | None:
    end   = datetime.now(timezone.utc)
    start = end - timedelta(days=days)

    resp = cw_client.get_metric_statistics(
        Namespace="AWS/EC2",
        MetricName="CPUUtilization",
        Dimensions=[{"Name": "InstanceId", "Value": instance_id}],
        StartTime=start,
        EndTime=end,
        Period=86400,          # daily data points
        Statistics=["Average"],
    )

    datapoints = resp.get("Datapoints", [])
    if not datapoints:
        return None
    return round(sum(d["Average"] for d in datapoints) / len(datapoints), 2)


def get_instance_name(instance: dict) -> str:
    for tag in instance.get("Tags", []):
        if tag["Key"] == "Name":
            return tag["Value"]
    return "—"


def scan_instances(days: int, cpu_threshold: float) -> list[dict]:
    ec2 = boto3.client("ec2")
    cw  = boto3.client("cloudwatch")

    paginator = ec2.get_paginator("describe_instances")
    results   = []

    for page in paginator.paginate(Filters=[{"Name": "instance-state-name", "Values": ["running"]}]):
        for reservation in page["Reservations"]:
            for inst in reservation["Instances"]:
                iid   = inst["InstanceId"]
                itype = inst["InstanceType"]
                az    = inst["Placement"]["AvailabilityZone"]
                name  = get_instance_name(inst)
                launch = str(inst["LaunchTime"].date())

                avg_cpu = get_avg_cpu(cw, iid, days)

                if avg_cpu is None:
                    flag = "No metrics — check CloudWatch agent"
                elif avg_cpu < cpu_threshold:
                    flag = f"IDLE — avg CPU {avg_cpu}%"
                else:
                    flag = f"Active — avg CPU {avg_cpu}%"

                results.append({
                    "instance_id":   iid,
                    "name":          name,
                    "type":          itype,
                    "az":            az,
                    "launch_date":   launch,
                    "avg_cpu_pct":   avg_cpu if avg_cpu is not None else "—",
                    "flag":          flag,
                })

    return results


def main():
    parser = argparse.ArgumentParser(description="Find idle EC2 instances via CloudWatch CPU metrics.")
    parser.add_argument("--days",          type=int,   default=14,
                        help="Look-back window in days (default: 14)")
    parser.add_argument("--cpu-threshold", type=float, default=5.0,
                        help="Flag instances with avg CPU below this %% (default: 5)")
    parser.add_argument("--output",        default="",
                        help="Optional CSV output path")
    args = parser.parse_args()

    print(f"Scanning running EC2 instances — {args.days}-day avg CPU, threshold {args.cpu_threshold}%...\n")
    results = scan_instances(args.days, args.cpu_threshold)

    idle = [r for r in results if "IDLE" in str(r["flag"])]
    print(f"  Total running instances : {len(results)}")
    print(f"  Likely idle             : {len(idle)}\n")

    fmt = "{:<20} {:<28} {:<14} {:<18} {:<12} {}"
    print(fmt.format("INSTANCE ID", "NAME", "TYPE", "AZ", "AVG CPU %", "FLAG"))
    print("-" * 110)
    for r in sorted(results, key=lambda x: str(x["avg_cpu_pct"])):
        print(fmt.format(
            r["instance_id"], r["name"][:27], r["type"],
            r["az"], str(r["avg_cpu_pct"]), r["flag"]
        ))

    if args.output:
        fields = ["instance_id", "name", "type", "az", "launch_date", "avg_cpu_pct", "flag"]
        with open(args.output, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            writer.writerows(results)
        print(f"\nSaved → {args.output}")


if __name__ == "__main__":
    main()
