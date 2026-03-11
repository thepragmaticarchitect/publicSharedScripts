#!/bin/bash

## Directory for export files
EXPORT_DIR="/home/cloudshell-user/loadbalexports"
mkdir -v -p $EXPORT_DIR
chmod 755 $EXPORT_DIR

read -p "Enter the AWS account name: " accountname
read -p "Enter the region: " region

# Define output file paths
ALB_JSON="$EXPORT_DIR/application_load_balancers_${accountname}_${region}.json"
CLB_JSON="$EXPORT_DIR/classic_load_balancers_${accountname}_${region}.json"
NLB_JSON="$EXPORT_DIR/network_load_balancers_${accountname}_${region}.json"
LISTENER_JSON="$EXPORT_DIR/listeners_${accountname}_${region}.json"
TARGET_GROUP_JSON="$EXPORT_DIR/target_groups_${accountname}_${region}.json"

# Temporary file for ARNs (ensuring it's fresh)
ARN_TEMP_FILE="$EXPORT_DIR/temp_arns.txt"
> "$ARN_TEMP_FILE"

# 1. Export Application Load Balancers
echo "Exporting Application Load Balancers..."
aws elbv2 describe-load-balancers --region "$region" --query 'LoadBalancers[?Type==`application`]' --output json > "$ALB_JSON"
jq -r '.[] | .LoadBalancerArn' "$ALB_JSON" >> "$ARN_TEMP_FILE"

# 2. Export Classic Load Balancers
echo "Exporting Classic Load Balancers..."
aws elb describe-load-balancers --region "$region" --output json > "$CLB_JSON"

# 3. Export Network Load Balancers
echo "Exporting Network Load Balancers..."
aws elbv2 describe-load-balancers --region "$region" --query 'LoadBalancers[?Type==`network`]' --output json > "$NLB_JSON"
jq -r '.[] | .LoadBalancerArn' "$NLB_JSON" >> "$ARN_TEMP_FILE"

# 4. Export Listeners (Looping through ARNs)
echo "Exporting Listener details..."
# Clear file if exists
> "$LISTENER_JSON"
while read -r arn; do
    if [ ! -z "$arn" ]; then
        echo "Processing: $arn"
        aws elbv2 describe-listeners --region "$region" --load-balancer-arn "$arn" --query 'Listeners[*]' --output json >> "$LISTENER_JSON"
    fi
done < "$ARN_TEMP_FILE"

# 5. Export Target Groups
echo "Exporting Target Group details..."
aws elbv2 describe-target-groups --region "$region" --query 'TargetGroups[*]' --output json > "$TARGET_GROUP_JSON"

# 6. Cleanup and Sync
echo "Export completed. Syncing to S3..."
aws s3 sync "$EXPORT_DIR" s3://bash-s3-bucket1/elbbackup/ --exclude "temp_arns.txt"

rm "$ARN_TEMP_FILE"
echo "Done."
