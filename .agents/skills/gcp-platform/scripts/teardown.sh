#!/usr/bin/env bash
# teardown.sh: PRINTS the commands to stop spend after the event. Runs nothing.
# Review, then copy-paste what you want. Judges may still open your Skills project, so
# scale to zero rather than delete until judging is complete.
PROJECT_ID="${PROJECT_ID:-$(gcloud config get-value project 2>/dev/null)}"
REGION="${REGION:-us-central1}"
cat <<EOF
# Scale to zero (keeps URLs working, with cold starts):
gcloud run services update heat-planner --min-instances=0 --project $PROJECT_ID --region $REGION
gcloud run services update heat-toolbox --min-instances=0 --project $PROJECT_ID --region $REGION
# Only after judging closes:
# gcloud run services delete heat-planner --project $PROJECT_ID --region $REGION
# gcloud run services delete heat-toolbox --project $PROJECT_ID --region $REGION
EOF
