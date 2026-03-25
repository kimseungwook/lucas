# Lucas 빠른 사용자 매뉴얼

> 이 문서는 **사람이 빠르게 읽는 한국어 안내서**입니다.  
> 실제 구현 기준, 상세 설계, 운영 제한사항은 `docs/specs/`와 `docs/ops/` 문서를 기준으로 확인해야 합니다.

## Lucas가 무엇인가

Lucas는 Kubernetes 환경에서 동작하는 운영·신뢰성 에이전트입니다.

현재 기준으로 Lucas는 크게 세 가지 경로로 동작합니다.

- **Slack 인터랙티브 에이전트**: 멘션이나 스레드 답글로 점검과 조사 수행
- **정기 점검 경로**: 주기적으로 namespace를 스캔하고 결과를 저장/알림
- **대시보드**: runs, sessions, token/cost, 상태 요약 확인

즉 Lucas는 “문제가 생겼을 때 사람이 kubectl로 직접 하나씩 보는 작업”을 줄이고, 1차 진단과 보고를 더 빠르게 만들기 위한 도구입니다.

## Lucas가 잘하는 일

- Pod 상태, restart, 이벤트, 로그 기반의 1차 점검
- Slack에서 운영자와 상호작용하며 원인 후보 정리
- 정기 스캔을 통한 이상 징후 요약
- 실행 결과를 저장하고 대시보드에서 다시 확인
- 일부 제한된 자동 복구 경로(예: Redis self-recovery)
- Drift, suspicious behavior, pod incident 같은 **증거 기반 보고**

Lucas는 만능 자동 복구 시스템이 아닙니다.  
특히 보안, 인프라, 스토리지, 이미지, 설정 문제는 **증거를 모아 사람에게 escalation**하는 쪽이 기본입니다.

## 빠른 시작

1. LLM API 키와 Slack 토큰을 Secret 또는 Sealed Secret으로 준비합니다.
2. `k8s/` 아래 manifest를 배포합니다.
3. Slack 채널에 Lucas bot을 초대합니다.
4. Dashboard에 접속해서 최근 run과 상태를 확인합니다.

정기 점검을 쓰려면 `SRE_ALERT_CHANNEL`이 설정되어 있어야 하고, 스캔 대상은 `TARGET_NAMESPACE` / `TARGET_NAMESPACES`로 정합니다.

## 운영 모드 이해하기

Lucas는 운영 모드에 따라 행동이 달라집니다.

- **watcher / report 모드**: 읽기 전용. 보고와 권고 중심
- **autonomous 모드**: 제한된 자동 조치 가능

실무에서는 먼저 **watcher/report 모드로 충분히 관찰**하고, 안전한 자동화만 별도로 좁혀서 여는 것이 좋습니다.

## Slack에서 어떻게 쓰나

### 1. 인터랙티브 조사

Slack에서 Lucas를 멘션하거나 스레드로 질문하면, Lucas가 현재 Kubernetes 상태를 바탕으로 조사 결과를 답합니다.

예시:

- 특정 pod가 왜 죽는지 확인
- 어떤 namespace에 restart가 많은지 점검
- 이벤트와 로그를 보고 원인 후보 정리

### 2. 정기 점검 알림

정기 점검이 켜져 있으면 Lucas가 주기적으로 상태를 살펴보고 Slack에 요약을 올립니다.

요약 메시지에는 보통 다음 정보가 포함됩니다.

- 전체 pod 수
- 에러 수
- restart가 있는 pod 수
- 상위 problematic pod
- 필요하면 drift / redis recovery / security suspicion / pod incident 섹션

## Pod 장애를 볼 때 Lucas가 주는 관점

최근 Lucas는 pod 장애를 단순히 “죽었다” 수준이 아니라, **incident triage 관점**으로 더 잘 설명할 수 있게 확장되었습니다.

메시지나 보고에서 다음 정보를 함께 볼 수 있습니다.

- 현재 `phase`
- `reason`
- restart count
- owner workload
- blast radius
- evidence
- likely cause
- recommended action

특히 소스코드를 바로 고칠 수 없는 프로젝트에서는 이 정보가 중요합니다.  
이 경우 Lucas는 대체로 다음 bucket 중 하나로 상황을 좁힙니다.

- `config_or_secret_failure`
- `image_or_startup_failure`
- `resource_or_probe_failure`
- `dependency_connectivity_failure`
- `infra_or_placement_failure`
- `pod_local_transient_failure`

즉 Slack 메시지 자체가 단순 알림이 아니라 **1차 진단 결과** 역할을 하게 됩니다.

## 자주 보는 운영 기능

### Scheduled scans

- 여러 namespace를 주기적으로 검사합니다.
- Slack 채널에 요약을 올립니다.
- 현재는 Kubernetes 상태와 런타임 신호를 바탕으로 **짧고 읽기 쉬운 결과**를 만드는 쪽에 초점을 둡니다.

### Drift Auditor

- read-only 중심의 drift 탐지 경로입니다.
- storage, runtime surface, deployment-vs-cron 차이 같은 drift를 보고합니다.

### Redis Safe Self-Recovery

- opt-in 기능입니다.
- 현재 승인된 자동 조치는 제한적이며, 핵심은 **안전한 조건에서 단일 pod 삭제 정도의 보수적 복구**입니다.

### Virtual-node compensating malware control

- OCI virtual node 환경을 고려한 compensating control입니다.
- 현재 방향은 **report-only, namespace-scoped, feature-flagged** 입니다.
- AI는 detector 자체가 아니라, deterministic signal을 해석하고 다음 조치를 정리하는 역할입니다.

## 자주 확인하는 설정

비밀값은 이 문서에 적지 않습니다.  
대신 운영 시 자주 보는 일반 설정은 아래와 같습니다.

- `TARGET_NAMESPACE`
- `TARGET_NAMESPACES`
- `SCAN_INTERVAL_SECONDS`
- `SRE_ALERT_CHANNEL`
- `SRE_MODE`
- `PROMPT_FILE`

최근 추가된 pod incident triage 범위 제어용 설정:

- `POD_INCIDENT_TARGET_NAMESPACES`
- `POD_INCIDENT_TARGET_WORKLOADS`

이 값들은 feature scope를 줄이는 데 유용합니다.  
예를 들어 특정 namespace나 특정 workload만 incident triage 대상으로 묶을 수 있습니다.

## Lucas를 사용할 때의 기본 원칙

1. **증거를 먼저 본다**
   - 이벤트, 상태, restart, 로그를 먼저 확인합니다.
2. **원인과 증거를 섞지 않는다**
   - evidence와 likely cause는 따로 봐야 합니다.
3. **애매하면 restart churn보다 escalation**
   - config, image, dependency, infra 문제는 무작정 재시작하는 것보다 소유자에게 넘기는 게 낫습니다.
4. **manual은 빠른 안내서일 뿐**
   - 상세 acceptance criteria와 설계는 `specs/`가 기준입니다.

## 어디를 먼저 보면 되나

### 운영자라면

먼저 아래 순서로 보는 것이 좋습니다.

1. `/manual` — 빠른 개요
2. `/ops/current-runtime-settings` — 현재 설정 확인
3. `/ops/operations` — 운영 경계와 체크리스트
4. `/specs/current-platform-state` — 현재 기술 상태 요약

### 변경 작업을 하려면

바로 manual만 보고 구현하면 안 됩니다. 아래를 기준으로 보세요.

1. `docs/specs/index.md`
2. 해당 기능의 PRD/TRD/implementation plan
3. `docs/ops/*` 운영 문서

## 저장소 구조 빠르게 보기

- `src/agent/` : Slack agent, scheduler, runbooks, 운영 로직
- `src/dashboard/` : 대시보드
- `k8s/` : 배포 manifest
- `docs/specs/` : 상세 명세
- `docs/ops/` : 운영 문서

## 마지막으로

이 문서는 Lucas를 빨리 이해하기 위한 **사람용 안내서**입니다.  
“지금 Lucas가 대략 어떤 역할을 하고, 어디까지 자동화하고, 어디서 더 자세히 봐야 하는지”를 빠르게 파악하는 데 쓰면 됩니다.

정확한 설계와 구현 기준이 필요하면, 항상 아래 문서로 내려가세요.

- `docs/specs/index.md`
- `docs/specs/current-platform-state.md`
- `docs/ops/current-runtime-settings.md`
- `docs/ops/operations.md`
