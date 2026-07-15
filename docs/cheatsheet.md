# ShopMart DevOps Interview Cheatsheet (Quick Prep)

Cheatsheet ngắn gọn, trực diện, trả lời đúng trọng tâm theo văn phong phỏng vấn thực tế của dân devops (ngắn, đủ ý, không lý thuyết suông).

---

## 1. Docker & Docker Compose

### Q&A Phỏng Vấn Cốt Lõi

#### Docker image là gì?
*   **Trả lời:** Là một template đóng gói sẵn code, thư viện và môi trường chạy. Nó ở dạng tĩnh (read-only) và dùng làm "bản thiết kế" để chạy container.

#### Dockerfile là gì và hoạt động thế nào?
*   **Trả lời:** Là file chứa các bước lệnh để build ra image. Mỗi dòng lệnh tạo ra một layer mới.

#### Docker cache là gì?
*   **Trả lời:** Là cơ chế lưu trữ lại kết quả của các layer đã build trước đó. Khi build lại image, Docker sẽ tái sử dụng các layer không thay đổi thay vì chạy lại lệnh đó, giúp tăng tốc độ build.

#### Khi nào Docker cache bị invalid?
*   **Trả lời:** Khi một dòng lệnh trong Dockerfile thay đổi, hoặc các file nguồn truyền vào lệnh `COPY`/`ADD` thay đổi. Lúc đó, layer tương ứng và toàn bộ các layer phía sau nó sẽ bị mất cache (invalidated) và phải chạy lại từ đầu.

#### Làm sao để build Docker image nhanh hơn?
*   **Trả lời:** 
    1. Sắp xếp thứ tự lệnh: Đưa các lệnh cài đặt dependencies ít thay đổi lên trên (ví dụ: `COPY package.json` rồi chạy cài thư viện), đưa các lệnh copy source code hay thay đổi xuống dưới cùng.
    2. Dùng `.dockerignore` để loại bỏ các file thừa (như `node_modules`, log, git) giúp lệnh `COPY . .` chạy nhanh và cache ổn định hơn.

#### Multi-stage build là gì?
*   **Trả lời:** Là kỹ thuật chia quá trình build Docker image thành nhiều giai đoạn (stages) trong cùng một Dockerfile bằng cách dùng nhiều câu lệnh `FROM`. Mỗi stage có thể dùng một base image khác nhau.

#### Vì sao production nên dùng multi-stage build?
*   **Trả lời:** Giúp tạo ra image chạy cuối cùng (final image) siêu nhẹ vì chỉ cần copy file chạy (binary hoặc build artifact) từ stage compile sang stage production tinh giản, loại bỏ hoàn toàn các SDK nặng và mã nguồn thừa. Vừa giảm dung lượng đĩa, vừa tăng tính bảo mật (giảm bề mặt tấn công).

#### Container là gì và khác gì so với Image?
*   **Trả lời:** 
    *   **Image:** Là bản thiết kế tĩnh (file read-only), không tiêu thụ CPU/RAM khi lưu trên ổ đĩa.
    *   **Container:** Là một thực thể chạy thực tế (runtime instance) được tạo từ Image. Nó được cấp phát CPU/RAM và có một lớp ghi (write layer) riêng biệt để chạy ứng dụng.

#### Docker Volume là gì và dùng để làm gì?
*   **Trả lời:** Là cơ chế gắn một thư mục ngoài máy host vào trong container để lưu dữ liệu bền vững (persist data). Vì dữ liệu ghi trực tiếp vào container sẽ mất sạch khi container bị xóa, Volume giúp dữ liệu (như data của database) tồn tại độc lập với vòng đời của container.

#### Biến môi trường (Environment Variable) là gì?
*   **Trả lời:** Là các cặp key-value được lưu trữ ngoài hệ thống, dùng để cấu hình động ứng dụng mà không cần thay đổi source code (ví dụ: DB_URL, API_KEY).

#### Cách truyền biến môi trường vào container?
*   **Trả lời:** Khai báo trực tiếp ở mục `environment` hoặc đọc từ file `.env` qua mục `env_file` trong file Compose; hoặc truyền tham số `-e` khi chạy lệnh `docker run`.

#### Docker Compose là gì và dùng để làm gì?
*   **Trả lời:** Là công cụ giúp định nghĩa và chạy hệ thống gồm nhiều container. Thay vì gõ tay từng lệnh `docker run` phức tạp cho từng dịch vụ, mình khai báo tất cả dịch vụ (database, backend, frontend) trong 1 file `docker-compose.yml` rồi chạy bằng `docker compose up`.

#### Các container giao tiếp với nhau thế nào trong Docker Compose?
*   **Trả lời:** Qua Docker Network. Các container trong cùng một file Compose sẽ tự động kết nối vào chung một mạng ảo (Bridge network) và có thể gọi nhau bằng **tên dịch vụ (service name)** được khai báo trong file Compose nhờ cơ chế phân giải tên miền (DNS) nội bộ của Docker.

#### Non-root user là gì và tại sao cần thiết lập trong Dockerfile?
*   **Trả lời:** Là việc cấu hình cho ứng dụng trong container chạy dưới quyền của một user thường thay vì user root mặc định. Điều này ngăn chặn hacker nếu xâm nhập được vào container cũng không thể leo thang đặc quyền để kiểm soát máy host.

#### Làm sao debug một container bị crash?
*   **Trả lời:** 
    1. Check logs nhanh bằng `docker logs <container-id>`.
    2. Dùng `docker ps -a` kiểm tra Exit Code (ví dụ code 137 thường do OOM - hết RAM).
    3. Nếu cần chui vào trong khám phá: Thay đổi entrypoint thành `sh` hoặc `bash` rồi chạy `docker run -it`.

---

### Bài tập docker-compose.yml (FastAPI + PostgreSQL + Redis)

```yaml
version: '3.8'

services:
  db:
    image: postgres:15-alpine
    container_name: app-db
    restart: always
    environment:
      POSTGRES_USER: admin
      POSTGRES_PASSWORD: secret_password
      POSTGRES_DB: app_db
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U admin -d app_db"]
      interval: 5s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    container_name: app-redis
    restart: always
    ports:
      - "6379:6379"
    volumes:
      - redisdata:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 5s
      retries: 5

  web:
    build:
      context: ./app
      dockerfile: Dockerfile
    container_name: app-fastapi
    restart: always
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql://admin:secret_password@db:5432/app_db
      - REDIS_URL=redis://redis:6379/0
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_healthy

volumes:
  pgdata:
  redisdata:
```

#### Giải thích siêu ngắn gọn:
*   `db` / `redis`: Chạy Postgres và Redis bản Alpine siêu nhẹ. Có mapping port ra máy host và setup volume (`pgdata`, `redisdata`) để lưu data không bị mất.
*   `healthcheck`: Check xem db/redis thực sự sẵn sàng chưa (`pg_isready` và `redis-cli ping`).
*   `web`: Tự build FastAPI từ Dockerfile trong thư mục `./app`.
*   `depends_on` kèm `condition`: Đảm bảo FastAPI chỉ start khi db và redis đã vượt qua vòng healthcheck (đã `healthy`).
*   `DATABASE_URL` / `REDIS_URL`: Gọi qua host là `db` và `redis` nhờ DNS nội bộ của Docker Compose.

---

## 2. Kubernetes cơ bản

### Q&A Phỏng Vấn Cốt Lõi

#### Pod là gì?
*   **Trả lời:** Đơn vị triển khai nhỏ nhất của K8s. Chứa một hoặc một nhóm container dùng chung IP, port (`localhost`) và chung ổ đĩa.

#### Replica là gì và ReplicaSet là gì?
*   **Trả lời:** 
    *   **Replica:** Số lượng bản sao Pod chạy song song để gánh tải và dự phòng.
    *   **ReplicaSet:** Controller chịu trách nhiệm duy trì đúng số lượng bản sao Pod chạy ổn định trên cluster tại mọi thời điểm.

#### Deployment là gì?
*   **Trả lời:** Thằng quản lý số lượng và vòng đời của Pod. Nó quản lý ReplicaSet bên dưới để thực hiện scale Pod lên/xuống, tự động tạo lại Pod mới nếu bị lỗi, và update phiên bản mới không gây downtime (rolling update).

#### Service là gì?
*   **Trả lời:** Là đầu mối nhận traffic. Pod sinh ra và chết đi sẽ đổi IP liên tục, Service cung cấp 1 IP tĩnh và tên DNS cố định để chuyển traffic vào đúng các Pod tương ứng (dùng selector label).

#### ClusterIP là gì?
*   **Trả lời:** Loại Service mặc định của K8s. Nó cấp một IP nội bộ chỉ có thể truy cập được từ bên trong cluster, dùng để các microservice gọi nội bộ nhau.

#### NodePort là gì?
*   **Trả lời:** Loại Service mở một cổng tĩnh (từ 30000-32767) trên tất cả các Worker Node. Traffic từ bên ngoài gọi vào bất kỳ IP của Node nào trên cổng này sẽ được định tuyến tới Pod tương ứng.

#### So sánh ClusterIP và NodePort?
*   **Trả lời:** 
    *   **ClusterIP:** Chỉ truy cập nội bộ trong cluster. Bảo mật hơn, dùng cho backend/database.
    *   **NodePort:** Mở cổng ra ngoài internet qua IP của Node. Dễ cấu hình nhưng khó quản lý quy mô lớn và kém bảo mật hơn, thường dùng làm cầu nối trước LoadBalancer.

#### HPA (Horizontal Pod Autoscaler) là gì?
*   **Trả lời:** Bộ tự động scale Pod theo chiều ngang. Nó sẽ tự động tăng hoặc giảm số lượng Pod chạy trong Deployment dựa trên lượng tài nguyên tiêu thụ thực tế.

#### HPA hoạt động như thế nào và dựa trên metric nào?
*   **Trả lời:** HPA liên tục thu thập metrics (thông qua Metrics Server) và so sánh với ngưỡng cấu hình. Metric phổ biến nhất là CPU và Memory (RAM). Dự án ShopMart đang dùng CPU với ngưỡng trung bình 70% để scale số Pod từ 2 lên tối đa 5 Pod.

#### ConfigMap là gì?
*   **Trả lời:** Đối tượng lưu trữ các cấu hình dạng key-value thông thường (như file config, biến môi trường) tách biệt khỏi mã nguồn của container.

#### Secret là gì?
*   **Trả lời:** Đối tượng dùng để lưu trữ các thông tin nhạy cảm (như mật khẩu, API key, chứng chỉ SSL) được mã hóa dưới dạng Base64 để tăng tính bảo mật.

#### So sánh ConfigMap và Secret?
*   **Trả lời:** 
    *   **ConfigMap:** Lưu thông tin cấu hình thường dạng plaintext. Dễ đọc, dễ sửa.
    *   **Secret:** Lưu thông tin bảo mật, mã hóa Base64 và có phân quyền truy cập chặt chẽ hơn để tránh lộ thông tin.

#### Probe trong K8s là gì?
*   **Trả lời:** Cơ chế kiểm tra sức khỏe của container do kubelet thực hiện định kỳ (bằng lệnh shell, HTTP request hoặc TCP socket check).

#### Liveness Probe và Readiness Probe khác nhau như thế nào?
*   **Trả lời:** 
    *   **Liveness Probe:** Check xem app có bị đơ/treo không. Nếu check thất bại, K8s sẽ restart Pod.
    *   **Readiness Probe:** Check xem app đã khởi động xong và sẵn sàng nhận traffic chưa. Nếu check thất bại, K8s sẽ tạm thời tách IP Pod ra khỏi Service để không nhận traffic nữa (không restart Pod).

#### DaemonSet là gì?
*   **Trả lời:** Controller đảm bảo chạy chính xác 1 bản sao Pod trên mỗi Worker Node. Khi thêm Node mới, nó tự chạy Pod trên Node đó. Phù hợp cho log agent (Fluentd) hoặc monitoring agent.

#### StatefulSet là gì?
*   **Trả lời:** Controller dùng để quản lý các ứng dụng cần giữ trạng thái (Stateful) như database. Nó đảm bảo định danh duy nhất, cố định cho từng Pod (db-0, db-1) và gắn cố định ổ đĩa (Persistent Volume) dù Pod có bị restart.

#### So sánh DaemonSet và StatefulSet?
*   **Trả lời:** 
    *   **DaemonSet:** Chạy đều khắp các node (1 node = 1 pod), không quan tâm đến thứ tự hay lưu trữ persistent chung. Dùng cho log/monitor.
    *   **StatefulSet:** Chạy theo thứ tự tăng dần (pod sau chỉ start khi pod trước healthy), gắn chặt với một ổ đĩa riêng. Dùng cho Database/Stateful app.

#### GitOps là gì?
*   **Trả lời:** Là phương pháp quản lý và triển khai hạ tầng/ứng dụng bằng cách lấy Git làm "nguồn chuẩn duy nhất" (Single Source of Truth). Mọi thay đổi hệ thống đều qua Git commit/PR.

#### ArgoCD là gì và nó hiện thực GitOps như thế nào?
*   **Trả lời:** Là công cụ CD (Continuous Delivery) chạy trong K8s. Nó liên tục so sánh trạng thái khai báo trên Git với trạng thái chạy thực tế trên cluster. Khi phát hiện commit mới trên Git, nó sẽ tự động đồng bộ (apply) xuống cluster. Nếu có ai sửa tay trên cluster, nó tự động ghi đè lại cho đúng như Git (Self-healing).

---

### Demo Lệnh kubectl & Helm
*   `kubectl get pods`: Xem các Pod có chạy ngon không, status thế nào.
*   `kubectl describe pod <name>`: Xem chi tiết cấu hình Pod và đặc biệt là mục **Events** ở cuối để xem vì sao Pod bị lỗi (lỗi pull image, lỗi thiếu tài nguyên...).
*   `kubectl logs <name>`: Xem log của container để debug lỗi code bên trong.
*   `kubectl apply -f shopmart-observability.yaml`: Apply file config YAML lên cluster.
*   `helm install my-app ./chart-path`: Deploy nhanh một Helm chart.

---

## 3. AWS (SAA-level cơ bản)

### Q&A Phỏng Vấn Cốt Lõi

#### Amazon S3 là gì?
*   **Trả lời:** Dịch vụ lưu trữ đối tượng (object storage) đám mây, lưu trữ file giá rẻ với độ bền và độ sẵn sàng cực cao (99.999999999%).

#### AWS Lambda là gì?
*   **Trả lời:** Dịch vụ chạy code serverless (FaaS). Chỉ cần tải code lên, AWS tự lo hạ tầng, tự scale và chỉ tính tiền trên số mili-giây code thực thi thực tế (không chạy không tốn tiền).

#### Amazon DynamoDB là gì?
*   **Trả lời:** Dịch vụ cơ sở dữ liệu NoSQL dạng Key-Value được quản lý hoàn toàn (fully managed), cung cấp độ trễ siêu thấp (<10ms) ở mọi quy mô.

#### Amazon SNS là gì?
*   **Trả lời:** Dịch vụ thông báo Pub/Sub (Publish/Subscribe). Cho phép gửi tin nhắn, email hoặc kích hoạt các service khác khi có sự kiện xảy ra (ví dụ gửi mail cảnh báo cho đội vận hành).

#### Amazon CloudWatch là gì?
*   **Trả lời:** Dịch vụ giám sát và quản lý log/metrics cho tài nguyên AWS. Dùng để gom log, theo dõi hiệu năng và thiết lập cảnh báo (Alarm) khi hệ thống gặp lỗi.

#### Amazon EC2 (Elastic Compute Cloud) là gì?
*   **Trả lời:** Dịch vụ cung cấp các máy chủ ảo (Virtual Server) trên đám mây. Người dùng có toàn quyền cấu hình hệ điều hành, cài phần mềm và phải tự quản lý, bảo trì máy chủ này.

#### Định dạng file CSV và Parquet là gì?
*   **Trả lời:** 
    *   **CSV (Comma-Separated Values):** Định dạng lưu dữ liệu dạng bảng dưới dạng text thuần túy, phân tách bằng dấu phẩy. Dễ đọc nhưng dung lượng lớn, đọc ghi chậm.
    *   **Parquet:** Định dạng lưu dữ liệu dạng cột (columnar) nhị phân, nén tốt. Phù hợp cho phân tích dữ liệu lớn vì tốc độ truy vấn cực nhanh và tiết kiệm dung lượng.

#### AWS Glue Data Catalog là gì?
*   **Trả lời:** Kho lưu trữ siêu dữ liệu (metadata) tập trung để quản lý schema (cấu trúc bảng) của các file dữ liệu lưu trên S3, giúp các công cụ truy vấn hiểu được cấu trúc của file.

#### Amazon Athena là gì?
*   **Trả lời:** Dịch vụ truy vấn SQL serverless. Cho phép dùng câu lệnh SQL tiêu chuẩn để truy vấn trực tiếp dữ liệu dạng file (CSV, Parquet, JSON) trên S3 mà không cần import vào cơ sở dữ liệu.

#### Amazon VPC (Virtual Private Cloud) là gì?
*   **Trả lời:** Mạng ảo riêng độc lập được cấp phát cho tài khoản AWS của bạn, cho phép bạn thiết lập dải IP, subnet, bảng định tuyến và firewall để bảo mật tài nguyên.

#### VPC Endpoints là gì và tại sao nên dùng cho S3/DynamoDB?
*   **Trả lời:** Là cổng kết nối riêng tư giữa VPC và các dịch vụ AWS khác. Thay vì đi qua đường internet công cộng (tốn tiền NAT Gateway và kém bảo mật), VPC Gateway Endpoint mở đường đi nội bộ trực tiếp từ Lambda/EC2 đến S3/DynamoDB vừa bảo mật tối đa vừa miễn phí tiền truyền tải dữ liệu.

#### Athena Partitioning là gì và giúp ích gì?
*   **Trả lời:** Kỹ thuật chia dữ liệu trên S3 thành các thư mục con theo cấu trúc phân cấp (ví dụ: `year=2026/month=07/`). Khi Athena truy vấn lọc theo ngày, nó chỉ quét các file trong đúng thư mục đó thay vì quét toàn bộ bucket S3, giúp tăng tốc độ chạy câu lệnh và tiết kiệm tối đa chi phí quét đĩa (Athena tính tiền trên dung lượng dữ liệu quét).

---

### Mô tả kiến trúc ShopMart (Luồng dữ liệu)

> **Mô tả nhanh:** "Cửa hàng upload file CSV lên **S3 Raw**. S3 trigger **Lambda** chạy. Lambda đầu tiên check tên file trong **DynamoDB** xem có bị trùng không (idempotency để tránh tính đúp doanh thu). Nếu file mới, Lambda xử lý làm sạch: file chuẩn thì đổi sang định dạng **Parquet** đẩy vào **S3 Processed**, file lỗi đẩy vào **S3 Quarantine** và gửi mail cảnh báo qua **SNS**. Cuối cùng, data sạch ở S3 Processed được map schema qua **Glue Catalog** để dùng **Athena** gõ SQL query phân tích. Toàn bộ log của Lambda được đẩy về **CloudWatch**."

---

## 4. Terraform

### Q&A Phỏng Vấn Cốt Lõi

#### Terraform là gì?
*   **Trả lời:** Là công cụ định nghĩa hạ tầng bằng code (Infrastructure as Code - IaC). Cho phép khai báo tài nguyên cloud muốn tạo bằng code (ngôn ngữ HCL) rồi chạy lệnh để Terraform tự động tạo đúng như thế.

#### State file là gì?
*   **Trả lời:** Là file JSON (`terraform.tfstate`) lưu trữ trạng thái thực tế của hạ tầng Cloud mà Terraform đang quản lý. Nó dùng để đối chiếu với code của bạn. Nếu mất file này, Terraform sẽ không biết tài nguyên nào đã được tạo và có thể sẽ tạo đè lên hoặc tạo mới hoàn toàn.

#### Các lệnh terraform init, plan, apply là gì và hoạt động thế nào?
*   **Trả lời:** 
    *   `init`: Khởi tạo thư mục làm việc, tải các plugin provider (như AWS, Azure) cần thiết để giao tiếp với Cloud API.
    *   `plan`: So sánh code với State file để hiển thị trước những thay đổi sẽ thực hiện (sẽ tạo mới, sửa hay xóa gì).
    *   `apply`: Thực thi các thay đổi thật lên Cloud và cập nhật lại State file.

#### Remote State & State Locking là gì và tại sao cần thiết khi làm việc nhóm?
*   **Trả lời:** 
    *   **Remote State:** Lưu file state tập trung (ví dụ trên S3 bucket) thay vì để ở máy cá nhân của từng dev.
    *   **State Locking:** Dùng một cơ chế khóa (ví dụ qua DynamoDB) để khi một người đang chạy lệnh `apply`, state file sẽ bị khóa lại. Ngăn người khác chạy đè đụng độ gây hỏng hoặc sai lệch file state.

#### Resource dependency là gì? (Implicit vs Explicit dependency là gì?)
*   **Trả lời:** Thứ tự ưu tiên tạo tài nguyên.
    *   **Implicit (Ngầm định):** Tự hiểu do code gọi giá trị của tài nguyên này trong cấu hình tài nguyên khác (ví dụ: tạo Subnet trước rồi lấy Subnet ID để tạo EC2).
    *   **Explicit (Tường minh):** Khai báo rõ ràng qua thuộc tính `depends_on` khi Terraform không tự phát hiện được mối liên hệ.

#### Input Variable là gì?
*   **Trả lời:** Biến đầu vào (giống như tham số hàm) dùng để cấu hình động cho mã nguồn Terraform mà không cần sửa cứng code (ví dụ: region, environment, subnet IP).

#### Output Value là gì?
*   **Trả lời:** Biến đầu ra dùng để xuất và hiển thị thông tin quan trọng ra màn hình sau khi Terraform thực thi xong (ví dụ: IP của EC2 vừa tạo, ARN của S3).

---

## 5. Linux & Bash

### Q&A Phỏng Vấn Cốt Lõi

#### Các lệnh Linux cốt lõi hay dùng là gì?
*   **Trả lời:** 
    *   `cat filename` / `tail -f app.log`: Xem nội dung file và xem log chạy realtime.
    *   `grep "ERROR" app.log`: Tìm kiếm dòng chứa chữ ERROR trong file log.
    *   `curl -I https://google.com`: Gửi request test nhanh xem HTTP status trả về là gì (200, 404, 500).
    *   `ss -tulpn`: Check xem cổng mạng nào đang mở, tiến trình nào đang chiếm port.
    *   `df -h` / `free -m`: Check dung lượng ổ đĩa trống và dung lượng RAM còn lại của server.
    *   `chmod 755 script.sh`: Phân quyền cho file script.

#### Ý nghĩa của quyền file (chmod 755) là gì?
*   **Trả lời:** Quyền `755` cấp quyền cho file script/thư mục: Chủ sở hữu (Owner) có toàn quyền đọc, ghi, chạy (Read, Write, Execute = 7). Nhóm (Group) và những người khác (Others) chỉ có quyền đọc và chạy (Read, Execute = 5).

#### `set -e` trong Bash script là gì và tại sao nên dùng?
*   **Trả lời:** Là tuỳ chọn cấu hình ở đầu script. Nó ra lệnh cho script dừng chạy ngay lập tức nếu có bất kỳ dòng lệnh nào ở giữa gặp lỗi (exit code khác 0), tránh việc chạy cố dẫn đến lỗi dây chuyền khó debug.

#### Standard Output (stdout) và Standard Error (stderr) là gì?
*   **Trả lời:** Là hai luồng dữ liệu đầu ra mặc định của một tiến trình trong Linux.
    *   **Stdout (Descriptor 1):** Luồng chứa kết quả đầu ra thành công của câu lệnh.
    *   **Stderr (Descriptor 2):** Luồng chứa thông tin lỗi, cảnh báo phát sinh khi câu lệnh chạy thất bại.

#### Ký tự `2>&1` hoạt động thế nào và dùng để làm gì?
*   **Trả lời:** Là cú pháp điều hướng luồng dữ liệu (Redirect). Nó chuyển toàn bộ dữ liệu từ luồng lỗi (stderr - 2) vào chung luồng kết quả (stdout - 1). Thường dùng khi chạy tiến trình ngầm để ghi cả log chạy và log lỗi vào chung một file duy nhất (ví dụ: `python app.py > app.log 2>&1 &`).

---

## 6. Networking

### Q&A Phỏng Vấn Cốt Lõi

#### HTTP là gì?
*   **Trả lời:** Giao thức truyền tải siêu văn bản (Hypertext Transfer Protocol) dùng để giao tiếp client-server trên web, truyền dữ liệu dưới dạng text thuần túy (plaintext) nên không bảo mật.

#### HTTPS là gì và khác gì HTTP?
*   **Trả lời:** Là phiên bản bảo mật của HTTP (HTTP Secure). Nó mã hóa dữ liệu truyền tải bằng SSL/TLS để ngăn chặn việc nghe lén, giả mạo dữ liệu.

#### DNS (Domain Name System) là gì?
*   **Trả lời:** Hệ thống phân giải tên miền. Nó hoạt động giống như một danh bạ điện thoại, giúp dịch các tên miền dễ nhớ (như `shopmart.local`) thành các địa chỉ IP số để máy tính hiểu và kết nối.

#### DNS hoạt động thế nào để dịch tên miền thành IP?
*   **Trả lời:** Khi bạn gõ tên miền, trình duyệt sẽ check cache local trước. Nếu không có, nó gửi yêu cầu đến Resolver (nhà mạng). Resolver tiếp tục đi hỏi lần lượt các Name Server cấp cao từ trên xuống: Root Name Server (`.`) -> TLD Name Server (`.com`) -> Authoritative Name Server (nơi quản lý trực tiếp bản ghi của domain) để lấy về địa chỉ IP chính xác rồi trả về cho client.

#### TCP (Transmission Control Protocol) là gì?
*   **Trả lời:** Giao thức truyền tải hướng kết nối, đảm bảo dữ liệu gửi đi được truyền tải tin cậy, đúng thứ tự và không bị mất mát thông tin.

#### TCP Handshake (Bắt tay 3 bước) là gì và hoạt động thế nào?
*   **Trả lời:** Là quá trình thiết lập kết nối tin cậy trước khi truyền dữ liệu qua TCP:
    1. Client gửi cờ `SYN` (Yêu cầu kết nối).
    2. Server phản hồi bằng cờ `SYN-ACK` (Xác nhận và đồng ý kết nối).
    3. Client gửi cờ `ACK` (Xác nhận lại). Bắt tay hoàn tất, đường truyền sẵn sàng.

#### Port (Cổng kết nối) là gì?
*   **Trả lời:** Cổng logic trên hệ điều hành để phân định các dịch vụ hoặc ứng dụng khác nhau chạy trên cùng một server vật lý (ví dụ: Web chạy port 80/443, PostgreSQL port 5432, Redis port 6379).

#### Firewall (Tường lửa) là gì?
*   **Trả lời:** Hệ thống bảo mật giám sát và kiểm soát lưu lượng mạng ra/vào dựa trên các quy tắc bảo mật được thiết lập sẵn.

#### Quy tắc inbound và outbound của Firewall là gì?
*   **Trả lời:** 
    *   **Inbound rule:** Kiểm soát lưu lượng đi từ ngoài internet/mạng khác kết nối vào bên trong server (mặc định chặn hết, phải mở port cụ thể).
    *   **Outbound rule:** Kiểm soát lưu lượng đi từ trong server kết nối ra ngoài internet (mặc định mở hết để tải thư viện, gọi API bên ngoài).

#### IP Private vs IP Public là gì?
*   **Trả lời:** 
    *   **IP Private (IP nội bộ):** Dùng để các thiết bị giao tiếp với nhau trong mạng LAN/VPC nội bộ, internet không thể nhìn thấy hoặc gọi trực tiếp tới IP này.
    *   **IP Public (IP công cộng):** Địa chỉ IP duy nhất trên toàn thế giới để các thiết bị kết nối trực tiếp với internet.

#### NAT (Network Address Translation) là gì?
*   **Trả lời:** Kỹ thuật dịch chuyển địa chỉ IP. Thường dùng để cho phép các máy chủ trong mạng nội bộ (dùng IP Private) đi ra ngoài internet bằng một địa chỉ IP Public đại diện duy nhất.

#### Pull-based vs Push-based monitoring là gì?
*   **Trả lời:** 
    *   **Pull-based:** Server giám sát chủ động gửi request kéo (pull) metrics từ các ứng dụng/máy chủ về (ví dụ: Prometheus).
    *   **Push-based:** Các máy chủ/ứng dụng tự cài agent để chủ động gửi (push) metrics lên server giám sát tập trung (ví dụ: Datadog, CloudWatch).

#### Vì sao Push-based monitoring giải quyết được vấn đề Firewall/NAT của mạng nội bộ (Private Network)?
*   **Trả lời:** Vì các máy chủ nằm sau firewall/NAT trong Private Network chặn mọi kết nối inbound (đi vào), khiến server giám sát bên ngoài không thể "kéo" (pull) data được. Tuy nhiên, NAT/Firewall luôn cho phép kết nối outbound (đi ra) nên cơ chế "đẩy" (push) giúp agent từ bên trong chủ động kết nối ra ngoài để gửi metrics lên Cloud/Monitoring Server thành công.

#### Security Group là gì?
*   **Trả lời:** Là tường lửa ảo hoạt động ở cấp **máy chủ (Instance)** trong AWS để kiểm soát traffic inbound/outbound. Nó hoạt động kiểu **Stateful** (nếu mở cổng inbound thì tự động cho phép traffic trả về đi ra tương ứng mà không cần mở outbound).

#### Network ACL (NACL) là gì?
*   **Trả lời:** Tường lửa hoạt động ở cấp **mạng con (Subnet)** trong AWS. Nó hoạt động kiểu **Stateless** (phải khai báo tường minh cả luật inbound và outbound cho chiều đi/về).

#### So sánh Security Group và NACL trong AWS?
*   **Trả lời:** 
    *   **Security Group:** Bảo vệ ở cấp Instance. Stateful. Chỉ hỗ trợ luật cho phép (Allow).
    *   **NACL:** Bảo vệ ở cấp Subnet. Stateless (phải khai báo 2 chiều). Hỗ trợ cả luật cho phép (Allow) và luật chặn (Deny).

---

## 7. Redis & PostgreSQL

### Q&A Phỏng Vấn Cốt Lõi

#### Redis là gì?
*   **Trả lời:** Là hệ thống lưu trữ dữ liệu dạng Key-Value trong bộ nhớ RAM (In-Memory database) siêu nhanh, độ trễ cực thấp (<1ms).

#### Redis được dùng để Cache và Rate Limiting như thế nào?
*   **Trả lời:** 
    *   **Cache:** Lưu tạm các dữ liệu truy vấn nặng từ database chính. Khi client gọi, backend lấy từ Redis ra ngay lập tức thay vì chạy lại câu lệnh SQL nặng nề.
    *   **Rate Limiting:** Sử dụng các lệnh như `INCR` (tăng số đếm) kết hợp `EXPIRE` (thiết lập thời gian sống - TTL) cho một IP Client. Nếu số đếm vượt quá ngưỡng trong khoảng thời gian quy định thì chặn request tiếp theo.

#### PostgreSQL là gì và Persistent Data là gì?
*   **Trả lời:** 
    *   **PostgreSQL:** Hệ quản trị cơ sở dữ liệu quan hệ (RDBMS) mạnh mẽ, mã nguồn mở, hỗ trợ chuẩn SQL và lưu trữ dữ liệu bền vững.
    *   **Persistent Data:** Dữ liệu được lưu trữ cố định trên ổ đĩa cứng, đảm bảo không bị mất đi khi ứng dụng tắt, server khởi động lại hoặc mất điện đột ngột.

#### PostgreSQL đảm bảo lưu trữ dữ liệu an toàn (ACID) như thế nào?
*   **Trả lời:** Tuân thủ chặt chẽ tính chất ACID (Atomicity, Consistency, Isolation, Durability) và sử dụng cơ chế ghi nhật ký trước (WAL - Write-Ahead Logging) xuống ổ đĩa cứng trước khi cập nhật dữ liệu thật, giúp dữ liệu phục hồi nguyên vẹn khi xảy ra sự cố đột ngột.

#### So sánh và giải thích tại sao không lưu trữ toàn bộ dữ liệu vào Redis?
*   **Trả lời:** 
    1. **Chi phí:** RAM đắt hơn ổ cứng rất nhiều, không thể lưu hàng trăm GB dữ liệu lớn trên RAM một cách kinh tế.
    2. **An toàn:** Dữ liệu trên RAM dễ mất khi sập nguồn (dù Redis có cơ chế snapshot AOF/RDB nhưng vẫn không an toàn tuyệt đối như DB ghi đĩa).
    3. **Tính năng:** Redis không hỗ trợ các câu lệnh truy vấn phức tạp (SQL JOINs, ràng buộc khóa ngoại, transaction phức tạp).

---

## 8. ShopMart Deep-Dive (Kiến trúc dự án)

Câu hỏi cụ thể về code và hạ tầng của ShopMart:

#### "Explain the architecture."
*   **Trả lời:** "Store upload CSV lên **S3 Raw**. S3 trigger **Lambda** chạy. Lambda check trùng lặp trên **DynamoDB** (idempotency). Nếu file mới, Lambda lọc sạch: data tốt ghi vào **S3 Processed dưới dạng Parquet** (chia partition theo ngày), data lỗi ghi vào **S3 Quarantine dưới dạng CSV** và cảnh báo qua **SNS**. Data sạch được mapping qua **Glue Data Catalog** để Business dùng **Athena** gõ SQL query."

#### "Why DynamoDB?" (Không phải PostgreSQL? Không phải Redis?)
*   **Trả lời:** Vì hệ thống cần chạy phi máy chủ (Serverless). DynamoDB tự động scale, không sợ nghẽn số lượng connection (connection limit) khi hàng trăm Lambda gọi tới cùng lúc như Postgres, và chi phí chạy On-Demand của nó rẻ hơn nhiều so với việc duy trì server Postgres chạy 24/7. Nó cũng bền vững dữ liệu hơn Redis.

#### "What is idempotency?" (Được code như thế nào?)
*   **Trả lời:** Là cơ chế đảm bảo một file dù có upload nhiều lần thì hệ thống cũng chỉ xử lý đúng một lần để tránh tính trùng doanh số. Trong code ShopMart, [hàm `_check_idempotency`](file:///e:/Shopmart/src/pipeline.py#L50-L71) sẽ lấy tên file query vào bảng DynamoDB. Nếu thấy file đó đã có status là `SUCCESS` thì Lambda lập tức bỏ qua không xử lý nữa.

#### "Why Lambda?" (Tại sao không EC2?)
*   **Trả lời:** Vì các cửa hàng chỉ upload file bán hàng một lần vào khung giờ cố định buổi sáng. Dùng EC2 chạy 24/7 sẽ rất lãng phí tiền thuê server chạy không tải. Lambda chạy serverless, chỉ tính tiền khi có file upload lên (tiết kiệm chi phí tối đa).

#### "Why Parquet?" (Tại sao không CSV?)
*   **Trả lời:** Parquet lưu trữ dữ liệu dạng cột và nén tốt, giúp giảm đến 90% dung lượng lưu trữ trên S3. Đặc biệt, khi dùng Athena để truy vấn SQL, Athena chỉ quét đúng cột cần tính toán thay vì quét cả file CSV, giúp câu lệnh chạy nhanh hơn và giảm chi phí quét đĩa (Athena tính tiền trên dung lượng dữ liệu quét).

#### "What if Lambda fails?"
*   **Trả lời:** 
    *   Lambda chạy bất đồng bộ qua S3 trigger sẽ tự động retry 2 lần.
    *   Nếu vẫn lỗi, S3 Event được đẩy vào hàng đợi lỗi **SQS DLQ** để lưu vết sự kiện chờ xử lý tay.
    *   Hàm Lambda có cơ chế try-catch để ghi nhận status `FAILED` lên DynamoDB và gửi mail cảnh báo thông qua SNS.

#### "How would you scale this?"
*   **Trả lời:** Hệ thống hiện tại dùng hoàn toàn serverless (S3, Lambda, DynamoDB, Athena) nên khả năng scale là tự động. Tuy nhiên, cần lưu ý giới hạn số lượng Lambda chạy song song (concurrency limit, mặc định 1000) và write capacity của DynamoDB (cần cấu hình Auto-Scaling hoặc On-Demand mode).

#### "What resources are provisioned by Terraform?"
*   **Trả lời:** Terraform trong [main.tf](file:///e:/Shopmart/iac/main.tf) tạo ra:
    *   3 cái S3 buckets (raw, processed, quarantine).
    *   Bảng DynamoDB `shopmart-metadata`.
    *   SNS Topic `shopmart-pipeline-alerts` to báo lỗi.
    *   AWS Lambda function xử lý dữ liệu và gắn AWS SDK Pandas Layer.
    *   IAM Role và Policy phân quyền chi tiết cho Lambda.
    *   S3 Bucket Notification trigger để kết nối sự kiện upload sang Lambda.

#### "What does ArgoCD actually do?"
*   **Trả lời:** ArgoCD làm nhiệm vụ GitOps: Nó canh thư mục chứa các file YAML cấu hình K8s trên Git (`devops/k8s`). Khi phát hiện có commit mới trên Git, nó sẽ tự động đồng bộ (apply) xuống cluster. Nó cũng lo việc tự sửa lỗi (Self-healing) - nếu ai đó sửa tay cấu hình trên cluster, nó sẽ tự động đè lại cấu hình chuẩn từ Git.

---

## 9. Cypher Deep-Dive (Kiến trúc dự án)

Câu hỏi cụ thể về code và hạ tầng của Cypher — một nền tảng monitoring mạng nội bộ push-based:

#### "Cypher là gì? Explain the project."
*   **Trả lời:** Là nền tảng giám sát mạng (network monitoring) tự lưu trữ (self-hosted), hoạt động theo cơ chế **push-based**. Thay vì server trung tâm đi kéo (pull) dữ liệu — cách này không khả thi khi thiết bị nằm sau tường lửa (NAT/private network) — các agent nhẹ chạy ngay trong mạng nội bộ, tự động kiểm tra kết nối (probe) target rồi đẩy dữ liệu về backend. Khi target mất kết nối (DOWN), agent tự chạy chẩn đoán lỗi (diagnostics) và gửi báo cáo sự cố về.
    *   **Self-hosted**: tự cài đặt, chạy trên server của chính bạn — không phụ thuộc dịch vụ bên ngoài. **Probe**: hành động thử kết nối đến một mục tiêu để kiểm tra xem mục tiêu còn sống không. **Push-based**: thiết bị con chủ động gửi dữ liệu lên server tổng, ngược với pull-based là server tổng đi hỏi từng thiết bị.

#### "Explain the architecture."
*   **Trả lời:** Gồm 4 thành phần chính:
    1. **Agent** (Python thuần, không thư viện ngoài): Chạy trong mạng nội bộ. Probe TCP mục tiêu, đo độ trễ (latency). UP → gửi `POST /heartbeat`. DOWN → chạy diagnostics rồi gửi `POST /incident`.
    2. **FastAPI Backend**: Nhận telemetry, xác thực chữ ký HMAC, lưu trạng thái vào **Redis** (cache nhanh) và sự cố vào **PostgreSQL** (lưu bền vững). Kích hoạt thông báo.
    3. **Redis**: Lưu heartbeat mới nhất theo key `heartbeat:{agent_id}:{target}`. Dashboard đọc từ đây để hiển thị trạng thái realtime.
    4. **Dashboard** (Vanilla JS + TailwindCSS): Website SPA — đọc `/api/v1/status` (Redis) và `/api/v1/incidents` (Postgres) để hiển thị.
    *   **Telemetry**: dữ liệu trạng thái và đo lường gửi về từ agent (status UP/DOWN, latency ms). **SPA (Single Page Application)**: website không tải lại trang, cập nhật nội dung bằng JavaScript chạy ngay trên trình duyệt.

#### "Why push-based monitoring? (Không phải pull-based?)"
*   **Trả lời:** Vì các target thường nằm trong mạng riêng (private network) chặn toàn bộ kết nối từ ngoài vào (inbound). Server bên ngoài không thể chủ động gọi vào để "kéo" (pull) dữ liệu. Push-based cho phép agent nằm ở bên trong mạng nội bộ chủ động gửi (outbound) dữ liệu ra ngoài — firewall mặc định luôn cho phép kết nối ra.
*   **Ví dụ thực tế (giám sát DB nội bộ từ nhà):**
    *   **Ngữ cảnh:** Công ty bạn có kiến trúc mạng:
        ```text
        Internet -> [Firewall] -> DMZ -> [Firewall] -> Internal DB (10.0.1.15, Không public)
        ```
        Nếu bạn ở nhà, máy tính của bạn **không bao giờ** kết nối trực tiếp được tới `10.0.1.15`.
    *   **Nếu dùng Pull-based (như Prometheus truyền thống):** Server Prometheus đặt bên ngoài internet (hoặc máy ở nhà bạn) sẽ chịu chết, không thể kéo metric từ `10.0.1.15` trừ khi đục lỗ firewall/NAT (cực kỳ nguy hiểm về bảo mật).
    *   **Cách Cypher giải quyết:** Bạn deploy một **Cypher Agent** nằm trong vùng mạng nội bộ của công ty (ví dụ: trong DMZ hoặc chung subnet có quyền kết nối đến `10.0.1.15`).
        1. Agent này chạy TCP probe local đến `10.0.1.15:5432` trong mạng nội bộ.
        2. Sau khi probe, agent chủ động thực hiện kết nối **outbound** (đi ra ngoài qua các lớp Firewall) để đẩy kết quả (heartbeat/incident) về Cypher Backend (đặt trên Cloud VPS công khai).
        3. Bạn ngồi ở nhà, truy cập vào Cypher Dashboard (kết nối tới Cypher Backend) để xem trạng thái database. Hoàn toàn không cần máy nhà bạn hay Backend phải chui vào mạng nội bộ của công ty.
    *   *Ghi chú:* Vì firewall của doanh nghiệp hầu hết đều cho phép outbound traffic (HTTPS ra cổng 443), luồng push này chạy trơn tru mà không cần IT/Security cấu hình gì đặc biệt.

#### "What is HMAC and how does Cypher use it?"
*   **Trả lời:**
    *   **HMAC là gì:** Là cơ chế tạo "chữ ký số" từ nội dung dữ liệu + một khóa bí mật (secret key). Chỉ ai có đúng secret key mới tạo lại được chữ ký đúng — dùng để xác nhận người gửi là thật, dữ liệu không bị giả mạo hoặc chỉnh sửa trên đường truyền.
    *   **Cypher dùng thế nào:**
        1. Khi đăng ký agent, backend tạo `key_id` (mã định danh công khai) và `key_secret` (chuỗi bí mật). Database lưu SHA256 hash của secret — không lưu bản gốc để dù DB bị lộ, secret vẫn không bị lấy được.
        2. Agent tính chữ ký: `signature = HMAC-SHA256(SHA256(key_secret), JSON_body)` — lấy hash của secret làm khóa, lấy nội dung JSON làm dữ liệu để ký.
        3. Agent gửi kèm 3 header: `X-Cypher-Key-Id` (tên key), `X-Cypher-Signature` (chữ ký), `X-Cypher-Timestamp` (thời điểm gửi).
        4. Backend lấy `key_hash` từ DB theo `key_id`, tự tính lại chữ ký kỳ vọng, dùng `hmac.compare_digest` để so sánh.
    *   **Payload**: nội dung dữ liệu gửi đi trong request (ở đây là chuỗi JSON). **HTTP Header**: dòng metadata đính kèm phía trên nội dung trong mỗi request/response — dùng để truyền thông tin phụ như xác thực, kiểu dữ liệu, thời gian. **SHA256 hash**: hàm băm một chiều — biến bất kỳ chuỗi nào thành chuỗi 64 ký tự cố định, không thể đảo ngược để lấy lại bản gốc. **`hmac.compare_digest`**: hàm so sánh hai chuỗi theo cách không để lộ thời gian phản hồi (timing-safe) — ngăn hacker đoán chữ ký đúng dần từng ký tự dựa vào tốc độ server trả lời.

#### "What is Rate Limiting? How is it implemented?"
*   **Trả lời:**
    *   **Rate Limiting là gì:** Cơ chế giới hạn số lượng request một nguồn có thể gửi trong một khoảng thời gian nhất định. Nếu vượt ngưỡng, server từ chối tiếp nhận và trả lỗi. Mục đích: ngăn agent bị chiếm quyền hoặc hacker gửi hàng nghìn request/giây làm sập server (DDoS).
    *   **Cypher implement thế nào:** Dùng Redis đếm request theo từng phút:
        1. Mỗi request đến, backend lấy `key_id` từ header (hoặc địa chỉ IP nếu không có key).
        2. Tạo Redis key: `ratelimit:{key_id}:{phút_hiện_tại}` — phút được tính bằng `epoch // 60` (lấy Unix timestamp chia cho 60).
        3. Gọi lệnh `INCR` để tăng bộ đếm lên 1. Nếu vượt quá 120 → trả về HTTP 429.
        4. Redis key tự xóa sau 120 giây để bộ nhớ không đầy.
    *   **Redis key**: cặp tên–giá trị lưu trong Redis, dùng tên duy nhất để theo dõi từng người gửi và từng phút riêng biệt. **INCR**: lệnh Redis tăng giá trị số nguyên của key lên 1; nếu key chưa tồn tại, tự tạo mới với giá trị 1. **HTTP 429 (Too Many Requests)**: mã lỗi HTTP báo client đã gửi quá nhiều request — hãy chờ rồi thử lại. **DDoS (Distributed Denial of Service)**: tấn công làm sập server bằng cách gửi lượng request khổng lồ từ nhiều nguồn cùng lúc.

#### "What is Root Cause Analysis (RCA)? How is it implemented?"
*   **Trả lời:**
    *   **RCA là gì:** Phân tích nguyên nhân gốc rễ của sự cố. Trong monitoring, thay vì chỉ biết "một agent báo target DOWN", RCA còn xác định được liệu target có thật sự chết hay chỉ do vấn đề mạng cục bộ của riêng một agent (ví dụ đứt cáp ISP tại văn phòng đó).
    *   **Cypher implement thế nào:** Khi nhận `POST /incident`, hàm `perform_rca()` chạy:
        1. Query Redis theo pattern `heartbeat:*:{target}` — lấy trạng thái của **tất cả** agent đang theo dõi cùng target đó.
        2. Đếm bao nhiêu agent thấy DOWN, so với tổng:
            *   Tất cả DOWN → **Global Outage**: target thật sự mất kết nối.
            *   Chỉ 1 agent DOWN → **Localized Issue**: vấn đề ISP/mạng riêng của agent đó, target vẫn sống.
            *   Một số DOWN → **Partial Outage**: sự cố một phần.
        3. Kết quả ghi vào PostgreSQL và đính kèm trong alert.
    *   **Pattern `heartbeat:*:{target}`**: trong Redis, dấu `*` là ký tự đại diện (wildcard) — khớp với bất kỳ chuỗi nào ở vị trí đó. Câu lệnh này lấy heartbeat của mọi agent đang monitor đúng target đó. **False alert**: cảnh báo sai — target vẫn UP nhưng hệ thống báo DOWN vì lỗi mạng cục bộ của một agent. **ISP (Internet Service Provider)**: nhà cung cấp dịch vụ internet — sự cố ISP tại một địa điểm có thể khiến agent ở đó mất kết nối nhưng agent ở chỗ khác vẫn bình thường.

#### "What diagnostics does the agent collect when a target goes DOWN?"
*   **Trả lời:** Ngay sau khi TCP probe thất bại, agent chạy 5 loại chẩn đoán để tự động thu thập bằng chứng:
    1. **ICMP Ping**: Gửi một gói tin thử nghiệm đến host, chờ phản hồi. Cho biết host có tồn tại và mạng có thể đến được không ở mức cơ bản nhất.
        *   **ICMP**: giao thức kiểm tra mạng cơ bản, không dùng cổng TCP/UDP — chỉ "hỏi" xem máy có còn sống không. **`-n 1` / `-c 1`**: chỉ gửi 1 gói ping duy nhất. **`-w 1000` / `-W 1`**: chờ tối đa 1 giây rồi bỏ cuộc, không chờ lâu làm chậm agent.
    2. **DNS Resolution**: Dịch hostname (tên miền dạng chữ như `api.example.com`) sang địa chỉ IP bằng hàm `socket.getaddrinfo()`. Nếu không ra được IP → tên miền sai hoặc DNS bị hỏng.
        *   **DNS (Domain Name System)**: hệ thống tra cứu tên miền, giống danh bạ điện thoại — nhập tên → trả ra số (IP). **Hostname**: tên miền dạng chữ. **IP (Internet Protocol address)**: địa chỉ số như `142.250.185.46` — máy tính dùng IP để kết nối thực sự, không dùng tên miền.
    3. **Traceroute**: Theo dõi từng bước nhảy (hop) từ agent đến target để xem gói tin đi qua những router nào và bị dừng ở đâu.
        *   **Hop**: mỗi router hoặc thiết bị mạng mà gói tin phải đi qua trên đường đến đích. **`-h 10` / `-m 10`**: giới hạn tối đa 10 hop — dừng sớm thay vì đợi vô tận. **`-d` / `-n`**: không dịch IP thành tên miền — chạy nhanh hơn.
    4. **HTTP Diagnostic**: Nếu port là cổng web tiêu chuẩn (80, 443, 8080, 8443), agent gửi một yêu cầu tải trang (HTTP GET) đến target và ghi lại toàn bộ kết quả trả về.
        *   **HTTP GET**: phương thức yêu cầu tải nội dung từ server — giống trình duyệt mở một trang web. **Status code**: con số server trả về để báo kết quả của yêu cầu — 200 (thành công), 404 (không tìm thấy trang), 500 (server bị lỗi nội bộ). **Response headers**: các dòng thông tin server gửi kèm phía trên nội dung — ghi rõ loại dữ liệu trả về, thời gian server, ngôn ngữ, encoding... **Response body**: nội dung thực sự server trả về — thường là HTML của trang web hoặc dữ liệu JSON. **200 bytes đầu**: chỉ đọc 200 ký tự đầu của body để không mất thời gian tải cả file lớn.
    5. **DNS Verification**: Resolve đồng thời cả hostname của target lẫn `google.com` (dùng làm chuẩn đối chứng). So sánh kết quả để tự kết luận nguyên nhân:
        *   `google.com` resolve OK nhưng target FAIL → DNS của target bị sai cấu hình hoặc tên miền không tồn tại.
        *   Cả hai đều FAIL → DNS resolver của chính agent bị hỏng hoặc agent mất kết nối internet hoàn toàn.
        *   **Control host**: host đối chứng (ở đây là `google.com`) — gần như luôn hoạt động, dùng để kiểm tra xem vấn đề là do target hay do agent. **DNS resolver**: server chịu trách nhiệm trả lời câu hỏi DNS — thường là router cục bộ hoặc server DNS của nhà mạng.

#### "Why Redis for live status and PostgreSQL for incidents?"
*   **Trả lời:** Hai nhu cầu khác nhau hoàn toàn nên dùng hai công cụ phù hợp:
    *   **Redis (trạng thái sống):** Dashboard cần hiển thị trạng thái hàng trăm agent **gần như tức thì** (<1ms). Redis lưu dữ liệu thẳng trong RAM nên đọc cực nhanh. Chỉ cần heartbeat mới nhất — ghi đè là xong, không cần lưu lịch sử.
    *   **PostgreSQL (sự cố lịch sử):** Incidents cần lưu **bền vững trên ổ đĩa** qua nhiều tháng, cần truy vấn lịch sử, tính uptime theo ngày. PostgreSQL đảm bảo ACID — dữ liệu không mất dù server tắt đột ngột.
    *   → Quyết định kiến trúc ghi trong `DECISIONS.txt`: *"Redis stores only the latest heartbeat. Historical data belongs in PostgreSQL."*
    *   **RAM (Random Access Memory)**: bộ nhớ tạm thời cực nhanh nhưng mất sạch khi mất điện. **ACID**: bộ 4 đảm bảo của database — Atomicity (ghi hết hoặc không ghi gì), Consistency (dữ liệu luôn hợp lệ), Isolation (các thao tác không xung đột), Durability (đã lưu thì không mất).

#### "What API endpoints does the backend expose?"
*   **Trả lời:** Chia làm 3 nhóm:
    *   **Agent-facing** (bắt buộc có chữ ký HMAC): `POST /heartbeat` (agent báo UP), `POST /incident` (agent báo DOWN kèm diagnostics).
    *   **Dữ liệu dashboard**: `GET /api/v1/status` (trạng thái live từ Redis), `GET /api/v1/incidents` (lịch sử sự cố từ Postgres, tối đa 50), `GET /api/v1/metrics/uptime` (% uptime 7 ngày).
    *   **Quản lý**: `GET/POST/PUT/DELETE /api/v1/destinations` (CRUD target), `GET/POST/PUT/DELETE /api/v1/agents` (CRUD agent).
    *   **Tiện ích**: `GET /api/v1/mode` (trả về đang ở single/auth mode), `GET /dashboard` (phục vụ file HTML dashboard).
    *   **Endpoint**: địa chỉ URL cụ thể trên server để client gửi request đến thực hiện một chức năng. **CRUD**: 4 thao tác cơ bản với dữ liệu — Create (POST tạo mới), Read (GET đọc), Update (PUT sửa), Delete (DELETE xóa).

#### "What notification channels does Cypher support?"
*   **Trả lời:** 5 kênh thông báo, tất cả kích hoạt **đồng thời** (concurrent) — không kênh nào phải chờ kênh khác:
    1. **Telegram**: Gửi tin nhắn có định dạng HTML qua Telegram Bot API. Cần cấu hình Bot Token và Chat ID.
    2. **Slack**: Gửi tin nhắn văn bản đến Incoming Webhook URL của workspace Slack.
    3. **Microsoft Teams**: Gửi thẻ tin nhắn (MessageCard) với thanh màu đỏ khi DOWN, xanh khi UP.
    4. **PagerDuty**: Tạo incident qua V2 Events API. Mức độ nghiêm trọng `critical` khi DOWN, `info` khi UP. `dedup_key = cypher-{agent_id}-{target}` để tránh tạo nhiều incident trùng cho cùng một sự cố.
    5. **Generic Webhook**: Gửi dữ liệu JSON đến bất kỳ URL tùy chỉnh nào.
    *   Tất cả optional — bỏ trống biến môi trường trong `.env` là disable. Một kênh lỗi không ảnh hưởng kênh khác.
    *   **Concurrent**: chạy song song cùng lúc — dùng `asyncio.gather()` để gửi đến 5 kênh cùng một lúc thay vì lần lượt từng cái. **Incoming Webhook**: URL đặc biệt mà Slack/Teams cấp cho bạn — chỉ cần gửi POST JSON đến đó là tin xuất hiện ngay trong channel. **dedup_key**: khóa định danh duy nhất cho một sự cố — PagerDuty dùng key này để nhận ra "đây vẫn là cùng sự cố cũ" thay vì tạo thêm incident mới mỗi lần agent báo lại.

#### "How is the agent deployed?"
*   **Trả lời:** 3 cách triển khai tùy môi trường:
    1. **Docker Compose** (`docker-compose.yml`): Dành cho môi trường phát triển local. Một lệnh `docker compose up` khởi chạy toàn bộ: `postgres:16-alpine`, `redis:7-alpine`, `backend` (FastAPI), `agent`. Agent cấu hình `depends_on: backend` — chờ backend healthy rồi mới chạy.
    2. **Kubernetes Helm Chart** (`deployments/helm/cypher-agent/`): Dành cho production trên K8s cluster. Deploy agent dưới dạng Deployment hoặc DaemonSet. Kubernetes Secret lưu `AGENT_KEY_ID`/`AGENT_KEY_SECRET` mã hóa an toàn. ConfigMap lưu danh sách TARGETS và cấu hình probe.
    3. **Serverless** (`agent/serverless_agent.py`): Agent chạy không cần server thường trực — phù hợp khi chỉ cần probe theo lịch. AWS Lambda (EventBridge cron), Azure Functions (TimerTrigger), Google Cloud Run (Cloud Scheduler). Mỗi lần kích hoạt, chạy một chu kỳ probe rồi tắt.
    *   **Helm Chart**: bộ template Kubernetes đóng gói sẵn, dùng lệnh `helm install` thay vì viết từng file YAML riêng. **DaemonSet**: loại workload K8s đảm bảo mỗi Node trong cluster chạy đúng 1 Pod — dùng khi muốn agent có mặt trên mọi máy trong cluster. **Serverless**: mô hình cloud chỉ cấp tài nguyên khi code cần chạy, giải phóng ngay sau khi xong — không tốn tiền khi không hoạt động.

#### "Các agent của Cypher có thể deploy ở đâu? Nếu chỉ ở máy cá nhân mà monitor instance ở Singapore thì ping có chính xác không?"
*   **Trả lời:**
    *   **Vị trí deploy:** Agent có thể deploy **anywhere in the world** — bất kỳ vùng mạng nào (Cloud VPS ở US/Singapore, K8s cluster nội bộ, PC cá nhân, hoặc AWS Lambda). Chỉ cần môi trường đó chạy được Python/Docker và có kết nối outbound ra internet/VPN để gọi API về Backend.
    *   **Độ chính xác của Ping:** Nếu bạn chỉ chạy agent ở máy cá nhân ở nhà (ví dụ tại Việt Nam) để monitor một instance ở Singapore, ping đo được chắc chắn **không chính xác** phản ánh latency thực tế của target đó (vì bị cộng thêm độ trễ truyền dẫn cáp quang biển, mạng nhà, Wi-Fi...).
    *   **Cách giải quyết:** Deploy một instance agent chạy trên một VPS nhỏ **ngay tại Singapore** (cùng vùng/datacenter với target). Agent đó probe target tại chỗ với latency cực thấp và chính xác (gần như <1ms), rồi push kết quả về Backend. Khi bạn ngồi ở nhà mở dashboard lên, bạn đang xem số liệu đo trực tiếp từ Singapore cực kỳ chính xác.

#### "What is Single-User Mode vs Auth Mode?"
*   **Trả lời:** Backend có 2 chế độ vận hành, điều khiển qua biến môi trường `SINGLE_USER_MODE`:
    *   **Single-User Mode (mặc định `true`):** Không cần đăng nhập. Mọi API đều mở tự do, không cần token JWT. Dùng cho cá nhân, homelab, demo nhanh.
    *   **Auth Mode (`false`):** Bật xác thực JWT. Người dùng phải đăng ký qua `/auth/register` và đăng nhập qua `/auth/login` để lấy token. Data của mỗi user được phân tách qua `user_key` — sẵn sàng cho mô hình SaaS nhiều khách hàng. Xác thực HMAC của agent vẫn bắt buộc ở cả hai chế độ.
    *   **JWT (JSON Web Token)**: chuỗi token mã hóa server cấp sau khi đăng nhập thành công. Client đính kèm vào mọi request tiếp theo để server nhận ra "đây là ai". **Multi-tenant (SaaS)**: nhiều tổ chức/khách hàng dùng chung một hệ thống nhưng dữ liệu của mỗi bên hoàn toàn cách ly nhau.

#### "What tech stack does Cypher use?"
*   **Trả lời:**
    *   **Backend:** Python 3.12, FastAPI (web framework bất đồng bộ), SQLAlchemy + asyncpg (kết nối PostgreSQL không blocking).
    *   **Database:** PostgreSQL 16 (lưu incidents, agents, uptime bền vững trên đĩa) + Redis 7 (live status cache + rate limiting trên RAM).
    *   **Frontend:** Vanilla JavaScript SPA + TailwindCSS (glassmorphism, dark mode). Một file HTML duy nhất, FastAPI phục vụ tại `/dashboard` — không dùng React/Vue.
    *   **Agent:** Thuần Python stdlib — `socket`, `subprocess`, `urllib`, `json`, `hmac`, `hashlib`. Không cài thêm thư viện nào → chạy được ở mọi nơi có Python.
    *   **Infra:** Docker Compose (dev local), Helm Charts (Kubernetes), Nginx (reverse proxy + SSL termination).
    *   **Bất đồng bộ (Async)**: server xử lý nhiều request cùng lúc mà không cần chờ từng cái hoàn thành — như phục vụ nhiều khách hàng song song thay vì xếp hàng. **stdlib**: bộ thư viện chuẩn có sẵn của Python, không cần cài thêm bất cứ gì. **Reverse proxy**: Nginx đứng trước FastAPI nhận request từ internet, chuyển tiếp vào — đồng thời xử lý SSL/HTTPS để FastAPI không cần lo.

#### "Mô tả luồng dữ liệu từ đầu đến cuối?"
*   **Trả lời:** *"Agent TCP probe target mỗi 30 giây. Nếu UP → gửi `POST /heartbeat` kèm chữ ký HMAC → backend lưu vào Redis key `heartbeat:{agent_id}:{target}`. Nếu DOWN → agent chạy 5 diagnostics (ping, DNS, traceroute, HTTP, DNS verification) → gửi `POST /incident` kèm HMAC → backend xác minh chữ ký, kiểm tra rate limit → lưu trạng thái DOWN vào Redis → query Redis toàn bộ agent của target đó để tính RCA → ghi incident đầy đủ vào PostgreSQL → chạy nền dispatch alert đồng thời đến Telegram/Slack/Teams/PagerDuty/Webhook. Dashboard tự gọi `/api/v1/status` mỗi 30 giây để cập nhật ô trạng thái (status tile)."*
    *   **TCP probe**: thử mở kết nối TCP đến `host:port` trong thời gian timeout định sẵn. Kết nối thành công → UP, timeout hoặc bị từ chối → DOWN. **Status tile**: ô hiển thị trạng thái của một target trên dashboard — xanh (UP) hoặc đỏ (DOWN) kèm latency đo được.

