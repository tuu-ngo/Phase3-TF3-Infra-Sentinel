# Nghiên cứu Kiến thức cốt lõi: Ngăn chặn rủi ro sập hệ thống (Tiền đề PM-118)

> **Mục đích:** Tài liệu này được biên soạn ngắn gọn để cả team có chung một hệ quy chiếu kiến thức, nhằm tránh lặp lại sai lầm ở sự cố PM-115/PM-116. Mọi thông tin đều được tham chiếu từ tài liệu chính thức.

---

## 1. Sự thật chết người về K8s NetworkPolicy: `Default-Deny-By-Selector`

Rất nhiều người nhầm tưởng NetworkPolicy là việc "Thêm rule cho phép". Sự thật là: Mặc định cụm K8s cho phép mọi kết nối (Allow All). Tuy nhiên, **ngay khi bạn áp dụng 1 NetworkPolicy có chứa `podSelector` nhắm vào 1 pod, pod đó lập tức rơi vào trạng thái CÔ LẬP (Deny All)** đối với chiều khai báo (Ingress/Egress). 

- **Cơ chế:** K8s sẽ tự động từ chối mọi traffic đi vào pod đó, NGOẠI TRỪ những luồng được định nghĩa rõ ràng trong phần `from:` (Allowlist).
- **Rút kinh nghiệm sự cố:** Khi chúng ta áp dụng NetworkPolicy cho Prometheus/Jaeger, chúng ta đã vô tình đẩy các pod này vào trạng thái "Deny All" với mọi dịch vụ khác. Kết quả là `aiops-engine` (dịch vụ lệ thuộc ngầm) bị chặn đứng kết nối, gây ra CrashLoopBackOff.
- 🔗 **Nguồn gốc:** [Kubernetes Official - Network Policies](https://kubernetes.io/docs/concepts/services-networking/network-policies/#isolated-and-non-isolated-pods)

---

## 2. AWS VPC CNI Network Policy: Sức mạnh và Độ trễ

Hệ thống EKS của chúng ta dùng AWS VPC CNI. Khác với các CNI cũ dùng `iptables`, VPC CNI thực thi luật mạng ở một đẳng cấp sâu hơn:
- **Cơ chế eBPF:** Khi NetworkPolicy được áp dụng, K8s API sẽ thêm finalizer (vd: `networking.k8s.aws/resources`). Dịch vụ `aws-network-policy-agent` chạy ngầm trên Node sẽ biên dịch luật này thành các chương trình **eBPF (Extended Berkeley Packet Filter)** nhúng thẳng vào Kernel của Linux.
- **Rủi ro (Blast Radius):** Mọi traffic vi phạm sẽ bị drop thẳng ở tầng Kernel một cách lạnh lùng. Không hề có logs hiện ra trên container của bạn. Khi có lỗi, việc debug vô cùng khó khăn nếu bạn không có công cụ đọc eBPF. 
- 🔗 **Nguồn gốc:** [AWS Docs - Restrict Pod network traffic with Kubernetes network policies](https://docs.aws.amazon.com/eks/latest/userguide/calico.html)

---

## 3. Vì sao ArgoCD Self-Heal "bất lực"?

Trong sự cố vừa rồi, NetworkPolicy bị apply tay thẳng lên cluster bằng lệnh `kubectl apply`. Câu hỏi đặt ra là: *Tại sao tính năng Self-Heal (tự động chữa lành) của ArgoCD không xóa nó đi?*

- **Bản chất của GitOps:** ArgoCD chỉ so sánh (Drift Detection) và chữa lành (Self-Heal) **những tài nguyên (Resources) đã được khai báo trong Git Repository**. 
- **Lỗ hổng "Out-of-band":** Các resource được gõ tay thẳng vào Cluster hoàn toàn vô hình (Unmanaged) đối với ArgoCD. ArgoCD không biết chúng là ai, nên cũng không có thẩm quyền để can thiệp hay revert (xóa) chúng. Do đó, một người gõ lệnh sai bằng tay có thể phá nát cụm mà hệ thống tự động không thể cứu được.
- 🔗 **Nguồn gốc:** [ArgoCD - Automated Sync Policy](https://argo-cd.readthedocs.io/en/stable/user-guide/auto_sync/)

---

## 4. Giải pháp RBAC: Cấp quyền Khẩn cấp (Break-Glass)

Sai lầm lớn nhất là kỹ sư có sẵn quyền `cluster-admin` để gõ tay lệnh `kubectl apply` hàng ngày. Theo AWS Well-Architected, chúng ta cần chia rẽ quyền này theo mô hình **Break-Glass**.

- **Không dùng chung IdP chính:** Quyền khẩn cấp không được phụ thuộc vào hệ thống đăng nhập chính (như Okta/Google Workspace) để đề phòng chính hệ thống SSO này bị sập.
- **EKS Access Entries:** Nên tạo một IAM Role riêng biệt (`EmergencyAdminRole`) map thẳng vào `system:masters` thông qua EKS Access Entries.
- **Bảo mật nhiều lớp:**
  1. Chỉ được phép kích hoạt (AssumeRole) khi có Hardware MFA.
  2. Thời hạn session cực ngắn (vd: 15-30 phút).
  3. Mọi hành động gõ lệnh bằng tài khoản này phải được bắn log (CloudTrail) qua Slack/SNS ngay lập tức để cả công ty đều biết có người đang dùng quyền khẩn cấp.
- 🔗 **Nguồn gốc:** [AWS Well-Architected - SEC03-BP03 Establish emergency access process](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/emergency-access-process.html)
