#!/usr/bin/env bash
#
# Deploy NyayaLens to Cloud Run.
#
# Two modes. Vertex AI is the one to use in production: the service account
# authenticates with Application Default Credentials, so no API key exists
# anywhere. An AI Studio key is supported for a quick deployment, and is read
# from Secret Manager rather than passed on the command line.
#
#   PROJECT_ID=my-project ./scripts/deploy.sh vertex
#   PROJECT_ID=my-project ./scripts/deploy.sh apikey
#
set -Eeuo pipefail

MODE="${1:-vertex}"
SERVICE="${SERVICE:-nyayalens}"
REGION="${REGION:-asia-south1}"
PROJECT_ID="${PROJECT_ID:?set PROJECT_ID to your Google Cloud project}"
SERVICE_ACCOUNT="${SERVICE_ACCOUNT:-${SERVICE}-run@${PROJECT_ID}.iam.gserviceaccount.com}"
SECRET_NAME="${SECRET_NAME:-gemini-api-key}"

common_env="LLM_PROVIDER=gemini,GEMINI_MODEL=${GEMINI_MODEL:-gemini-3.6-flash}"
common_env+=",GEMINI_MODEL_LITE=${GEMINI_MODEL_LITE:-gemini-3.1-flash-lite}"
common_env+=",LOG_LEVEL=${LOG_LEVEL:-INFO}"
common_env+=",LAW_DATA_SHOW_UNREVIEWED=${LAW_DATA_SHOW_UNREVIEWED:-false}"
common_env+=",EXPORT_WARMUP=true"

args=(
  run deploy "${SERVICE}"
  --source .
  --project "${PROJECT_ID}"
  --region "${REGION}"
  --allow-unauthenticated
  --cpu-boost
  --memory 1Gi
  --cpu 1
  --concurrency 40
  --max-instances "${MAX_INSTANCES:-3}"
  --min-instances "${MIN_INSTANCES:-0}"
  --timeout 120
  --service-account "${SERVICE_ACCOUNT}"
)

case "${MODE}" in
  vertex)
    echo "Deploying with Vertex AI. No API key will exist anywhere."
    args+=(--set-env-vars "${common_env},GOOGLE_GENAI_USE_VERTEXAI=true,GOOGLE_CLOUD_PROJECT=${PROJECT_ID},GOOGLE_CLOUD_LOCATION=${REGION}")
    ;;
  apikey)
    echo "Deploying with an AI Studio key from Secret Manager: ${SECRET_NAME}"
    args+=(--set-env-vars "${common_env}")
    args+=(--set-secrets "GEMINI_API_KEY=${SECRET_NAME}:latest")
    ;;
  *)
    echo "Unknown mode '${MODE}'. Use 'vertex' or 'apikey'." >&2
    exit 2
    ;;
esac

gcloud "${args[@]}"

url="$(gcloud run services describe "${SERVICE}" --project "${PROJECT_ID}" --region "${REGION}" --format 'value(status.url)')"
echo
echo "Deployed: ${url}"
echo "Checking health..."
curl -fsS "${url}/healthz" && echo " ok"
