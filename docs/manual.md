# Lucas 간단 메뉴얼

이 문서는 사람이 빠르게 현재 Lucas 기능을 이해하고 운영 상태를 따라가기 위한 간단 안내서입니다.

## 이 문서의 용도

- 운영자나 담당자가 지금 Lucas가 무슨 기능을 하고 있는지 빠르게 이해하기 위한 문서입니다.
- 기능명세 전체를 다 읽기 전에 큰 흐름을 파악하기 위한 문서입니다.
- 현재 어떤 기능이 실제로 붙어 있는지 사람 기준으로 보기 쉽게 정리한 문서입니다.

## 이 문서는 구현의 기준 문서가 아닙니다

- 이 문서는 사람용 빠른 안내서입니다.
- 기능 개발이나 구조 변경의 source of truth 는 `docs/specs/` 와 `docs/ops/` 아래 문서입니다.
- 에이전트나 개발 작업은 보통 이 문서를 읽지 않아도 됩니다.
- 구현 기준이 필요하면 먼저 `docs/specs/index.md` 와 `docs/specs/current-platform-state.md` 를 보세요.

## 지금 Lucas에서 볼 수 있는 큰 기능

### 1. Redis health check / Redis safe self-recovery

- Redis 상태를 보고 이상 징후를 감시합니다.
- 자동 조치는 매우 제한적으로 설계되어 있습니다.
- 현재 기본 방향은 “안전한 범위에서만”, 그리고 “필요할 때만 켜는 기능”입니다.
- 현재 템플릿 기본값은 비활성화입니다.

관련 상세 문서:

- `docs/specs/prd-redis-safe-self-recovery.md`
- `docs/specs/trd-redis-safe-self-recovery.md`
- `docs/specs/implementation-plan-redis-safe-self-recovery.md`

### 2. AI Pod 감시 / 보안 의심 행위 감시

- OCI virtual node 환경 제약 때문에 일반적인 host-level 보안 도구 대신 보완 통제 방식으로 설계된 기능입니다.
- 현재 방향은 report-only 입니다.
- 모든 namespace를 강제로 보는 것이 아니라, 필요한 namespace만 대상으로 둘 수 있게 설계돼 있습니다.
- 현재 템플릿 기본값은 비활성화입니다.

관련 상세 문서:

- `docs/specs/prd-virtual-node-compensating-malware-control.md`
- `docs/specs/trd-virtual-node-compensating-malware-control.md`
- `docs/specs/implementation-plan-virtual-node-compensating-malware-control.md`

### 3. Drift Auditor

- 코드/설정/저장소 상태가 의도와 다르게 흘러가는 drift를 감시하는 기능입니다.
- 첫 단계는 read-only / report 중심입니다.
- 운영자가 “지금 실제 상태가 설계와 어긋났는지” 보기 위한 하드닝 기능입니다.

관련 상세 문서:

- `docs/specs/prd-drift-auditor.md`
- `docs/specs/trd-drift-auditor.md`
- `docs/specs/implementation-plan-drift-auditor.md`

### 4. Dashboard

- 최근 실행 결과, 세션, 비용, 운영 상태를 보는 웹 UI 입니다.
- 현재 방향은 Postgres 기반 상태 조회입니다.
- 예전처럼 shared SQLite report path에 계속 묶이지 않도록 정리하는 방향으로 바뀌었습니다.

관련 상세 문서:

- `docs/ops/dashboard.md`
- `docs/ops/operations.md`

### 5. Postgres 전환

- Lucas 저장 상태를 shared SQLite에서 Postgres로 옮기는 작업입니다.
- dev에서는 이미 direct Postgres write 상태까지 확인된 단계입니다.
- production cutover는 별도 통제된 단계로 보는 것이 맞습니다.

관련 상세 문서:

- `docs/specs/prd-postgres-migration.md`
- `docs/specs/trd-postgres-migration.md`
- `docs/specs/implementation-plan-postgres-migration.md`
- `docs/ops/current-runtime-settings.md`

## 사람이 지금 가장 먼저 보면 좋은 문서 순서

1. `docs/manual.md`
2. `docs/specs/current-platform-state.md`
3. `docs/ops/current-runtime-settings.md`
4. 필요한 개별 기능 문서 (`docs/specs/*.md`)

## 지금 설정값을 보고 싶으면

- 현재 적용된 non-secret runtime 값과 secret reference 이름은 `docs/ops/current-runtime-settings.md`

## 지금 전체 기술 상태를 보고 싶으면

- 전체 workstream 기준 기술 상태 요약은 `docs/specs/current-platform-state.md`

## 기능명세 전체 목록을 보고 싶으면

- 기능별 PRD / TRD / 구현계획 목록은 `docs/specs/index.md`
