# Ke hoach thuc hien Mandate 10 - Secure Delivery Pipeline

Ngay lap ke hoach: 20/07/2026

## Muc tieu

Hoan thanh phan con thieu cua Mandate 10 ve cong chan CI/CD:

- Xac nhan bang chung that danh sach required status checks tren nhanh `main`.
- Them cong chan scan IaC misconfiguration cho Terraform production.
- Them cong chan SAST cho luong checkout/payment.
- Nho admin repo gan cac check moi vao branch protection.
- Tao PR test co CI do de chung minh merge bi khoa that.

Ket qua cuoi cung can chung minh: neu IaC scan hoac SAST fail thi PR khong merge duoc vao `main`, va tu do khong the di tiep den deploy.

## Tinh trang hien tai

- Branch protection tren `main` da ton tai that theo bang chung PR #273.
- Khong can bat lai branch protection.
- Ket qua `gh api .../branches/main/protection` tra 404 truoc day khong duoc xem la bang chung branch protection khong ton tai, vi token cu khong co quyen admin repo.
- `.github/workflows/secret-scan.yml` da co Gitleaks cho `push` va `pull_request`.
- `.github/workflows/build-push-ecr.yml` da co Trivy image scan, nhung can admin xac nhan check nao dang la required check.
- `.github/workflows/terraform-plan.yml` chua co IaC misconfig scan va hien chi chay plan tren `push main`/manual.
- Chua thay SAST gate cho checkout/payment trong CI.

## Cach lam tong the

Khong sua branch protection bang suy doan. Viec dau tien la lay bang chung tu nguoi co quyen admin. Sau do moi them cac workflow/check con thieu, roi nho admin gan dung ten check moi vao required status checks.

Phan code thay doi se tap trung vao GitHub Actions:

- Them IaC scan vao `.github/workflows/terraform-plan.yml`.
- Them SAST workflow rieng hoac job rieng cho checkout/payment.
- Giu cac workflow co ten check on dinh de admin co the chon lam required check.

## Chi tiet ky thuat du kien

### IaC scan

- File can sua: `.github/workflows/terraform-plan.yml`
- Cach tach job:
  - `iac-scan` chay tren `pull_request`
  - `plan` giu nguyen cho `push` vao `main`
- Thu muc scan:
  - `infra/live/production`
  - `infra/modules`
- Cach run:
  - checkout source
  - setup Terraform nhu workflow hien tai neu can parse
  - cai `tfsec` hoac `checkov`
  - chay scan tren `infra/live/production`
- Dieu kien fail:
  - HIGH/CRITICAL finding -> job fail
- Ten check goi y:
  - `IaC scan (production)`

### SAST

- File can them: `.github/workflows/sast-money-path.yml`
- Job goi y:
  - `sast-checkout` cho Go service
  - `sast-payment` cho Node service
  - `sast-gate` neu muon gom ket qua thanh 1 check chat
- Pham vi:
  - `phase3 - information/techx-corp-platform/src/checkout`
  - `phase3 - information/techx-corp-platform/src/payment`
- Cach run:
  - checkout source
  - cai `gosec` cho checkout
  - cai `semgrep` cho payment, hoac dung Semgrep de scan ca hai luong
  - fail neu co HIGH finding
- Ten check goi y:
  - `SAST money path`

## Cac buoc thuc hien

### Buoc 1 - Xac nhan required checks hien tai

Nguoi thuc hien: nguoi co quyen admin repo.

Viec can lam:

- Vao GitHub repo -> Settings -> Branches -> branch protection cua `main`.
- Chup anh hoac export cau hinh required status checks hien tai.
- Xac nhan trong danh sach dang co nhung check nao:
  - build/test
  - Trivy
  - secret scan/Gitleaks
  - IaC scan
  - SAST

Ket qua can co:

- Anh/export danh sach required status checks hien tai.
- Ghi chu ro check nao da co, check nao con thieu.

Ly do:

Required checks nam trong cau hinh GitHub, khong nam trong file workflow. Neu khong co quyen admin thi khong the ket luan chinh xac. Mandate 10 can bang chung that, khong chap nhan suy doan.

### Buoc 2 - Them IaC misconfiguration scan

Nguoi thuc hien: team dev/infra.

Viec can lam:

- Sua `.github/workflows/terraform-plan.yml`.
- Them trigger `pull_request` cho cac duong dan:
  - `infra/live/production/**`
  - `infra/modules/**`
  - `.github/workflows/terraform-plan.yml`
- Them job hoac step scan rieng cho Terraform production, vi du ten check: `IaC scan (production)`.
- Dung Checkov hoac tfsec de scan `infra/live/production`.
- Cau hinh fail khi co HIGH/CRITICAL finding.
- Khong yeu cau AWS credentials cho scan PR, de PR tu branch van chay duoc.
- Neu dung tfsec:
  - scan truc tiep thu muc production
  - giu output ngan gon de trong CI log de doc
- Neu dung Checkov:
  - giu check theo framework terraform
  - chi scan thu muc production, khong scan toan repo neu khong can

Ket qua can co:

- PR diff co IaC scan trong workflow.
- CI log cho thay scan chay tren PR.
- Khi chen misconfig Terraform HIGH, check `IaC scan (production)` phai do.

Ly do:

Terraform production co the thay doi network, IAM, encryption, EKS, registry, hoac cac cau hinh bao mat. Neu chi `terraform plan` ma khong scan misconfig thi van co the dua loi bao mat vao production. IaC scan phai la cong chan truoc merge.

### Buoc 3 - Them SAST cho checkout/payment

Nguoi thuc hien: team dev/appsec.

Viec can lam:

- Tao workflow moi, vi du `.github/workflows/sast-money-path.yml`, hoac them job SAST vao workflow phu hop.
- Dat ten check on dinh, vi du `SAST money path`.
- Scan toi thieu cac path:
  - `phase3 - information/techx-corp-platform/src/checkout/**`
  - `phase3 - information/techx-corp-platform/src/payment/**`
- Dung gosec cho checkout Go service, hoac Semgrep de phu ca checkout va payment.
- Cau hinh fail khi co HIGH finding.
- Trigger tren `pull_request` va `push` vao `main`.
- Cach lam ro:
  - checkout: chay `gosec ./...` trong thu muc `src/checkout`
  - payment: chay `semgrep` tren `src/payment`
  - neu dung 1 workflow duy nhat, them `sast-gate` de gom ket qua 2 job con
- Needing pin:
  - pin version action/cli de check ten khong doi giua cac lan chay

Ket qua can co:

- PR diff co SAST gate.
- CI log cho thay checkout/payment duoc scan.
- Khi chen loi SAST HIGH, check `SAST money path` phai do.

Ly do:

Checkout va payment la luong ra tien. Loi bao mat o day co tac dong truc tiep den thanh toan, don hang, va du lieu khach hang. SAST giup chan cac loi code ro rang truoc khi code duoc build thanh image.

### Buoc 4 - Cap nhat branch protection

Nguoi thuc hien: nguoi co quyen admin repo.

Viec can lam:

- Sau khi IaC scan va SAST da chay thanh cong it nhat mot lan tren PR, vao Settings -> Branches -> `main`.
- Them cac check moi vao required status checks:
  - `IaC scan (production)`
  - `SAST money path`
- Neu bang chung buoc 1 cho thay Trivy hoac secret scan chua required, them luon:
  - Trivy image scan check phu hop
  - Gitleaks/secret scan check phu hop
- Chup anh/export cau hinh sau khi update.

Ket qua can co:

- Anh/export required status checks sau update.
- Danh sach required checks day du gom build/test, Trivy, secret scan, IaC scan, SAST.

Ly do:

Them workflow thoi chua du. Neu admin khong gan vao required checks, PR van co the merge khi check do, va Mandate 10 chua dat.

### Buoc 5 - Tao PR test CI do

Nguoi thuc hien: team dev/infra.

Viec can lam:

- Tao branch test rieng.
- Chen co chu dich mot misconfig Terraform HIGH trong `infra/live/production`, vi du:
  - mo public access sai muc do
  - bo encryption
  - rule security group qua rong
- Chen co chu dich mot loi SAST HIGH trong checkout hoac payment, vi du:
  - gosec finding ro rang trong checkout
  - rule Semgrep danh dau unsafe pattern trong payment
- Mo PR vao `main`.
- Doi CI chay xong.
- Chup anh PR cho thay:
  - required check fail
  - nut merge bi khoa
  - GitHub hien thi khong duoc merge do required check chua pass
- Khong merge PR test nay.
- Dong PR hoac revert commit test.

Ket qua can co:

- Link PR test.
- Anh chup check do va merge bi chan.
- CI log cua IaC scan/SAST cho thay loi co chu dich bi phat hien.

Ly do:

Day la bang chung manh nhat cho Mandate 10: khong chi co cau hinh tren giay, ma khi CI do that thi GitHub chan merge that.

## Output can nop

- Anh/export required status checks tren `main` sau khi cap nhat.
- PR/commit them IaC scan va SAST scan.
- CI log cho IaC scan va SAST.
- PR test co CI co tinh do.
- Anh chup PR test cho thay merge bi khoa.

## Definition of Done

- Co bang chung admin-access xac nhan required checks, khong suy doan tu API token cu.
- Required checks tren `main` gom build/test, Trivy, secret scan, IaC scan, SAST.
- IaC scan fail khi co Terraform HIGH/CRITICAL misconfiguration.
- SAST fail khi co HIGH finding trong checkout/payment.
- PR test co required check fail va merge bi khoa.

## Luu y khi lam

- Khong commit secret that, AWS credential, token flagd, hoac key that de tao test fail.
- Neu dung GitHub Action ben thu ba, can pin version theo yeu cau Mandate 10; tot nhat pin commit SHA khi chot ban nop.
- Neu Trivy hien chi chay sau merge tren `push main`, can them PR-mode scan hoac xac nhan check nao moi that su chan merge.
- Cac loi HIGH chen de test phai nam trong PR test rieng va khong duoc merge vao `main`.
