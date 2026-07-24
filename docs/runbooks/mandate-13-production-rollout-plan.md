# Mandate 13 - Ke hoach rollout production an toan

Tai lieu nay giai thich ro thay doi du kien cho Mandate 13, tai sao can thay doi, rui ro nao da duoc kiem soat, va can verify gi sau khi merge.

## 1. Muc tieu

Thay doi nay nham day production toi trang thai co the dat cac dieu kien con thieu cua Mandate 13:

1. spot ratio dat it nhat 50% theo node count
2. co arm64/Graviton live tren production
3. khong dong truc tiep vao duong checkout/place-order truoc khi quay video

## 2. Hien trang truoc thay doi

Snapshot read-only ngay 24/07/2026:

- Tong node: `8`
- Spot node: `3`
- On-demand node: `5`
- Ty le spot: `37.5%`
- Toan bo node dang la `amd64`

Nhan dinh:

- Production da co spot that
- Critical path da chay tren spot
- Nhung chua dat `>= 50% spot`
- Chua co `arm64` live, nen chua claim duoc Graviton

## 3. Thay doi duoc dua vao PR

## 3.1. Tat stateful nodegroup dang rong

Phan Terraform duoc them de cho phep tat han `stateful_1a` bang bien `enable_stateful_node_group = false`.

Ly do:

- Nodegroup nay duoc tao cho PostgreSQL/Valkey in-cluster
- Hai datastore nay da retire o production
- Kiem tra thuc te khong con pod `techx-tf3` nao nam tren node do
- Giu node on-demand rong se lam ty le spot xau di ma khong tang an toan he thong

Tac dung mong doi:

- Giam 1 on-demand node rong
- Khong giam headroom cua 4 node on-demand dang gang observability va workload nen

## 3.2. Them 1 arm64 spot NodePool rieng

Them `flash-sale-spot-arm64` trong Karpenter voi:

- `kubernetes.io/arch = arm64`
- `karpenter.sh/capacity-type = spot`
- taint rieng `techx.io/arch = arm64:NoSchedule`

Ly do:

- NodePool spot hien tai hardcode `amd64`
- Du image da multi-arch thi production van khong len duoc arm64 neu khong mo nodepool rieng
- Tach nodepool arm64 rieng giup rollout theo cach co kiem soat, khong day toan bo workload sang arm64 ngay

## 3.3. Chi opt-in `recommendation` sang arm64

Them file override rieng `values-mandate13.yaml` va moc vao Argo Application.

Workload duoc chon:

- `recommendation`

Ly do chon:

- la workload stateless
- khong nam tren duong place-order truc tiep
- image dang deploy la OCI image index, co the hien la multi-arch
- failure cua no co tac dong hep hon so voi `checkout`, `frontend-proxy`, `cart`

## 4. Tai sao khong sua manh tay hon

Khong chon cac huong sau:

- khong giam node on-demand observability dang ganh Grafana/Prometheus/Jaeger/OpenSearch
- khong dua `checkout` len arm64 ngay
- khong doi nodepool spot hien co tu `amd64` sang `amd64+arm64` cho tat ca workload

Ly do:

- cac huong do kho predict hon
- de lam xau he thong that truoc khi co evidence
- kho khoanh vung neu rollout loi

Phuong an trong PR nay uu tien:

- thay doi it nhat
- de rollback
- de chung minh yeu cau mandate truoc

## 5. Kiem tra an toan da lam truoc PR

Da kiem tra:

1. `kubectl top nodes`
   - node `ip-10-0-4-166` dung rat thap
2. `kubectl -n techx-tf3 get pods -o wide --field-selector spec.nodeName=ip-10-0-4-166...`
   - khong co pod `techx-tf3` nao tren node stateful
3. `kubectl get nodeclaims`
   - hien co 3 spot nodeclaim
4. `aws ecr describe-images` cho tag recommendation dang deploy
   - `imageManifestMediaType = application/vnd.oci.image.index.v1+json`
   - xac nhan la manifest list, khong phai single-arch image
5. `terraform validate`
   - pass
6. `kubectl apply --dry-run=client -f gitops/karpenter/spot-nodepool.yaml`
   - pass
7. `kubectl apply --dry-run=client -f gitops/apps/techx-corp.yaml`
   - pass
8. `terraform plan -refresh=false "-target=module.eks_platform"`
   - cho thay y do chinh la destroy nodegroup `stateful_1a`

## 6. Anh huong du kien sau merge

Neu rollout thanh cong:

- `stateful_1a` bi go bo
- Karpenter co the tao 1 arm64 spot node moi khi `recommendation` can schedule
- Tong the node sau on dinh du kien:
  - 4 spot
  - 4 on-demand
  - ty le spot = `50%`
- Production co arm64 live de claim Graviton

## 7. Rui ro con lai

Van con 3 nhom rui ro can theo doi sau merge:

1. `recommendation` co the image multi-arch nhung runtime van gap issue rieng tren arm64
2. Karpenter co the chua tao arm64 node neu scheduler chua canh tranh du de dat pod moi
3. Go `stateful_1a` la thay doi ha tang that, can xac nhan lai khong con phu thuoc an danh nao ngoai `techx-tf3`

## 8. Cach verify sau merge

Chay cac lenh sau:

```powershell
kubectl --kubeconfig C:\Users\Admin\.kube\config --server=https://localhost:8443 --insecure-skip-tls-verify=true get nodes -L karpenter.sh/capacity-type,node.kubernetes.io/instance-type,kubernetes.io/arch,topology.kubernetes.io/zone
```

```powershell
kubectl --kubeconfig C:\Users\Admin\.kube\config --server=https://localhost:8443 --insecure-skip-tls-verify=true -n techx-tf3 get pods -o wide
```

```powershell
kubectl --kubeconfig C:\Users\Admin\.kube\config --server=https://localhost:8443 --insecure-skip-tls-verify=true get nodeclaims
```

```powershell
$nodes = kubectl --kubeconfig C:\Users\Admin\.kube\config --server=https://localhost:8443 --insecure-skip-tls-verify=true get nodes -L karpenter.sh/capacity-type --no-headers
$spot = ($nodes | Select-String "spot").Count
$total = ($nodes | Measure-Object).Count
"total=$total spot=$spot ratio=$([math]::Round(($spot*100.0)/$total,2))%"
```

Dieu can thay:

- co node `arm64`
- `recommendation` nam tren node `arm64`
- spot ratio dat `>= 50%`
- he thong van xanh, khong co pod critical bi Pending

## 9. Binh luan cho buoi review

Noi gon:

- thay doi nay khong co tinh chat “toi uu dep”
- day la rollout co chu dich de dat 2 gap con thieu cua Mandate 13 la `spot ratio` va `arm64 live`
- chon workload nhe va bo node rong de giam rui ro production
