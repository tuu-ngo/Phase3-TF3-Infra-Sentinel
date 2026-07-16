# Bao cao Pod Security hardening - 2026-07-16

## Muc tieu

Yeu cau can dap ung:

- Khong container nao chay root.
- Buoc `runAsNonRoot`.
- Drop cac Linux capabilities khong can thiet, mac dinh `capabilities.drop: ["ALL"]`.
- Chi giu capability that su can, hien tai chua ghi nhan service nao can add capability rieng.
- Lam theo tung buoc de giam rui ro downtime, khong bat enforce/restricted dot ngot.

## Pham vi da thuc hien

Branch hien tai: `hieu`

Commit lien quan:

- `e9549be security: harden non-root workload contexts`
- `e7c10a9 security: enforce non-root app containers`
- `e865b2f fix: conflict in product review`

### 1. Harden cac workload da non-root san

Da them `securityContext`/`podSecurityContext` cho cac service da co runtime user non-root hoac image non-root ro rang:

- `frontend-proxy`
- `image-provider`
- `quote`
- `kafka` main container
- `valkey-cart`
- `accounting`
- `fraud-detection`
- `product-catalog`

Cac truong chinh da ap dung:

```yaml
securityContext:
  runAsNonRoot: true
  allowPrivilegeEscalation: false
  capabilities:
    drop: ["ALL"]

podSecurityContext:
  seccompProfile:
    type: RuntimeDefault
```

### 2. Sua Dockerfile cho cac app image truoc do chay root

Da them non-root user vao Dockerfile cho cac service app-owned:

- `ad`
- `cart`
- `currency`
- `email`
- `llm`
- `load-generator`
- `product-reviews`
- `recommendation`

Mau thay doi chinh:

- Tao user/group non-root, phan lon dung UID/GID `65532`.
- `chown` thu muc app can thiet.
- Dat `USER 65532:65532`.
- Voi Python image, them:

```dockerfile
ENV PYTHONDONTWRITEBYTECODE=1
```

Ly do: tranh Python tu ghi `.pyc` / `__pycache__` luc runtime, giam nhu cau ghi filesystem va chuan bi tot hon neu sau nay bat `readOnlyRootFilesystem`.

### 3. Enforce lai tren Helm values

Sau khi Dockerfile co user non-root, da them `securityContext` vao Helm values cho cac service do:

- `ad`
- `cart`
- `currency`
- `email`
- `llm`
- `load-generator`
- `product-reviews`
- `recommendation`

Da harden them initContainer cho cac job cho dependency:

- `accounting.wait-for-kafka`
- `fraud-detection.wait-for-kafka`
- `cart.wait-for-valkey-cart`

InitContainer nay chi dung `nc` de cho dependency, khong can root, nen da ap:

```yaml
runAsUser: 65534
runAsGroup: 65534
runAsNonRoot: true
allowPrivilegeEscalation: false
capabilities:
  drop: ["ALL"]
```

## Ket qua hien tai trong code

Tong so component enabled trong `values.yaml`: `22`

Main container da co day du:

- `runAsNonRoot: true`
- `allowPrivilegeEscalation: false`
- `capabilities.drop: ["ALL"]`

Ket qua: `20/22` main containers.

Da dat:

- `accounting`
- `ad`
- `cart`
- `checkout`
- `currency`
- `email`
- `fraud-detection`
- `frontend`
- `frontend-proxy`
- `image-provider`
- `kafka`
- `llm`
- `load-generator`
- `payment`
- `product-catalog`
- `product-reviews`
- `quote`
- `recommendation`
- `shipping`
- `valkey-cart`

Chua dat:

- `flagd` - da them baseline securityContext cho main container, sidecar `flagd-ui`, va init container; can rollout test live.
- `postgresql` - da them baseline securityContext + fsGroup; can rollout test live vi day la workload stateful.

## Nhung diem chua xu ly co chu dich

### 1. `postgresql`

`postgresql` la datastore stateful, co PVC va data path rieng. Da them `runAsNonRoot`, `runAsUser: 999`, `runAsGroup: 999`, `fsGroup: 999`, `allowPrivilegeEscalation: false`, va drop `ALL` capability trong chart. Can rollout test live de xac nhan PVC va `PGDATA` van ghi duoc.

### 2. `flagd`

`flagd` la third-party image. Da harden main container, `flagd-ui` sidecar, va `init-config` container bang baseline non-root + drop capability + seccomp/pod fsGroup. Can rollout test live de xac nhan khong co path ghi nao bi thieu quyen.

### 3. Kafka initContainer van chay root

Main container `kafka` da harden non-root, nhung trong `phase3 - information/deploy/values-prod.yaml` van co:

```yaml
initContainers:
  - name: init-kafka-data
    securityContext:
      runAsUser: 0
```

Ly do chua sua ngay: initContainer nay dang tao/chown `/var/lib/kafka/data` tren PVC. Neu bo root ma chua thay co che permission thay the, Kafka co the mat quyen ghi volume va fail startup.

Huong can thao luan:

- Dung `fsGroup`/`fsGroupChangePolicy` neu du.
- Pre-provision PVC/data path voi owner dung.
- Hoac giu exception co thoi han cho initContainer root, kem ly do ro.

## Rui ro downtime va cach giam thieu

Cac thay doi Dockerfile can build image moi. Khi deploy:

1. Khong rollout toan bo cung luc.
2. Uu tien batch nho:
   - Batch A: service replica >= 2 va it stateful.
   - Batch B: service co dependency DB/Kafka.
   - Batch C: service con lai.
3. Sau moi batch:

```bash
kubectl -n techx-tf3 rollout status deploy/<service>
kubectl -n techx-tf3 get pods
kubectl -n techx-tf3 logs deploy/<service> --tail=100
```

4. Rieng checkout path can theo doi:

- `frontend`
- `frontend-proxy`
- `checkout`
- `cart`
- `currency`
- `payment`
- `product-catalog`
- `shipping`
- `postgresql`
- `kafka`
- `valkey-cart`

5. Neu service CrashLoop sau rollout, rollback image/tag hoac revert commit tuong ung.

## Trang thai yeu cau

Hien tai code da tien rat gan toi yeu cau cho app-owned workload:

- Main app containers: `20/22` da co hardening day du.
- App image truoc do chay root da duoc them non-root user.
- Chua dat tuyet doi "khong container nao chay root" vi con:
  - `postgresql`
  - `flagd`
  - Kafka `init-kafka-data` root initContainer

Ket luan: phan app-owned stateless/near-stateless da duoc harden trong code. Phan con lai can quyet dinh cung team vi lien quan stateful volume va third-party image, khong nen ep nhanh de tranh outage.
