# Security Hardening - Phase 12

Tai lieu nay ghi cac rule bao mat can giu khi demo chung, staging va production.

## 1. RBAC va admin action

- Root admin moi duoc tao/demote/promote admin.
- Root admin moi duoc retry embedding job loai `permanent` hoac `include_permanent=true`.
- Cac action rui ro phai co `reason`:
  - reject entity
  - disable KG
  - merge entity
  - retry permanent embedding jobs
  - taxonomy alias mapping
  - request more information
  - mark/disable orphan from recommendation
- Tat ca action governance/embedding/admin quan trong phai ghi audit log.

## 2. Rate limit

Rate limit mac dinh bat qua `RATE_LIMIT_ENABLED=true`.

Nhom dang duoc gioi han:

- `auth_register`: 5 request/phut/IP
- `auth_login`: 10 request/phut/IP
- `profile_update`: 30 request/phut/IP
- `project_create`: 10 request/phut/IP
- `embedding_recompute`: 20 request/phut/IP
- admin governance / embedding / user-management mutations

Ghi chu: limiter hien la in-memory, phu hop single backend process. Khi scale nhieu backend replicas, can chuyen sang Redis-backed limiter.

## 3. Secret va production env

Khong dung cac gia tri default trong production:

- `APP_AUTH_SECRET=dev-change-me`
- `ROOT_ADMIN_PASSWORD=Admin@123456`
- `NEO4J_PASSWORD=password|your_password|neo4j`
- RabbitMQ `guest:guest` neu `ENVIRONMENT=production`
- `CORS_ORIGINS=*`

Kiem tra nhanh:

```powershell
cd backend
python scripts\check_phase12_security_config.py
```

Script se tao:

```text
backend/scripts/phase12_security_config_report.json
```

Script khong in secret that, chi report issue da redact.

## 4. Frontend dependency audit

Khong chay:

```powershell
npm audit fix --force
```

neu chua review breaking changes.

Quy trinh dung:

```powershell
cd frontend
npm audit --json
npm run typecheck
npm run build
```

Neu can fix dependency:

1. Fix tung nhom package.
2. Commit lockfile rieng.
3. Chay `npm run typecheck`.
4. Chay `npm run build`.
5. Smoke test UI login/dashboard/admin.

## 5. Pending cho scale lon

- Doi in-memory rate limiter sang Redis-backed limiter khi backend co nhieu replica.
- Them CSP/security headers neu publish public domain.
- Them SAST/dependency audit trong CI.
- Review npm audit high/critical theo tung dependency thay vi fix force.
