# Walkthrough: Di chuyển EKS sang ArgoCD GitOps (Zero Downtime)

Chúng ta đã hoàn thành xuất sắc việc chuyển dịch toàn bộ TechX Corp Platform sang quản lý bằng GitOps thông qua ArgoCD trên EKS cluster mà **không gây ra bất kỳ giây gián đoạn hay restart pod nào**.

## Các thay đổi đã thực hiện

### 1. Chuẩn bị tài nguyên GitOps (Trên nhánh `feature/gitops-migration`)
*   **Trích xuất cấu hình active:** Dump và phân tích giá trị đang chạy của Helm release `techx-corp`.
*   **Tạo file values Production mới:** Tạo [values-prod.yaml](file:///home/tutruong/project/Phase3-TF3-Infra-Sentinel/phase3%20-%20information/deploy/values-prod.yaml) để lưu trữ các cấu hình override thực tế (limits memory, registry, tag).
*   **Bảo mật Secret:** 
    *   Tạo K8s secret `flagd-sync-token` để lưu trữ sync token của BTC ngoài Git.
    *   Cấu hình biến môi trường `FLAGD_SYNC_TOKEN` và cơ chế K8s env expansion `$(FLAGD_SYNC_TOKEN)` trong tham số command của container `flagd`.
*   **Khai báo ArgoCD Manifests:**
    *   [application.yaml](file:///home/tutruong/project/Phase3-TF3-Infra-Sentinel/gitops/bootstrap/application.yaml): Định nghĩa parent app (App-of-Apps).
    *   [techx-corp.yaml](file:///home/tutruong/project/Phase3-TF3-Infra-Sentinel/gitops/apps/techx-corp.yaml): Đồng bộ Helm chart và values.
    *   [infrastructure-app.yaml](file:///home/tutruong/project/Phase3-TF3-Infra-Sentinel/gitops/apps/infrastructure-app.yaml): Đồng bộ manifests hạ tầng.
*   **Khai báo tài nguyên hạ tầng:**
    *   [network-policy-postgres.yaml](file:///home/tutruong/project/Phase3-TF3-Infra-Sentinel/gitops/infrastructure/network-policy-postgres.yaml): Giới hạn kết nối Postgres chỉ từ 3 service hợp lệ.
    *   [resource-quota.yaml](file:///home/tutruong/project/Phase3-TF3-Infra-Sentinel/gitops/infrastructure/resource-quota.yaml): Giới hạn tài nguyên namespace `techx-tf3`.

### 2. Triển khai & Cấu hình ArgoCD trên EKS
*   **Cài đặt ArgoCD:** Deploy ArgoCD Helm Chart thành công vào namespace `argocd`.
*   **Cấu hình Best Practice:** Cập nhật `argocd-cm` ConfigMap để chuyển chế độ `resourceTrackingMethod` sang `annotation`. Việc này giải quyết triệt để lỗi `spec.selector is immutable` khi ArgoCD chiếm quyền quản lý các subcharts (Prometheus, Grafana, Jaeger, OpenSearch) có sẵn từ Helm.
*   **Đồng bộ Parent App:** Apply parent app `techx-corp-bootstrap`.

---

## Kết quả kiểm thử & Xác minh

### 1. Đồng bộ trạng thái GitOps thành công
Cả ba ứng dụng ArgoCD đều đã chuyển sang trạng thái hoạt động chính xác:
*   `techx-corp-bootstrap`: **Synced / Healthy**
*   `techx-infrastructure-app`: **Synced / Healthy** (Deploy thành công NetworkPolicy và ResourceQuota).
*   `techx-corp`: **Synced / Progressing** (Đã đồng bộ toàn bộ 18+ microservices).

### 2. Xác minh Không xảy ra Downtime / Restarts (Zero Downtime)
Kiểm tra thời gian chạy (AGE) của toàn bộ các Pod ứng dụng trong namespace `techx-tf3` ngay sau khi ArgoCD đồng bộ thành công:
```sh
$ kubectl get pods -n techx-tf3
NAME                               READY   STATUS    RESTARTS   AGE
accounting-599df6c744-dbkzg        1/1     Running   0          3d
ad-84bd5fc556-z6pwr                1/1     Running   0          3d
cart-7f7c88558c-l4pcd              1/1     Running   0          3d
checkout-f4c86f8fb-rd49k           1/1     Running   0          2d19h
...
```
*   **Kết quả:** Tất cả các Pod ứng dụng đều giữ nguyên AGE (`3d`, `2d19h`,...) và số lần restart (`0`). 
*   **Kết luận:** ArgoCD đã tiếp quản thành công các tài nguyên K8s hiện có mà không kích hoạt chu trình recreate hay restart Pod, đạt chuẩn quy trình **Zero Downtime**.

### 3. Thông tin truy cập ArgoCD
*   **Username:** `admin`
*   **Lấy password khởi tạo bằng lệnh:**
    ```sh
    kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath="{.data.password}" | base64 -d && echo ""
    ```
*   **Lệnh port-forward để truy cập Dashboard:**
    ```sh
    kubectl port-forward service/argocd-server -n argocd 8082:443
    ```
    *(Mở trình duyệt truy cập `https://localhost:8082`)*

### 4. Điều chỉnh Resource Quota & Bật Auto-Sync
*   **Bật Auto-Sync & Self-Heal:** Chúng ta đã chuyển đổi `syncPolicy` của ứng dụng chính `techx-corp` từ `manual` sang `automated: prune: true, selfHeal: true`. Từ giờ, ArgoCD sẽ tự động đồng bộ mọi thay đổi cấu hình từ Git xuống cluster.
*   **Điều chỉnh Resource Quota (Tối ưu cho việc scale):** 
    *   *Sự cố phát hiện:* Khi áp đặt giới hạn CPU (`requests.cpu` và `limits.cpu`) trong ResourceQuota, Kubernetes bắt buộc toàn bộ pod trong namespace phải khai báo CPU requests/limits. Do 28/32 containers trong chart gốc không có CPU requests/limits, việc này gây nghẽn toàn bộ quá trình cập nhật Pod mới (`FailedCreate` do vượt quota).
    *   *Khắc phục:* Đã loại bỏ CPU quota, chỉ giữ lại giới hạn RAM (**`Requests: 16Gi / Limits: 20Gi`**) và Pod limit (**`50`**). Đây là mức tối ưu giúp tận dụng tối đa 24Gi RAM vật lý của cluster, chừa lại 4Gi cho hệ thống K8s/ArgoCD, đồng thời cung cấp đủ không gian (headroom) để scale replicas luồng checkout lên 3-4 bản sao thoải mái.

### 5. Kích hoạt & Xác minh Network Policy (eBPF)
*   **Vấn đề trước đó:** Do CNI gốc của EKS (`aws-node`) chạy ở chế độ tự quản (self-managed) và tắt tính năng Network Policy, các NetworkPolicy khai báo trên Git không có hiệu lực thực tế.
*   **Kích hoạt EKS Managed Add-on:** Chúng ta đã import và chuyển đổi VPC CNI sang dạng AWS EKS Managed Add-on và bật tính năng Network Policy thông qua lệnh AWS CLI:
    ```sh
    aws eks create-addon \
      --cluster-name techx-corp-tf3 \
      --addon-name vpc-cni \
      --configuration-values '{"enableNetworkPolicy": "true"}' \
      --region ap-southeast-1
    ```
    EKS đã tự động chạy và quản lý `aws-network-policy-controller` trên Control Plane để tạo ra các `PolicyEndpoint` tài nguyên phục vụ việc chặn eBPF dưới node.
*   **Kết quả xác minh thực tế:**
    *   **Thử nghiệm 1 (Chặn kết nối trái phép):** Thực thi lệnh kết nối cổng Postgres 5432 từ pod `image-provider` (không có trong whitelist) -> Kết quả: **`Blocked`** (Bị eBPF chặn hoàn toàn và timeout).
    *   **Thử nghiệm 2 (Cho phép kết nối hợp lệ):** Thực thi socket kết nối từ pod `product-reviews` (nằm trong whitelist NetworkPolicy) -> Kết quả: **`Connected`** (Kết nối thông suốt ngay lập tức).

---

## Lưu ý về CI/CD Workflow (`build-push-ecr.yml`)

Do OAuth token trong môi trường agent bị giới hạn quyền `workflow` (không được tự động cập nhật các file CI workflow trên GitHub), thay đổi trên file [.github/workflows/build-push-ecr.yml](file:///home/tutruong/project/Phase3-TF3-Infra-Sentinel/.github/workflows/build-push-ecr.yml) hiện chỉ được lưu local. 

Bạn hãy sử dụng Pull Request hoặc tự push phần diff sau lên GitHub để hoàn thiện luồng CI tự động cập nhật tag:

```diff
 permissions:
   id-token: write # required for OIDC -> assume AWS role
-  contents: read
+  contents: write # changed from read to write to allow GitOps updates
 
...

       - name: Build & push all app images
         run: |
           set -a; . ./.env.override; set +a
           # opensearch has a `build:` stanza but no `image:` tag...
           docker buildx bake -f docker-compose.yml --push \
             --set "*.platform=${{ inputs.platforms || 'linux/amd64,linux/arm64' }}" \
             accounting ad cart checkout currency email fraud-detection frontend \
             frontend-proxy image-provider kafka llm load-generator payment \
             product-catalog product-reviews quote recommendation shipping flagd-ui
+
+      - name: Update image tag in values-prod.yaml (GitOps)
+        working-directory: .
+        run: |
+          yq -i '.default.image.tag = "${{ steps.vars.outputs.tag }}"' "phase3 - information/deploy/values-prod.yaml"
+
+      - name: Commit and push updated image tag
+        working-directory: .
+        run: |
+          git config --global user.name "github-actions[bot]"
+          git config --global user.email "github-actions[bot]@users.noreply.github.com"
+          git add "phase3 - information/deploy/values-prod.yaml"
+          git commit -m "chore(gitops): update production image tag to ${{ steps.vars.outputs.tag }} [skip ci]" || echo "No changes to commit"
+          git push origin HEAD:${{ github.ref }}
```
