#!/usr/bin/env bash
#
# Lucas Installation Script
# https://github.com/a2wio/lucas
#
# Usage: curl -sSL https://raw.githubusercontent.com/a2wio/lucas/main/scripts/install.sh | bash
#    or: git clone https://github.com/a2wio/lucas && cd lucas/scripts && ./install.sh
#
# This script runs entirely locally. No data is sent to any server.
# View the source: https://github.com/a2wio/lucas/blob/main/scripts/install.sh
#

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m' # No Color

# Configuration defaults
LUCAS_NAMESPACE="a2w-lucas"
TARGET_NAMESPACE="default"
TARGET_NAMESPACES="default"
LUCAS_MODE="autonomous"
LLM_BACKEND="claude-code"
LLM_PROVIDER="anthropic"
LLM_MODEL=""
LLM_BASE_URL=""
CLAUDE_MODEL="sonnet"
SCAN_INTERVAL="3600"
SEALED_SECRETS_NAMESPACE="sealed-secrets"
SEALED_SECRETS_CONTROLLER="sealed-secrets-controller"
SECRET_BACKEND="manual"
DASHBOARD_ENABLED="true"
DASHBOARD_HOST=""
KUBECTL_CONTEXT=""
IMAGE_REGISTRY="ghcr.io/a2wio"
IMAGE_PULL_SECRET=""
SLACK_WEBHOOK_URL=""
SLACK_ALERT_CHANNEL=""
SLACK_EMERGENCY_ACTIONS_ENABLED="false"
SLACK_ACTION_ALLOWED_CHANNELS=""
SLACK_ACTION_ALLOWED_USERS=""
SLACK_ACTION_ALLOWED_NAMESPACES=""
DASHBOARD_USER="admin"
DASHBOARD_PASS=""
OUTPUT_DIR="./lucas-k8s"

print_banner() {
    echo -e "${CYAN}"
    cat << 'EOF'
    __
   / /   __  __ _____ ____ _____
  / /   / / / // ___// __ `/ ___/
 / /___/ /_/ // /__ / /_/ (__  )
/_____/\__,_/ \___/ \__,_/____/

    Autonomous SRE Agent
    https://github.com/a2wio/lucas
EOF
    echo -e "${NC}"
}

print_step() {
    echo -e "\n${BLUE}==>${NC} ${BOLD}$1${NC}"
}

print_success() {
    echo -e "${GREEN}✓${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}!${NC} $1"
}

print_error() {
    echo -e "${RED}✗${NC} $1"
}

print_info() {
    echo -e "${CYAN}ℹ${NC} $1"
}

normalize_config() {
    if [ -n "$SRE_ALERT_CHANNEL" ]; then
        SLACK_ALERT_CHANNEL="$SRE_ALERT_CHANNEL"
    fi
    if [ -n "$DASHBOARD_AUTH_USER" ]; then
        DASHBOARD_USER="$DASHBOARD_AUTH_USER"
    fi
    if [ -n "$DASHBOARD_AUTH_PASS" ]; then
        DASHBOARD_PASS="$DASHBOARD_AUTH_PASS"
    fi
    if [ -z "$TARGET_NAMESPACES" ]; then
        TARGET_NAMESPACES="$TARGET_NAMESPACE"
    fi
    TARGET_NAMESPACE="${TARGET_NAMESPACES%%,*}"
}

load_env_file() {
    local env_file="$1"
    if [ ! -f "$env_file" ]; then
        print_error "Env file not found: $env_file"
        exit 1
    fi

    set -a
    . "$env_file"
    set +a

    normalize_config
    print_info "Loaded configuration from $env_file"
}

check_command() {
    if command -v "$1" &> /dev/null; then
        print_success "$1 found: $(command -v $1)"
        return 0
    else
        print_error "$1 not found"
        return 1
    fi
}

check_prerequisites() {
    print_step "Checking prerequisites"

    local missing=0

    # Required
    check_command "kubectl" || missing=$((missing + 1))
    if [ "$SECRET_BACKEND" = "sealed-secrets" ]; then
        check_command "kubeseal" || missing=$((missing + 1))
    fi

    # Check cluster connection
    echo ""
    if [ -n "$KUBECTL_CONTEXT" ]; then
        KUBE_ARGS=(--context "$KUBECTL_CONTEXT")
    else
        KUBE_ARGS=()
    fi

    if kubectl "${KUBE_ARGS[@]}" cluster-info &> /dev/null; then
        print_success "Kubernetes cluster is accessible"
        local context="$KUBECTL_CONTEXT"
        if [ -z "$context" ]; then
            context=$(kubectl config current-context 2>/dev/null || echo "unknown")
        fi
        print_info "Current context: ${context}"
    else
        print_error "Cannot connect to Kubernetes cluster"
        missing=$((missing + 1))
    fi

    if [ "$SECRET_BACKEND" = "sealed-secrets" ]; then
        echo ""
        if kubectl "${KUBE_ARGS[@]}" get deployment -n "$SEALED_SECRETS_NAMESPACE" "$SEALED_SECRETS_CONTROLLER" &> /dev/null; then
            print_success "Sealed Secrets controller found in namespace '$SEALED_SECRETS_NAMESPACE'"
        else
            print_warning "Sealed Secrets controller not found in namespace '$SEALED_SECRETS_NAMESPACE'"
            print_info "You can specify a different namespace during configuration"
        fi
    fi

    if [ $missing -gt 0 ]; then
        echo ""
        print_error "Missing $missing required prerequisite(s)"
        echo ""
        echo "Please install the missing tools:"
        echo "  - kubectl: https://kubernetes.io/docs/tasks/tools/"
        if [ "$SECRET_BACKEND" = "sealed-secrets" ]; then
            echo "  - kubeseal: https://github.com/bitnami-labs/sealed-secrets#kubeseal"
        fi
        echo ""
        exit 1
    fi

    print_success "All prerequisites met"
}

prompt_value() {
    local prompt="$1"
    local default="$2"
    local var_name="$3"
    local is_secret="${4:-false}"

    if [ -n "$default" ]; then
        prompt="$prompt [${default}]"
    fi

    echo -ne "${CYAN}?${NC} ${prompt}: " > /dev/tty

    if [ "$is_secret" = "true" ]; then
        read -s value < /dev/tty
        echo "" > /dev/tty
    else
        read value < /dev/tty
    fi

    if [ -z "$value" ] && [ -n "$default" ]; then
        value="$default"
    fi

    eval "$var_name='$value'"
}

prompt_yes_no() {
    local prompt="$1"
    local default="${2:-y}"

    if [ "$default" = "y" ]; then
        prompt="$prompt [Y/n]"
    else
        prompt="$prompt [y/N]"
    fi

    echo -ne "${CYAN}?${NC} ${prompt}: " > /dev/tty
    read answer < /dev/tty

    if [ -z "$answer" ]; then
        answer="$default"
    fi

    case "$answer" in
        [Yy]* ) return 0;;
        * ) return 1;;
    esac
}

prompt_choice() {
    local prompt="$1"
    shift
    local options=("$@")

    echo -e "${CYAN}?${NC} ${prompt}" > /dev/tty
    for i in "${!options[@]}"; do
        echo "  $((i+1))) ${options[$i]}" > /dev/tty
    done
    echo -ne "Enter choice [1-${#options[@]}]: " > /dev/tty
    read choice < /dev/tty

    echo "$choice"
}

configure_installation() {
    print_step "Configuration"

    echo ""
    echo -e "${YELLOW}╔════════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${YELLOW}║${NC}  ${BOLD}PRIVACY NOTICE${NC}                                               ${YELLOW}║${NC}"
    echo -e "${YELLOW}║${NC}                                                                ${YELLOW}║${NC}"
    echo -e "${YELLOW}║${NC}  All credentials you enter are processed ${BOLD}locally only${NC}.        ${YELLOW}║${NC}"
    echo -e "${YELLOW}║${NC}  They are written into local manifests or secrets according   ${YELLOW}║${NC}"
    echo -e "${YELLOW}║${NC}  to your selected secret backend.                            ${YELLOW}║${NC}"
    echo -e "${YELLOW}║${NC}                                                                ${YELLOW}║${NC}"
    echo -e "${YELLOW}║${NC}  View: ${BLUE}https://github.com/a2wio/lucas/blob/main/scripts/install.sh${NC}  ${YELLOW}║${NC}"
    echo -e "${YELLOW}╚════════════════════════════════════════════════════════════════╝${NC}"
    echo ""

    print_info "Secret backend"
    prompt_value "Secret backend (manual/sealed-secrets)" "$SECRET_BACKEND" SECRET_BACKEND

    if [ "$SECRET_BACKEND" = "sealed-secrets" ]; then
        check_command "kubeseal" || {
            print_error "kubeseal is required when SECRET_BACKEND=sealed-secrets"
            exit 1
        }

        print_info "Sealed Secrets Configuration"
        prompt_value "Sealed Secrets namespace" "$SEALED_SECRETS_NAMESPACE" SEALED_SECRETS_NAMESPACE
        prompt_value "Sealed Secrets controller name" "$SEALED_SECRETS_CONTROLLER" SEALED_SECRETS_CONTROLLER

        if [ -n "$KUBECTL_CONTEXT" ]; then
            KUBE_ARGS=(--context "$KUBECTL_CONTEXT")
        else
            KUBE_ARGS=()
        fi

        if ! kubectl "${KUBE_ARGS[@]}" get deployment -n "$SEALED_SECRETS_NAMESPACE" "$SEALED_SECRETS_CONTROLLER" &> /dev/null; then
            print_error "Cannot find Sealed Secrets controller at $SEALED_SECRETS_NAMESPACE/$SEALED_SECRETS_CONTROLLER"
            print_info "Please ensure Sealed Secrets is installed: https://github.com/bitnami-labs/sealed-secrets"
            exit 1
        fi
    fi

    echo ""
    print_info "Lucas Configuration"
    prompt_value "Lucas namespace" "$LUCAS_NAMESPACE" LUCAS_NAMESPACE
    prompt_value "Namespace(s) to monitor (comma-separated)" "$TARGET_NAMESPACES" TARGET_NAMESPACES

    echo ""
    echo "Lucas modes:"
    echo "  autonomous - Lucas can automatically fix issues"
    echo "  watcher    - Lucas only observes and reports"
    prompt_value "Lucas mode (autonomous/watcher)" "$LUCAS_MODE" LUCAS_MODE

    echo ""
    prompt_value "LLM backend (claude-code/openai-compatible)" "$LLM_BACKEND" LLM_BACKEND
    prompt_value "LLM provider (anthropic/groq/kimi/gemini)" "$LLM_PROVIDER" LLM_PROVIDER

    if [ "$LLM_BACKEND" = "claude-code" ]; then
        echo "Claude models:"
        echo "  sonnet - Faster, cheaper (\$3/\$15 per 1M tokens)"
        echo "  opus   - More capable (\$15/\$75 per 1M tokens)"
        prompt_value "Claude model (sonnet/opus)" "$CLAUDE_MODEL" CLAUDE_MODEL
    else
        local default_model="llama-3.3-70b-versatile"
        local default_base_url="https://api.groq.com/openai/v1"
        if [ "$LLM_PROVIDER" = "kimi" ]; then
            default_model="kimi-k2.5"
            default_base_url="https://api.moonshot.ai/v1"
        elif [ "$LLM_PROVIDER" = "gemini" ]; then
            default_model="gemini-2.5-flash"
            default_base_url="https://generativelanguage.googleapis.com/v1beta/openai"
        fi
        prompt_value "LLM model" "$default_model" LLM_MODEL
        prompt_value "LLM base URL" "$default_base_url" LLM_BASE_URL
    fi

    prompt_value "Scan interval in seconds" "$SCAN_INTERVAL" SCAN_INTERVAL

    echo ""
    print_info "API Credentials"
    echo -e "${CYAN}ℹ${NC} Provide the API key for the selected provider"
    prompt_value "LLM API key" "" LLM_API_KEY true

    if [ -z "$LLM_API_KEY" ]; then
        print_error "LLM API key is required"
        exit 1
    fi

    echo ""
    print_info "Slack Configuration"
    echo -e "${CYAN}ℹ${NC} Create a Slack app at: https://api.slack.com/apps"
    echo -e "${CYAN}ℹ${NC} Required scopes: chat:write, app_mentions:read, channels:history"
    prompt_value "Slack Bot Token (xoxb-...)" "" SLACK_BOT_TOKEN true

    if [ -z "$SLACK_BOT_TOKEN" ]; then
        print_error "Slack Bot Token is required"
        exit 1
    fi

    prompt_value "Slack App Token (xapp-...)" "" SLACK_APP_TOKEN true

    if [ -z "$SLACK_APP_TOKEN" ]; then
        print_error "Slack App Token is required"
        exit 1
    fi

    prompt_value "Slack Alert Channel ID (optional, e.g., C0123456789)" "" SLACK_ALERT_CHANNEL
    prompt_value "Slack webhook URL (optional)" "$SLACK_WEBHOOK_URL" SLACK_WEBHOOK_URL true
    prompt_value "Slack emergency actions enabled (true/false)" "$SLACK_EMERGENCY_ACTIONS_ENABLED" SLACK_EMERGENCY_ACTIONS_ENABLED
    prompt_value "Slack action allowed channel IDs (comma-separated, empty=all)" "$SLACK_ACTION_ALLOWED_CHANNELS" SLACK_ACTION_ALLOWED_CHANNELS
    prompt_value "Slack action allowed user IDs (comma-separated, empty=all)" "$SLACK_ACTION_ALLOWED_USERS" SLACK_ACTION_ALLOWED_USERS
    prompt_value "Slack action allowed namespaces (comma-separated, empty=all)" "$SLACK_ACTION_ALLOWED_NAMESPACES" SLACK_ACTION_ALLOWED_NAMESPACES

    echo ""
    print_info "Dashboard Configuration"
    prompt_value "Dashboard username" "$DASHBOARD_USER" DASHBOARD_USER

    # Generate random password if not provided
    local default_pass=$(openssl rand -base64 12 2>/dev/null || cat /dev/urandom | tr -dc 'a-zA-Z0-9' | fold -w 12 | head -n 1)
    prompt_value "Dashboard password" "$default_pass" DASHBOARD_PASS true

    echo ""
    print_info "Image and cluster configuration"
    prompt_value "Kubernetes context (optional)" "$KUBECTL_CONTEXT" KUBECTL_CONTEXT
    prompt_value "Image registry" "$IMAGE_REGISTRY" IMAGE_REGISTRY
    prompt_value "Image pull secret (optional)" "$IMAGE_PULL_SECRET" IMAGE_PULL_SECRET

    echo ""
    prompt_value "Output directory for manifests" "$OUTPUT_DIR" OUTPUT_DIR

    normalize_config
}

generate_manifests() {
    print_step "Generating Kubernetes manifests"

    normalize_config

    mkdir -p "$OUTPUT_DIR"

    local image_pull_secrets=""
    if [ -n "$IMAGE_PULL_SECRET" ]; then
        image_pull_secrets="
      imagePullSecrets:
        - name: ${IMAGE_PULL_SECRET}"
    fi

    local cron_image_pull_secrets=""
    if [ -n "$IMAGE_PULL_SECRET" ]; then
        cron_image_pull_secrets="
          imagePullSecrets:
            - name: ${IMAGE_PULL_SECRET}
"
    fi

    # namespace.yaml
    cat > "$OUTPUT_DIR/namespace.yaml" << EOF
apiVersion: v1
kind: Namespace
metadata:
  name: ${LUCAS_NAMESPACE}
  labels:
    app: a2w-lucas
EOF
    print_success "Generated namespace.yaml"

    # rbac.yaml
    cat > "$OUTPUT_DIR/rbac.yaml" << EOF
apiVersion: v1
kind: ServiceAccount
metadata:
  name: a2w-lucas
  namespace: ${LUCAS_NAMESPACE}
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: a2w-lucas
rules:
  - apiGroups: [""]
    resources: ["pods", "pods/status"]
    verbs: ["get", "list", "watch"]
  - apiGroups: [""]
    resources: ["pods"]
    verbs: ["delete"]
  - apiGroups: [""]
    resources: ["pods/log"]
    verbs: ["get", "list"]
  - apiGroups: [""]
    resources: ["pods/exec"]
    verbs: ["create", "get"]
  - apiGroups: [""]
    resources: ["events"]
    verbs: ["get", "list", "watch"]
  - apiGroups: [""]
    resources: ["namespaces"]
    verbs: ["get", "list", "watch"]
  - apiGroups: [""]
    resources: ["configmaps"]
    verbs: ["get", "list"]
  - apiGroups: ["apps"]
    resources: ["deployments", "deployments/status", "deployments/scale", "statefulsets", "statefulsets/status", "statefulsets/scale"]
    verbs: ["get", "list", "watch", "patch", "update"]
  - apiGroups: ["apps"]
    resources: ["replicasets"]
    verbs: ["get", "list", "watch"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: a2w-lucas
subjects:
  - kind: ServiceAccount
    name: a2w-lucas
    namespace: ${LUCAS_NAMESPACE}
roleRef:
  kind: ClusterRole
  name: a2w-lucas
  apiGroup: rbac.authorization.k8s.io
EOF
    print_success "Generated rbac.yaml"

    # pvc.yaml
    cat > "$OUTPUT_DIR/pvc.yaml" << EOF
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: lucas-data
  namespace: ${LUCAS_NAMESPACE}
spec:
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: 1Gi
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: claude-sessions
  namespace: ${LUCAS_NAMESPACE}
spec:
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: 1Gi
EOF
    print_success "Generated pvc.yaml"

    if [ "$SECRET_BACKEND" = "sealed-secrets" ]; then
        print_info "Creating sealed secrets..."

        kubectl create secret generic llm-auth \
            --namespace="$LUCAS_NAMESPACE" \
            --from-literal=api-key="$LLM_API_KEY" \
            --dry-run=client -o yaml | \
            kubeseal --controller-namespace="$SEALED_SECRETS_NAMESPACE" \
                     --controller-name="$SEALED_SECRETS_CONTROLLER" \
                     --format=yaml > "$OUTPUT_DIR/sealed-llm-auth.yaml"
        print_success "Generated sealed-llm-auth.yaml"

        local slack_secret_args="--from-literal=bot-token=$SLACK_BOT_TOKEN --from-literal=app-token=$SLACK_APP_TOKEN"
        if [ -n "$SLACK_ALERT_CHANNEL" ]; then
            slack_secret_args="$slack_secret_args --from-literal=alert-channel=$SLACK_ALERT_CHANNEL"
        fi

        kubectl create secret generic slack-bot \
            --namespace="$LUCAS_NAMESPACE" \
            $slack_secret_args \
            --dry-run=client -o yaml | \
            kubeseal --controller-namespace="$SEALED_SECRETS_NAMESPACE" \
                     --controller-name="$SEALED_SECRETS_CONTROLLER" \
                     --format=yaml > "$OUTPUT_DIR/sealed-slack-bot.yaml"
        print_success "Generated sealed-slack-bot.yaml"

        kubectl create secret generic dashboard-auth \
            --namespace="$LUCAS_NAMESPACE" \
            --from-literal=username="$DASHBOARD_USER" \
            --from-literal=password="$DASHBOARD_PASS" \
            --dry-run=client -o yaml | \
            kubeseal --controller-namespace="$SEALED_SECRETS_NAMESPACE" \
                     --controller-name="$SEALED_SECRETS_CONTROLLER" \
                     --format=yaml > "$OUTPUT_DIR/sealed-dashboard-auth.yaml"
        print_success "Generated sealed-dashboard-auth.yaml"

        if [ -n "$SLACK_WEBHOOK_URL" ]; then
            kubectl create secret generic slack-webhook \
                --namespace="$LUCAS_NAMESPACE" \
                --from-literal=webhook-url="$SLACK_WEBHOOK_URL" \
                --dry-run=client -o yaml | \
                kubeseal --controller-namespace="$SEALED_SECRETS_NAMESPACE" \
                         --controller-name="$SEALED_SECRETS_CONTROLLER" \
                         --format=yaml > "$OUTPUT_DIR/sealed-slack-webhook.yaml"
            print_success "Generated sealed-slack-webhook.yaml"
        fi
    else
        print_info "Creating direct Kubernetes Secret manifests..."

        kubectl create secret generic llm-auth \
            --namespace="$LUCAS_NAMESPACE" \
            --from-literal=api-key="$LLM_API_KEY" \
            --dry-run=client -o yaml > "$OUTPUT_DIR/secret-llm-auth.yaml"
        print_success "Generated secret-llm-auth.yaml"

        local slack_secret_args="--from-literal=bot-token=$SLACK_BOT_TOKEN --from-literal=app-token=$SLACK_APP_TOKEN"
        if [ -n "$SLACK_ALERT_CHANNEL" ]; then
            slack_secret_args="$slack_secret_args --from-literal=alert-channel=$SLACK_ALERT_CHANNEL"
        fi

        kubectl create secret generic slack-bot \
            --namespace="$LUCAS_NAMESPACE" \
            $slack_secret_args \
            --dry-run=client -o yaml > "$OUTPUT_DIR/secret-slack-bot.yaml"
        print_success "Generated secret-slack-bot.yaml"

        kubectl create secret generic dashboard-auth \
            --namespace="$LUCAS_NAMESPACE" \
            --from-literal=username="$DASHBOARD_USER" \
            --from-literal=password="$DASHBOARD_PASS" \
            --dry-run=client -o yaml > "$OUTPUT_DIR/secret-dashboard-auth.yaml"
        print_success "Generated secret-dashboard-auth.yaml"

        if [ -n "$SLACK_WEBHOOK_URL" ]; then
            kubectl create secret generic slack-webhook \
                --namespace="$LUCAS_NAMESPACE" \
                --from-literal=webhook-url="$SLACK_WEBHOOK_URL" \
                --dry-run=client -o yaml > "$OUTPUT_DIR/secret-slack-webhook.yaml"
            print_success "Generated secret-slack-webhook.yaml"
        fi
    fi

    # agent-deployment.yaml
    cat > "$OUTPUT_DIR/agent-deployment.yaml" << EOF
apiVersion: apps/v1
kind: Deployment
metadata:
  name: a2w-lucas-agent
  namespace: ${LUCAS_NAMESPACE}
  labels:
    app: a2w-lucas-agent
spec:
  replicas: 1
  selector:
    matchLabels:
      app: a2w-lucas-agent
  template:
    metadata:
      labels:
        app: a2w-lucas-agent
    spec:
      serviceAccountName: a2w-lucas
${image_pull_secrets}
      initContainers:
        - name: fix-permissions
          image: busybox:latest
          command: ["sh", "-c", "chmod -R 777 /data && chmod -R 777 /home/claude"]
          securityContext:
            runAsUser: 0
          volumeMounts:
            - name: data
              mountPath: /data
            - name: claude-sessions
              mountPath: /home/claude/.claude
      containers:
        - name: agent
          image: ${IMAGE_REGISTRY}/lucas-agent:latest
          imagePullPolicy: Always
          env:
            - name: TARGET_NAMESPACE
              value: "${TARGET_NAMESPACE}"
            - name: TARGET_NAMESPACES
              value: "${TARGET_NAMESPACES}"
            - name: SRE_MODE
              value: "${LUCAS_MODE}"
            - name: LLM_BACKEND
              value: "${LLM_BACKEND}"
            - name: LLM_PROVIDER
              value: "${LLM_PROVIDER}"
            - name: CLAUDE_MODEL
              value: "${CLAUDE_MODEL}"
            - name: LLM_MODEL
              value: "${LLM_MODEL}"
            - name: LLM_BASE_URL
              value: "${LLM_BASE_URL}"
            - name: SQLITE_PATH
              value: "/data/lucas.db"
            - name: HOME
              value: "/home/claude"
            - name: SCAN_INTERVAL_SECONDS
              value: "${SCAN_INTERVAL}"
            - name: SLACK_EMERGENCY_ACTIONS_ENABLED
              value: "${SLACK_EMERGENCY_ACTIONS_ENABLED}"
            - name: SLACK_ACTION_ALLOWED_CHANNELS
              value: "${SLACK_ACTION_ALLOWED_CHANNELS}"
            - name: SLACK_ACTION_ALLOWED_USERS
              value: "${SLACK_ACTION_ALLOWED_USERS}"
            - name: SLACK_ACTION_ALLOWED_NAMESPACES
              value: "${SLACK_ACTION_ALLOWED_NAMESPACES}"
            - name: PROMPT_FILE
              value: "/app/master-prompt-interactive.md"
            - name: LLM_API_KEY
              valueFrom:
                secretKeyRef:
                  name: llm-auth
                  key: api-key
            - name: ANTHROPIC_API_KEY
              valueFrom:
                secretKeyRef:
                  name: llm-auth
                  key: api-key
                  optional: true
            - name: SLACK_BOT_TOKEN
              valueFrom:
                secretKeyRef:
                  name: slack-bot
                  key: bot-token
            - name: SLACK_APP_TOKEN
              valueFrom:
                secretKeyRef:
                  name: slack-bot
                  key: app-token
          volumeMounts:
            - name: data
              mountPath: /data
            - name: claude-sessions
              mountPath: /home/claude/.claude
          resources:
            requests:
              memory: "256Mi"
              cpu: "100m"
            limits:
              memory: "1Gi"
              cpu: "500m"
      volumes:
        - name: data
          persistentVolumeClaim:
            claimName: lucas-data
        - name: claude-sessions
          persistentVolumeClaim:
            claimName: claude-sessions
EOF
    print_success "Generated agent-deployment.yaml"

    # dashboard-deployment.yaml
    cat > "$OUTPUT_DIR/dashboard-deployment.yaml" << EOF
apiVersion: apps/v1
kind: Deployment
metadata:
  name: dashboard
  namespace: ${LUCAS_NAMESPACE}
  labels:
    app: dashboard
spec:
  replicas: 1
  selector:
    matchLabels:
      app: dashboard
  template:
    metadata:
      labels:
        app: dashboard
    spec:
      containers:
        - name: dashboard
          image: ${IMAGE_REGISTRY}/lucas-dashboard:latest
          imagePullPolicy: Always
          env:
            - name: SQLITE_PATH
              value: "/data/lucas.db"
            - name: PORT
              value: "8080"
            - name: LOG_PATH
              value: "/data/lucas.log"
            - name: AUTH_USER
              valueFrom:
                secretKeyRef:
                  name: dashboard-auth
                  key: username
            - name: AUTH_PASS
              valueFrom:
                secretKeyRef:
                  name: dashboard-auth
                  key: password
          ports:
            - containerPort: 8080
          volumeMounts:
            - name: data
              mountPath: /data
          resources:
            requests:
              memory: "64Mi"
              cpu: "50m"
            limits:
              memory: "128Mi"
              cpu: "100m"
          livenessProbe:
            httpGet:
              path: /health
              port: 8080
            initialDelaySeconds: 5
            periodSeconds: 10
          readinessProbe:
            httpGet:
              path: /health
              port: 8080
            initialDelaySeconds: 5
            periodSeconds: 5
      volumes:
        - name: data
          persistentVolumeClaim:
            claimName: lucas-data
EOF
    print_success "Generated dashboard-deployment.yaml"

    # dashboard-service.yaml
    cat > "$OUTPUT_DIR/dashboard-service.yaml" << EOF
apiVersion: v1
kind: Service
metadata:
  name: dashboard
  namespace: ${LUCAS_NAMESPACE}
spec:
  selector:
    app: dashboard
  ports:
    - protocol: TCP
      port: 80
      targetPort: 8080
  type: ClusterIP
EOF
    print_success "Generated dashboard-service.yaml"

    local cron_webhook_env=""
    if [ -n "$SLACK_WEBHOOK_URL" ]; then
        cron_webhook_env="
                - name: SLACK_WEBHOOK_URL
                  valueFrom:
                    secretKeyRef:
                      name: slack-webhook
                      key: webhook-url
                      optional: true"
    fi

    cat > "$OUTPUT_DIR/cronjob.yaml" << EOF
apiVersion: batch/v1
kind: CronJob
metadata:
  name: a2w-lucas
  namespace: ${LUCAS_NAMESPACE}
spec:
  schedule: "*/5 * * * *"
  concurrencyPolicy: Forbid
  successfulJobsHistoryLimit: 3
  failedJobsHistoryLimit: 3
  jobTemplate:
    spec:
      backoffLimit: 0
      ttlSecondsAfterFinished: 300
      template:
        spec:
          serviceAccountName: a2w-lucas
${cron_image_pull_secrets}
          restartPolicy: Never
          initContainers:
            - name: fix-permissions
              image: busybox:latest
              command: ["sh", "-c", "chmod -R 777 /data"]
              securityContext:
                runAsUser: 0
              volumeMounts:
                - name: data
                  mountPath: /data
          containers:
            - name: lucas
              image: ${IMAGE_REGISTRY}/lucas:latest
              imagePullPolicy: Always
              env:
                - name: TARGET_NAMESPACE
                  value: "${TARGET_NAMESPACE}"
                - name: TARGET_NAMESPACES
                  value: "${TARGET_NAMESPACES}"
                - name: SRE_MODE
                  value: "${LUCAS_MODE}"
                - name: SQLITE_PATH
                  value: "/data/lucas.db"
                - name: HOME
                  value: "/home/claude"
                - name: LLM_BACKEND
                  value: "${LLM_BACKEND}"
                - name: LLM_PROVIDER
                  value: "${LLM_PROVIDER}"
                - name: LLM_MODEL
                  value: "${LLM_MODEL}"
                - name: LLM_BASE_URL
                  value: "${LLM_BASE_URL}"
                - name: AUTH_MODE
                  value: "api-key"
                - name: LLM_API_KEY
                  valueFrom:
                    secretKeyRef:
                      name: llm-auth
                      key: api-key
                      optional: true${cron_webhook_env}
              volumeMounts:
                - name: data
                  mountPath: /data
          volumes:
            - name: data
              persistentVolumeClaim:
                claimName: lucas-data
EOF
    print_success "Generated cronjob.yaml"

    print_success "All manifests generated in $OUTPUT_DIR/"
}

apply_manifests() {
    print_step "Applying manifests to cluster"

    # Apply in order
    local files=(
        "namespace.yaml"
        "rbac.yaml"
        "pvc.yaml"
        "sealed-llm-auth.yaml"
        "secret-llm-auth.yaml"
        "sealed-slack-bot.yaml"
        "secret-slack-bot.yaml"
        "sealed-dashboard-auth.yaml"
        "secret-dashboard-auth.yaml"
        "sealed-slack-webhook.yaml"
        "secret-slack-webhook.yaml"
        "agent-deployment.yaml"
        "cronjob.yaml"
        "dashboard-deployment.yaml"
        "dashboard-service.yaml"
    )

    for file in "${files[@]}"; do
        if [ -f "$OUTPUT_DIR/$file" ]; then
            if [ -n "$KUBECTL_CONTEXT" ]; then
                kubectl --context "$KUBECTL_CONTEXT" apply -f "$OUTPUT_DIR/$file"
            else
                kubectl apply -f "$OUTPUT_DIR/$file"
            fi
            print_success "Applied $file"
        fi
    done

    echo ""
    print_success "Lucas deployed successfully!"
}

print_next_steps() {
    print_step "Next steps"

    echo ""
    echo "Lucas has been deployed to your cluster!"
    echo ""
    echo -e "${BOLD}Check deployment status:${NC}"
    echo "  kubectl get pods -n ${LUCAS_NAMESPACE}"
    echo ""
    echo -e "${BOLD}View agent logs:${NC}"
    echo "  kubectl logs -n ${LUCAS_NAMESPACE} -l app=a2w-lucas-agent -f"
    echo ""
    echo -e "${BOLD}Access dashboard:${NC}"
    echo "  kubectl port-forward -n ${LUCAS_NAMESPACE} svc/dashboard 8080:80"
    echo "  Then open: http://localhost:8080"
    echo "  Username: ${DASHBOARD_USER}"
    echo "  Password: (the one you configured)"
    echo ""
    echo -e "${BOLD}Interact via Slack:${NC}"
    echo "  @Lucas check pods in namespace ${TARGET_NAMESPACE%%,*}"
    echo "  @Lucas why is pod xyz crashing?"
    echo ""
    echo -e "${BOLD}Documentation:${NC}"
    echo "  https://github.com/a2wio/lucas"
    echo ""
}

generate_templates() {
    print_step "Generating template manifests"

    mkdir -p "$OUTPUT_DIR"

    print_info "Generating manifests with placeholder values..."
    print_info "You will need to create Kubernetes Secrets or Sealed Secrets manually."

    # Set placeholder values
    LUCAS_NAMESPACE="a2w-lucas"
    TARGET_NAMESPACE="default"
    LUCAS_MODE="autonomous"
    CLAUDE_MODEL="sonnet"
    SCAN_INTERVAL="3600"

    # namespace.yaml
    cat > "$OUTPUT_DIR/namespace.yaml" << EOF
apiVersion: v1
kind: Namespace
metadata:
  name: ${LUCAS_NAMESPACE}
  labels:
    app: a2w-lucas
EOF
    print_success "Generated namespace.yaml"

    # rbac.yaml
    cat > "$OUTPUT_DIR/rbac.yaml" << EOF
apiVersion: v1
kind: ServiceAccount
metadata:
  name: a2w-lucas
  namespace: ${LUCAS_NAMESPACE}
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: a2w-lucas
rules:
  - apiGroups: [""]
    resources: ["pods", "pods/status"]
    verbs: ["get", "list", "watch"]
  - apiGroups: [""]
    resources: ["pods"]
    verbs: ["delete"]
  - apiGroups: [""]
    resources: ["pods/log"]
    verbs: ["get", "list"]
  - apiGroups: [""]
    resources: ["pods/exec"]
    verbs: ["create", "get"]
  - apiGroups: [""]
    resources: ["events"]
    verbs: ["get", "list", "watch"]
  - apiGroups: [""]
    resources: ["namespaces"]
    verbs: ["get", "list", "watch"]
  - apiGroups: [""]
    resources: ["configmaps"]
    verbs: ["get", "list"]
  - apiGroups: ["apps"]
    resources: ["deployments", "deployments/status", "deployments/scale", "statefulsets", "statefulsets/status", "statefulsets/scale"]
    verbs: ["get", "list", "watch", "patch", "update"]
  - apiGroups: ["apps"]
    resources: ["replicasets"]
    verbs: ["get", "list", "watch"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: a2w-lucas
subjects:
  - kind: ServiceAccount
    name: a2w-lucas
    namespace: ${LUCAS_NAMESPACE}
roleRef:
  kind: ClusterRole
  name: a2w-lucas
  apiGroup: rbac.authorization.k8s.io
EOF
    print_success "Generated rbac.yaml"

    # pvc.yaml
    cat > "$OUTPUT_DIR/pvc.yaml" << EOF
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: lucas-data
  namespace: ${LUCAS_NAMESPACE}
spec:
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: 1Gi
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: claude-sessions
  namespace: ${LUCAS_NAMESPACE}
spec:
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: 1Gi
EOF
    print_success "Generated pvc.yaml"

    cat > "$OUTPUT_DIR/secrets-template.yaml" << 'EOF'
# IMPORTANT: Do not apply secrets with real values to Git.
# Create direct Kubernetes Secrets locally, or pipe them through kubeseal if you use Sealed Secrets:
#
# kubectl create secret generic llm-auth \
#     --namespace=a2w-lucas \
#     --from-literal=api-key="YOUR_LLM_API_KEY" \
#     --dry-run=client -o yaml > secret-llm-auth.yaml
#
# kubectl create secret generic slack-bot \
#     --namespace=a2w-lucas \
#     --from-literal=bot-token="xoxb-YOUR-BOT-TOKEN" \
#     --from-literal=app-token="xapp-YOUR-APP-TOKEN" \
#     --from-literal=alert-channel="C0123456789" \
#     --dry-run=client -o yaml > secret-slack-bot.yaml
#
# kubectl create secret generic dashboard-auth \
#     --namespace=a2w-lucas \
#     --from-literal=username="admin" \
#     --from-literal=password="YOUR_PASSWORD" \
#     --dry-run=client -o yaml > secret-dashboard-auth.yaml
EOF
    print_success "Generated secrets-template.yaml (instructions for creating secret manifests)"

    # agent-deployment.yaml with placeholders
    cat > "$OUTPUT_DIR/agent-deployment.yaml" << 'EOF'
apiVersion: apps/v1
kind: Deployment
metadata:
  name: a2w-lucas-agent
  namespace: a2w-lucas
  labels:
    app: a2w-lucas-agent
spec:
  replicas: 1
  selector:
    matchLabels:
      app: a2w-lucas-agent
  template:
    metadata:
      labels:
        app: a2w-lucas-agent
    spec:
      serviceAccountName: a2w-lucas
      initContainers:
        - name: fix-permissions
          image: busybox:latest
          command: ["sh", "-c", "chmod -R 777 /data && chmod -R 777 /home/claude"]
          securityContext:
            runAsUser: 0
          volumeMounts:
            - name: data
              mountPath: /data
            - name: claude-sessions
              mountPath: /home/claude/.claude
      containers:
        - name: agent
          image: ghcr.io/a2wio/lucas-agent:latest
          imagePullPolicy: Always
          env:
            - name: TARGET_NAMESPACE
              value: "default"  # Change to your namespace
            - name: TARGET_NAMESPACES
              value: "default"  # Comma-separated list
            - name: SRE_MODE
              value: "autonomous"  # or "watcher"
            - name: LLM_BACKEND
              value: "claude-code"  # or "openai-compatible"
            - name: LLM_PROVIDER
              value: "anthropic"  # or "groq", "kimi"
            - name: CLAUDE_MODEL
              value: "sonnet"  # Claude only
            - name: LLM_MODEL
              value: ""
            - name: LLM_BASE_URL
              value: ""
            - name: SQLITE_PATH
              value: "/data/lucas.db"
            - name: HOME
              value: "/home/claude"
            - name: SCAN_INTERVAL_SECONDS
              value: "3600"
            - name: PROMPT_FILE
              value: "/app/master-prompt-interactive.md"
            - name: LLM_API_KEY
              valueFrom:
                secretKeyRef:
                  name: llm-auth
                  key: api-key
            - name: ANTHROPIC_API_KEY
              valueFrom:
                secretKeyRef:
                  name: llm-auth
                  key: api-key
                  optional: true
            - name: SLACK_BOT_TOKEN
              valueFrom:
                secretKeyRef:
                  name: slack-bot
                  key: bot-token
            - name: SLACK_APP_TOKEN
              valueFrom:
                secretKeyRef:
                  name: slack-bot
                  key: app-token
            - name: SRE_ALERT_CHANNEL
              valueFrom:
                secretKeyRef:
                  name: slack-bot
                  key: alert-channel
                  optional: true
          volumeMounts:
            - name: data
              mountPath: /data
            - name: claude-sessions
              mountPath: /home/claude/.claude
          resources:
            requests:
              memory: "256Mi"
              cpu: "100m"
            limits:
              memory: "1Gi"
              cpu: "500m"
      volumes:
        - name: data
          persistentVolumeClaim:
            claimName: lucas-data
        - name: claude-sessions
          persistentVolumeClaim:
            claimName: claude-sessions
EOF
    print_success "Generated agent-deployment.yaml"

    # dashboard-deployment.yaml
    cat > "$OUTPUT_DIR/dashboard-deployment.yaml" << 'EOF'
apiVersion: apps/v1
kind: Deployment
metadata:
  name: dashboard
  namespace: a2w-lucas
  labels:
    app: dashboard
spec:
  replicas: 1
  selector:
    matchLabels:
      app: dashboard
  template:
    metadata:
      labels:
        app: dashboard
    spec:
      containers:
        - name: dashboard
          image: ghcr.io/a2wio/lucas-dashboard:latest
          imagePullPolicy: Always
          env:
            - name: SQLITE_PATH
              value: "/data/lucas.db"
            - name: PORT
              value: "8080"
            - name: LOG_PATH
              value: "/data/lucas.log"
            - name: AUTH_USER
              valueFrom:
                secretKeyRef:
                  name: dashboard-auth
                  key: username
            - name: AUTH_PASS
              valueFrom:
                secretKeyRef:
                  name: dashboard-auth
                  key: password
          ports:
            - containerPort: 8080
          volumeMounts:
            - name: data
              mountPath: /data
          resources:
            requests:
              memory: "64Mi"
              cpu: "50m"
            limits:
              memory: "128Mi"
              cpu: "100m"
          livenessProbe:
            httpGet:
              path: /health
              port: 8080
            initialDelaySeconds: 5
            periodSeconds: 10
          readinessProbe:
            httpGet:
              path: /health
              port: 8080
            initialDelaySeconds: 5
            periodSeconds: 5
      volumes:
        - name: data
          persistentVolumeClaim:
            claimName: lucas-data
EOF
    print_success "Generated dashboard-deployment.yaml"

    # dashboard-service.yaml
    cat > "$OUTPUT_DIR/dashboard-service.yaml" << 'EOF'
apiVersion: v1
kind: Service
metadata:
  name: dashboard
  namespace: a2w-lucas
spec:
  selector:
    app: dashboard
  ports:
    - protocol: TCP
      port: 80
      targetPort: 8080
  type: ClusterIP
EOF
    print_success "Generated dashboard-service.yaml"

    echo ""
    print_success "All template manifests generated in $OUTPUT_DIR/"
    echo ""
    print_warning "Next steps:"
    echo "  1. Review and edit the manifests as needed"
    echo "  2. Create direct secrets or sealed secrets using the commands in secrets-template.yaml"
    echo "  3. Apply: kubectl apply -f $OUTPUT_DIR/"
    echo ""
}

main() {
    print_banner

    if [ "$1" = "--env-file" ] && [ -n "$2" ]; then
        load_env_file "$2"
        check_prerequisites
        generate_manifests
        print_success "Manifests generated from env file in: ${OUTPUT_DIR}"
        return
    fi

    echo -e "${BOLD}Welcome to the Lucas installer!${NC}"
    echo ""
    echo "This script will help you deploy Lucas to your Kubernetes cluster."
    echo ""

    check_prerequisites

    echo ""
    echo -e "${CYAN}?${NC} How would you like to proceed?" > /dev/tty
    echo "  1) Guided setup - Interactive prompts for all configuration" > /dev/tty
    echo "  2) Generate templates - Create manifest files with placeholders" > /dev/tty
    echo "  3) Exit - I'll install manually from GitHub" > /dev/tty
    echo -ne "Enter choice [1-3]: " > /dev/tty
    read choice < /dev/tty

    case "$choice" in
        1)
            configure_installation
            generate_manifests

            echo ""
            echo -e "${BOLD}Manifests generated in: ${OUTPUT_DIR}/${NC}"
            echo ""
            ls -la "$OUTPUT_DIR/"

            echo ""
            if prompt_yes_no "Would you like to apply these manifests to your cluster now?" "y"; then
                apply_manifests
                print_next_steps
            else
                echo ""
                print_info "To apply later, run:"
                echo "  kubectl apply -f $OUTPUT_DIR/"
                echo ""
                print_next_steps
            fi
            ;;
        2)
            prompt_value "Output directory for manifests" "$OUTPUT_DIR" OUTPUT_DIR
            generate_templates
            ;;
        3|*)
            echo ""
            print_info "To install manually, download the manifests from:"
            echo "  https://github.com/a2wio/lucas/tree/main/k8s"
            echo ""
            print_info "Documentation:"
            echo "  https://github.com/a2wio/lucas"
            echo ""
            ;;
    esac
}

# Run main function
main "$@"
